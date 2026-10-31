"""AI co-pilot: explain one trace step, or answer a question about it.

The prompt receives only the selected step, the source lines, and the
run's error, all from the stored trace. Nothing else about the user,
the room, or any other run goes to the model, and the answer must cite
the step and line it explains. The model provider is one function
behind explain_step, so swapping Groq for something else touches this
file only. The key lives in the GROQ_API_KEY environment variable; it
is never logged, never returned, and never shipped to the browser.
"""

import json
import os

import httpx

from .config import COPILOT_TIMEOUT_SECONDS, MAX_QUESTION_CHARS
from .trace_schema import Trace

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = (
    "You explain one step of a code execution trace. Use only the values "
    "in the trace below. Do not invent values, variables, or steps that "
    "are not in it. Cite the step index and line number in your answer. "
    "Keep it short: what happened at this step and why it matters."
)


class CopilotUnavailable(Exception):
    """The co-pilot cannot answer right now (no key, provider error)."""


class CopilotTimeout(Exception):
    """The model did not answer within the timeout budget."""


def build_explain_prompt(
    trace: Trace, step_index: int, question: str | None = None
) -> list[dict[str, str]]:
    """Build the model messages for one step. Validates its own inputs."""
    if step_index < 0 or step_index >= len(trace.steps):
        raise ValueError(f"step_index {step_index} out of range for {len(trace.steps)} steps")
    if question is not None and len(question) > MAX_QUESTION_CHARS:
        raise ValueError(f"question exceeds {MAX_QUESTION_CHARS} character cap")
    step = trace.steps[step_index]
    payload: dict = {
        "step_index": step.i,
        "line": step.line,
        "source_line": trace.source_lines[step.line - 1] if 0 < step.line <= len(trace.source_lines) else "",
        "event": step.event,
        "stack": step.stack,
        "locals": step.locals,
        "stdout_so_far": step.stdout_so_far,
        "source_lines": trace.source_lines,
        "result_error": trace.result.error,
    }
    if question:
        payload["question"] = question
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload)},
    ]


def _call_groq(messages: list[dict[str, str]]) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise CopilotUnavailable("Groq key not configured")
    model = os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
    try:
        resp = httpx.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 500,
            },
            timeout=COPILOT_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except httpx.TimeoutException as exc:
        raise CopilotTimeout("model did not answer in time") from exc
    except httpx.HTTPError as exc:
        raise CopilotUnavailable("model provider error") from exc
    try:
        text = resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise CopilotUnavailable("model provider error") from exc
    if not isinstance(text, str) or not text.strip():
        raise CopilotUnavailable("model provider error")
    return text.strip()


def explain_step(
    trace: Trace,
    step_index: int,
    question: str | None = None,
    call_model=None,
) -> str:
    """Explain step_index of trace, optionally answering question.

    call_model is the injection point for tests; production passes None
    and gets the Groq call. The returned text always cites the step and
    line, with a factual header added when the model itself did not cite.
    """
    messages = build_explain_prompt(trace, step_index, question)
    text = (call_model or _call_groq)(messages)
    step = trace.steps[step_index]
    lowered = text.lower()
    if f"step {step.i}" not in lowered or f"line {step.line}" not in lowered:
        return f"Step {step.i} (line {step.line}): {text.strip()}"
    return text.strip()

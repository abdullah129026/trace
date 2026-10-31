# ADR-004: AI co-pilot provider and prompt boundary

## Decision

The co-pilot calls Groq's chat completions API over plain httpx (already
a pinned dependency, so no new package) from a single `explain_step`
function in `backend/app/copilot.py`. The API key comes only from the
`GROQ_API_KEY` environment variable. Voice narration uses only the
browser's built-in SpeechSynthesis API; there is no server TTS contract.

## Prompt boundary

The model sees exactly one thing: the selected step (index, line, source
line, event, stack, locals, stdout so far), the full source lines, and
the run's error, all taken from the stored trace. No room metadata, no
other runs, no user data. The answer must cite the step and line; when
the model does not, the API prepends a factual "Step N (line L)" header
rather than inventing content.

## Failure modes

No key configured, or a provider error, means HTTP 503 with a plain
message, not a fabricated explanation. A model answer slower than the
5 second budget means HTTP 504, and the panel tells the user to try
again. Co-pilot calls are rate-limited per IP in their own bucket,
separate from execution, because they cost a model call.

## Alternatives considered

A local rule-based explainer was rejected: it would look like an AI
answer while only restating the trace, and the prompt already requires
the co-pilot to be a real model explanation. A streaming response was
deferred; v1 answers are short and the timeout budget covers them.

"""Python execution tracer.

Runs user source under sys.settrace inside the calling process and records
one step per executed line plus function/module returns: line number, stack,
a JSON-safe snapshot of locals, and stdout so far.

Step semantics are honest about when they fire: a "line" step captures the
state *before* that line executes, a "return" step captures the state after
a frame finished (so the module's return step always holds the final
state and the complete stdout).

Sandboxing (subprocess, scrubbed env, no network, rlimits, wall timeout)
is NOT this module's job. Day 2's runner calls trace_python() inside the
sandbox. Never call this on untrusted code in the API process.
"""

import builtins
import io
import sys
from contextlib import redirect_stdout
from types import FrameType
from typing import Any

from .config import (
    MAX_SNAPSHOT_CHARS,
    MAX_STACK_FRAMES,
    MAX_STDOUT_CHARS,
    MAX_TRACE_STEPS,
    SANDBOX_IMPORT_ALLOWLIST,
)
from .trace_schema import Trace, TraceResult, TraceStep, snapshot_value

USER_CODE_FILENAME = "<trace_user_code>"


class _StepLimitExceeded(BaseException):
    """Raised to halt a runaway run once the step cap is hit.

    BaseException on purpose: a plain Exception could be swallowed by user
    code's `except Exception`, letting the run spin untraced until the wall
    timeout. Only `except BaseException` catches this, which is explicit.
    """


_real_import = builtins.__import__


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    top = name.split(".")[0]
    if level != 0 or top not in SANDBOX_IMPORT_ALLOWLIST:
        raise ImportError(f"import of {name!r} is not allowed in the Trace sandbox")
    return _real_import(name, globals, locals, fromlist, level)


def _restricted_builtins() -> dict:
    """Builtins for sandboxed runs: no open(), imports limited to the allowlist."""
    safe = {name: value for name, value in vars(builtins).items() if name != "open"}
    safe["__import__"] = _guarded_import
    return safe


def _stack_names(frame: FrameType) -> list[str]:
    names: list[str] = []
    f: FrameType | None = frame
    while f is not None and len(names) < MAX_STACK_FRAMES:
        if f.f_code.co_filename == USER_CODE_FILENAME:
            names.append(f.f_code.co_name)
        f = f.f_back
    remaining = 0
    while f is not None:
        if f.f_code.co_filename == USER_CODE_FILENAME:
            remaining += 1
        f = f.f_back
    if remaining:
        names.append(f"<{remaining} frames truncated>")
    return names


def trace_python(
    source: str, room_id: str = "LOCAL", max_steps: int = MAX_TRACE_STEPS, restricted: bool = False
) -> Trace:
    """Trace Python source and return a schema-v1 Trace.

    In-process by design; the caller is responsible for sandboxing.
    With restricted=True the code runs with sandboxed builtins (no open(),
    imports limited to the allowlist). The sandbox driver always passes
    restricted=True; the API process must never run untrusted code at all.
    """
    source_lines = source.splitlines()
    try:
        code = compile(source, USER_CODE_FILENAME, "exec")
    except SyntaxError as e:
        return Trace(
            language="python",
            room_id=room_id,
            source_lines=source_lines,
            steps=[],
            result=TraceResult(status="error", steps_captured=0, error=f"SyntaxError: {e.msg} (line {e.lineno})"),
        )

    steps: list[TraceStep] = []
    stdout_buf = io.StringIO()
    truncated = False

    def record(frame: FrameType, event: str) -> None:
        nonlocal truncated
        if len(steps) >= max_steps:
            # Tracing is disabled before raising: otherwise the exception
            # event for this raise would re-enter the tracer.
            truncated = True
            sys.settrace(None)
            raise _StepLimitExceeded()
        steps.append(
            TraceStep(
                i=len(steps),
                line=frame.f_lineno,
                event=event,
                stack=_stack_names(frame),
                locals={name: snapshot_value(value, max_chars=MAX_SNAPSHOT_CHARS) for name, value in frame.f_locals.items()},
                stdout_so_far=stdout_buf.getvalue()[-MAX_STDOUT_CHARS:],
            )
        )

    def tracer(frame: FrameType, event: str, arg: Any):
        if frame.f_code.co_filename != USER_CODE_FILENAME:
            return None
        # "line" fires before the line runs, "return" after the frame
        # finished; "exception" as it propagates. All three are real data.
        if event in ("line", "return", "exception"):
            record(frame, event)
        return tracer

    status = "ok"
    error: str | None = None
    namespace: dict[str, Any] = {"__name__": "__main__"}
    if restricted:
        namespace["__builtins__"] = _restricted_builtins()
    old_trace = sys.gettrace()
    sys.settrace(tracer)
    try:
        with redirect_stdout(stdout_buf):
            try:
                exec(code, namespace)
            except _StepLimitExceeded:
                status = "truncated"
            except Exception as e:
                status = "error"
                error = f"{type(e).__name__}: {e}"
    finally:
        sys.settrace(old_trace)

    return Trace(
        language="python",
        room_id=room_id,
        source_lines=source_lines,
        steps=steps,
        result=TraceResult(status=status, steps_captured=len(steps), truncated=truncated, error=error),
    )

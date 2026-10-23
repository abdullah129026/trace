"""Sandboxed execution runner.

User code NEVER runs in the API process. Each run spawns a one-shot child
(the Python or Node driver) with a scrubbed environment, a read-only temp
workdir, rlimit caps, and a wall-clock timeout from the parent. The child
prints exactly one Trace JSON document to stdout.

Outcomes:
- user code ok / error / truncated -> returned as a Trace (UI-renderable)
- wall timeout or signal kill -> returned as an error Trace naming the cause
- driver crash / bad JSON -> SandboxError (infrastructure failure, 500)
"""

import json
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from .config import (
    MAX_SNAPSHOT_CHARS,
    MAX_SOURCE_BYTES,
    MAX_STACK_FRAMES,
    MAX_STDOUT_CHARS,
    MAX_TRACE_STEPS,
    MAX_WALL_SECONDS,
    SANDBOX_CPU_SECONDS,
    SANDBOX_FILE_BYTES,
    SANDBOX_MEMORY_BYTES,
    SANDBOX_NODE_HEAP_MB,
    SANDBOX_NODE_MEMORY_BYTES,
    SNAPSHOT_PREVIEW_ITEMS,
    SUPPORTED_LANGUAGES,
)
from .trace_schema import Trace, TraceResult

BACKEND_DIR = Path(__file__).resolve().parent.parent
JS_DRIVER = Path(__file__).resolve().parent / "js_driver" / "tracer.js"


class SandboxError(Exception):
    """The sandbox infrastructure failed, not the user code."""


def sandbox_env() -> dict[str, str]:
    """Minimal environment for the child: no secrets, no HOME, no extras."""
    return {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(BACKEND_DIR),
    }


def _limit_resources(memory_bytes: int = SANDBOX_MEMORY_BYTES) -> None:
    # Runs in the child before exec (preexec_fn). Caps are named constants
    # in config.py; tuning is one edit.
    resource.setrlimit(resource.RLIMIT_CPU, (SANDBOX_CPU_SECONDS, SANDBOX_CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (SANDBOX_FILE_BYTES, SANDBOX_FILE_BYTES))


def _killed_trace(source: str, language: str, room_id: str, message: str) -> Trace:
    return Trace(
        language=language,
        room_id=room_id,
        source_lines=source.splitlines(),
        steps=[],
        result=TraceResult(status="error", steps_captured=0, error=message),
    )


def run_trace(
    source: str,
    language: str,
    room_id: str = "LOCAL",
    *,
    max_steps: int = MAX_TRACE_STEPS,
    wall_seconds: float = MAX_WALL_SECONDS,
) -> Trace:
    """Run source in the sandbox and return its Trace."""
    if language not in SUPPORTED_LANGUAGES:
        raise SandboxError(f"unsupported language: {language!r}")
    if len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise SandboxError(f"source exceeds {MAX_SOURCE_BYTES} byte cap")

    if language == "python":
        argv = [sys.executable, "-m", "app.sandbox_driver"]
        memory_bytes = SANDBOX_MEMORY_BYTES
    else:
        node = shutil.which("node")
        if node is None:
            raise SandboxError("node runtime is not available for javascript traces")
        # The heap flag is the real memory bound for node; the address-space
        # rlimit just needs to cover V8's virtual reservations (see config).
        argv = [node, f"--max-old-space-size={SANDBOX_NODE_HEAP_MB}", str(JS_DRIVER)]
        memory_bytes = SANDBOX_NODE_MEMORY_BYTES

    # Fresh read-only workdir per run: user code cannot write anywhere and
    # cannot see other runs' files.
    workdir = tempfile.mkdtemp(prefix="trace_sandbox_")
    os.chmod(workdir, 0o555)
    # Snapshot caps ride along so config.py stays the single source of
    # truth; the JS driver has no import path to the Python config.
    request = json.dumps(
        {
            "source": source,
            "room_id": room_id,
            "max_steps": max_steps,
            "wall_seconds": wall_seconds,
            "snapshot_chars": MAX_SNAPSHOT_CHARS,
            "preview_items": SNAPSHOT_PREVIEW_ITEMS,
            "max_stdout_chars": MAX_STDOUT_CHARS,
            "max_stack_frames": MAX_STACK_FRAMES,
        }
    )

    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=workdir,
            env=sandbox_env(),
            preexec_fn=lambda: _limit_resources(memory_bytes),
        )
        try:
            out, err = proc.communicate(request.encode("utf-8"), timeout=wall_seconds)
        except subprocess.TimeoutExpired:
            # The kill path: SIGKILL the runaway child, reap it, and report
            # an error Trace so the UI can render the timeout honestly.
            proc.kill()
            proc.communicate()
            return _killed_trace(
                source, language, room_id, f"execution timed out after {wall_seconds:g} seconds (wall clock)"
            )

        if proc.returncode != 0:
            if proc.returncode < 0:
                # Killed by a signal (e.g. SIGXCPU from the CPU rlimit).
                try:
                    sig = signal.Signals(-proc.returncode).name
                except ValueError:
                    sig = f"signal {-proc.returncode}"
                return _killed_trace(
                    source, language, room_id, f"execution killed by {sig}: sandbox resource limit exceeded"
                )
            raise SandboxError(f"sandbox driver exited with code {proc.returncode}: {err.decode('utf-8', 'replace')[:500]}")

        try:
            return Trace.model_validate_json(out)
        except ValueError as exc:
            raise SandboxError(f"sandbox driver returned invalid trace JSON: {exc}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

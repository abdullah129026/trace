"""One-shot sandbox driver: trace untrusted code, print one Trace JSON.

Spawned by app/sandbox.py with a scrubbed env, rlimit caps, and a
read-only cwd. Never imported by the API process.

Stdout discipline: fd 1 points at /dev/null while user code runs, so even
fd-level writes from user code cannot corrupt the Trace JSON. Afterwards
fd 1 is restored and exactly one JSON document is printed.
"""

import importlib
import json
import os
import sys

from .config import SANDBOX_IMPORT_ALLOWLIST
from .python_tracer import trace_python

# Import everything user code is allowed to use BEFORE the audit hook goes
# up, so allowed imports never open files during the traced run.
for _module_name in sorted(SANDBOX_IMPORT_ALLOWLIST):
    importlib.import_module(_module_name)

_BLOCKED_EVENT_PREFIXES = (
    "os.",
    "socket.",
    "subprocess.",
    "shutil.",
    "signal.",
    "pty.",
    "tempfile.",
    "multiprocessing.",
    "webbrowser.",
    "ctypes.",
)

_hook_armed = False


def _audit_hook(event, _args):
    # Second layer behind the import allowlist: even if user code reaches a
    # dangerous stdlib entry point without importing it (subclass crawling),
    # the call dies here.
    if _hook_armed and (event == "open" or event.startswith(_BLOCKED_EVENT_PREFIXES)):
        raise RuntimeError(f"sandbox: {event} is not allowed")


sys.addaudithook(_audit_hook)


def main() -> None:
    request = json.loads(sys.stdin.read())
    source = request["source"]
    room_id = request.get("room_id", "LOCAL")
    max_steps = int(request.get("max_steps", 2000))

    saved_stdout = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    try:
        global _hook_armed
        _hook_armed = True
        try:
            trace = trace_python(source, room_id=room_id, max_steps=max_steps, restricted=True)
        finally:
            _hook_armed = False
    finally:
        os.dup2(saved_stdout, 1)
        os.close(saved_stdout)
        os.close(devnull)

    sys.stdout.write(trace.model_dump_json())
    sys.stdout.flush()


if __name__ == "__main__":
    main()

"""Behavior tests for the sandboxed execution runner.

Each test names the production behavior that would embarrass us if it
broke: user code runs outside the API process, with capped CPU/memory,
a wall timeout that actually kills, a step cap, and no network, file,
or environment access.
"""

import os
import time

import pytest

from app.sandbox import SandboxError, run_trace, sandbox_env


def test_simple_run_returns_schema_trace():
    trace = run_trace("x = 1\ny = x + 2\n", "python", room_id="LOCAL")
    assert trace.language == "python"
    assert trace.room_id == "LOCAL"
    assert trace.result.status == "ok"
    assert trace.steps[-1].locals["y"] == 3


def test_user_exception_becomes_error_result_not_crash():
    trace = run_trace("x = 1\ny = x / 0\n", "python", room_id="LOCAL")
    assert trace.result.status == "error"
    assert "division by zero" in trace.result.error


def test_step_cap_truncates_through_runner():
    trace = run_trace("while True:\n    pass\n", "python", room_id="LOCAL", max_steps=100)
    assert trace.result.status == "truncated"
    assert trace.result.truncated is True
    assert trace.result.steps_captured == 100


def test_step_limit_survives_user_try_except():
    # The step-cap exception must not be catchable as a normal Exception,
    # or user code could swallow it and spin until the wall timeout.
    src = "try:\n    while True:\n        pass\nexcept Exception:\n    pass\n"
    trace = run_trace(src, "python", room_id="LOCAL", max_steps=100)
    assert trace.result.status == "truncated"
    assert trace.result.steps_captured == 100


def test_wall_timeout_kills_runaway_run():
    start = time.monotonic()
    trace = run_trace("while True:\n    pass\n", "python", room_id="LOCAL", max_steps=10**9, wall_seconds=2)
    elapsed = time.monotonic() - start
    assert trace.result.status == "error"
    assert "timed out" in trace.result.error
    # The kill path must actually fire: the call returns near the timeout,
    # not minutes later, and no child is left spinning.
    assert elapsed < 15


def test_import_of_socket_is_blocked():
    trace = run_trace("import socket\n", "python", room_id="LOCAL")
    assert trace.result.status == "error"
    assert "not allowed" in trace.result.error


def test_import_of_os_is_blocked():
    trace = run_trace("import os\nprint(os.getcwd())\n", "python", room_id="LOCAL")
    assert trace.result.status == "error"
    assert "not allowed" in trace.result.error


def test_open_builtin_is_removed():
    trace = run_trace('open("/etc/passwd").read()\n', "python", room_id="LOCAL")
    assert trace.result.status == "error"
    assert "open" in trace.result.error


def test_allowed_imports_still_work():
    trace = run_trace("import math\nx = math.sqrt(16)\n", "python", room_id="LOCAL")
    assert trace.result.status == "ok"
    assert trace.steps[-1].locals["x"] == 4.0


def test_stdout_captured_from_sandbox():
    trace = run_trace('print("from-sandbox")\n', "python", room_id="LOCAL")
    assert trace.result.status == "ok"
    assert trace.steps[-1].stdout_so_far == "from-sandbox\n"


def test_sandbox_env_is_scrubbed():
    os.environ["TRACE_TEST_SECRET"] = "should-never-leak"
    try:
        env = sandbox_env()
    finally:
        del os.environ["TRACE_TEST_SECRET"]
    assert "TRACE_TEST_SECRET" not in env
    assert env["PATH"] == "/usr/bin:/bin"


def test_unsupported_language_raises():
    with pytest.raises(SandboxError):
        run_trace("x = 1\n", "ruby", room_id="LOCAL")


def test_oversize_source_raises_before_spawn():
    with pytest.raises(SandboxError):
        run_trace("x = 1\n" * 100_000, "python", room_id="LOCAL")


def test_audit_hook_blocks_dangerous_events_when_armed():
    import app.sandbox_driver as driver

    driver._hook_armed = True
    try:
        with pytest.raises(RuntimeError):
            driver._audit_hook("os.system", ())
        with pytest.raises(RuntimeError):
            driver._audit_hook("socket.getaddrinfo", ())
        with pytest.raises(RuntimeError):
            driver._audit_hook("open", ())
        # Harmless events pass through: the hook must not break tracing.
        driver._audit_hook("import", ())
    finally:
        driver._hook_armed = False

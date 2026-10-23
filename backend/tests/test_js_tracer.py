"""Behavior tests for the JavaScript tracer.

Same fixture discipline as the Python tracer: loops, recursion, exceptions,
mutation, stdout, truncation, plus the v1 async rejection. Every test runs
through the real sandbox (node subprocess, acorn instrumentation, vm).
"""

from fastapi.testclient import TestClient

from app.main import app
from app.sandbox import run_trace

client = TestClient(app)
ROOM = "ABCDEF"


def trace_js(source, room_id=ROOM, **kwargs):
    return run_trace(source, "javascript", room_id=room_id, **kwargs)


def line_steps(trace, line):
    return [s for s in trace.steps if s.line == line and s.event == "line"]


def test_loop_captures_line_events_with_locals():
    trace = trace_js("let total = 0;\nfor (let i = 0; i < 3; i++) {\n  total += i;\n}\n")
    assert trace.result.status == "ok"
    assert trace.language == "javascript"
    i_values = [s.locals["i"] for s in line_steps(trace, 3)]
    assert i_values == [0, 1, 2]
    # The final "return" step holds the finished state, like Python's.
    assert trace.steps[-1].event == "return"
    assert trace.steps[-1].locals["total"] == 3


def test_recursion_grows_stack():
    src = "function fact(n) {\n  if (n <= 1) {\n    return 1;\n  }\n  return n * fact(n - 1);\n}\nfact(3);\n"
    trace = trace_js(src)
    assert trace.result.status == "ok"
    deepest = max(s.stack.count("fact") for s in trace.steps)
    assert deepest >= 3


def test_exception_reports_error_with_exception_step():
    trace = trace_js("let x = 1;\nlet y = x / 0;\nthrow new Error('boom');\n")
    assert trace.result.status == "error"
    assert "boom" in trace.result.error
    exc_steps = [s for s in trace.steps if s.event == "exception"]
    assert len(exc_steps) == 1
    assert exc_steps[0].line == 3


def test_mutation_visible_in_snapshots():
    trace = trace_js("const items = [];\nitems.push(1);\nitems.push(2);\n")
    assert trace.result.status == "ok"
    assert line_steps(trace, 2)[-1].locals["items"]["length"] == 0
    assert line_steps(trace, 3)[-1].locals["items"]["length"] == 1
    assert trace.steps[-1].event == "return"
    assert trace.steps[-1].locals["items"]["length"] == 2


def test_async_is_rejected_cleanly():
    trace = trace_js("async function f() {\n  await Promise.resolve(1);\n}\nf();\n")
    assert trace.result.status == "error"
    assert "not supported" in trace.result.error
    assert trace.steps == []


def test_syntax_error_reports_error_without_steps():
    trace = trace_js("function broken( {\n")
    assert trace.result.status == "error"
    assert trace.steps == []
    assert "SyntaxError" in trace.result.error or "Unexpected" in trace.result.error


def test_infinite_loop_truncates_honestly():
    trace = trace_js("while (true) {\n}\n", max_steps=100)
    assert trace.result.status == "truncated"
    assert trace.result.truncated is True
    assert trace.result.steps_captured == 100


def test_stdout_captured_per_step():
    trace = trace_js('console.log("hello");\nconsole.log("world");\n')
    assert trace.result.status == "ok"
    assert line_steps(trace, 1)[-1].stdout_so_far == ""
    assert line_steps(trace, 2)[-1].stdout_so_far == "hello\n"
    assert trace.steps[-1].stdout_so_far == "hello\nworld\n"


def test_require_is_not_available():
    trace = trace_js('const fs = require("fs");\n')
    assert trace.result.status == "error"
    assert "require" in trace.result.error


def test_process_is_not_available():
    trace = trace_js("process.exit(1);\n")
    assert trace.result.status == "error"


def test_unbraced_if_body_keeps_semantics():
    # Instrumentation must not turn `if (x) y();` into `if (x) step(); y();`.
    trace = trace_js("let a = 0;\nlet b = 0;\nif (a === 0) b = 1;\nif (a === 1) b = 2;\n")
    assert trace.result.status == "ok"
    assert trace.steps[-1].locals["b"] == 1


def test_trace_carries_room_id_and_version():
    trace = trace_js("let x = 1;\n", room_id="ROOM42")
    assert trace.room_id == "ROOM42"
    assert trace.language == "javascript"
    assert trace.version == 1


def test_execute_api_serves_javascript():
    resp = client.post("/execute", json={"source": "let x = 40 + 2;\n", "language": "javascript", "room_id": ROOM})
    assert resp.status_code == 200
    trace = resp.json()["trace"]
    assert trace["language"] == "javascript"
    assert trace["result"]["status"] == "ok"
    assert trace["steps"][-1]["locals"]["x"] == 42

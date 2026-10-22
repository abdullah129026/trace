"""Behavior tests for the Python tracer.

Each test names the production behavior that would break if the tracer
regressed: line events, locals, stack, stdout, errors, truncation.
"""

import time

from app.python_tracer import trace_python


def line_steps(trace, line):
    return [s for s in trace.steps if s.line == line and s.event == "line"]


def test_loop_captures_line_events_with_locals():
    trace = trace_python("total = 0\nfor i in range(3):\n    total += i\n", room_id="T1")
    assert trace.result.status == "ok"
    i_values = [s.locals["i"] for s in line_steps(trace, 3)]
    assert i_values == [0, 1, 2]
    assert line_steps(trace, 3)[-1].locals["total"] == 3


def test_recursion_grows_stack():
    src = "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)\n\nfactorial(3)\n"
    trace = trace_python(src, room_id="T1")
    assert trace.result.status == "ok"
    deepest = max(s.stack.count("factorial") for s in trace.steps)
    assert deepest >= 3


def test_exception_reports_error_status():
    trace = trace_python("x = 1\ny = x / 0\n", room_id="T1")
    assert trace.result.status == "error"
    assert "division by zero" in trace.result.error
    assert any(s.event == "exception" for s in trace.steps)


def test_syntax_error_reports_error_without_steps():
    trace = trace_python("def broken(:\n", room_id="T1")
    assert trace.result.status == "error"
    assert trace.steps == []
    assert "SyntaxError" in trace.result.error or "invalid syntax" in trace.result.error


def test_mutation_visible_in_snapshots():
    trace = trace_python("items = []\nitems.append(1)\nitems.append(2)\n", room_id="T1")
    assert trace.result.status == "ok"
    last = line_steps(trace, 3)[-1]
    assert last.locals["items"]["type"] == "list"
    assert last.locals["items"]["length"] == 2


def test_infinite_loop_truncates_honestly():
    trace = trace_python("while True:\n    pass\n", room_id="T1", max_steps=50)
    assert trace.result.status == "truncated"
    assert trace.result.truncated is True
    assert trace.result.steps_captured == 50


def test_stdout_captured_per_step():
    trace = trace_python('print("hello")\nprint("world")\n', room_id="T1")
    assert trace.result.status == "ok"
    assert trace.steps[-1].stdout_so_far == "hello\nworld\n"
    assert line_steps(trace, 1)[-1].stdout_so_far == "hello\n"


def test_steps_only_reference_user_code_lines():
    trace = trace_python("a = 1\nb = 2\nc = a + b\n", room_id="T1")
    assert all(1 <= s.line <= 3 for s in trace.steps)


def test_trace_carries_room_id_and_version():
    trace = trace_python("x = 1\n", room_id="ROOM42")
    assert trace.room_id == "ROOM42"
    assert trace.language == "python"
    assert trace.version == 1
    assert trace.source_lines == ["x = 1"]


def test_thousand_step_run_finishes_quickly():
    src = "x = 0\nfor i in range(400):\n    x += i\n"
    start = time.monotonic()
    trace = trace_python(src, room_id="T1")
    elapsed = time.monotonic() - start
    assert trace.result.status == "ok"
    assert len(trace.steps) > 800
    assert elapsed < 3.0

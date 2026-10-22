"""Contract tests for trace schema v1.

Every trace payload, from either language tracer, must validate against
these models. The version field and room_id are baked in from day one so
schema changes and the Redis upgrade path do not touch routes.
"""

import pytest
from pydantic import ValidationError

from app.trace_schema import Trace, TraceResult, TraceStep, snapshot_value


def _minimal_step(**overrides):
    base = {
        "i": 0,
        "line": 1,
        "event": "line",
        "stack": ["<module>"],
        "locals": {"x": snapshot_value(3)},
        "stdout_so_far": "",
    }
    base.update(overrides)
    return base


def _minimal_trace(**overrides):
    base = {
        "version": 1,
        "language": "python",
        "room_id": "ABC123",
        "source_lines": ["x = 1"],
        "steps": [_minimal_step()],
        "result": {"status": "ok", "steps_captured": 1, "truncated": False},
    }
    base.update(overrides)
    return Trace(**base)


def test_trace_carries_schema_version():
    assert _minimal_trace().version == 1


def test_trace_requires_room_id():
    with pytest.raises(ValidationError):
        Trace(**{k: v for k, v in _minimal_trace().model_dump().items() if k != "room_id"})


def test_language_allowlist_accepts_python_and_javascript():
    assert _minimal_trace(language="python").language == "python"
    assert _minimal_trace(language="javascript").language == "javascript"


def test_language_allowlist_rejects_other_languages():
    with pytest.raises(ValidationError):
        _minimal_trace(language="ruby")


def test_step_event_types():
    for event in ("line", "call", "return", "exception"):
        assert _minimal_step(event=event)["event"] == event
    with pytest.raises(ValidationError):
        TraceStep(**_minimal_step(event="teleport"))


def test_result_status_values():
    for status in ("ok", "error", "truncated"):
        assert TraceResult(status=status, steps_captured=1, truncated=False).status == status
    with pytest.raises(ValidationError):
        TraceResult(status="exploded", steps_captured=1, truncated=False)


def test_error_result_may_carry_message():
    r = TraceResult(status="error", steps_captured=5, truncated=False, error="ZeroDivisionError: division by zero")
    assert "division by zero" in r.error


def test_snapshot_primitives_pass_through():
    assert snapshot_value(3) == 3
    assert snapshot_value(2.5) == 2.5
    assert snapshot_value("hi") == "hi"
    assert snapshot_value(True) is True
    assert snapshot_value(None) is None


def test_snapshot_names_type_on_truncation_marker():
    deep = {"a": {"b": {"c": {"d": 1}}}}
    snap = snapshot_value(deep, max_depth=1)
    assert snap["__trace_truncated__"] is True
    assert "dict" in snap["type"]


def test_snapshot_list_carries_length_and_preview():
    snap = snapshot_value([1, 2, 3, 4, 5, 6, 7], preview_items=3)
    assert snap["type"] == "list"
    assert snap["length"] == 7
    assert snap["preview"] == [1, 2, 3]
    assert snap["__trace_truncated__"] is True


def test_snapshot_long_string_is_truncated_with_marker():
    snap = snapshot_value("x" * 100, max_chars=10)
    assert snap["__trace_truncated__"] is True
    assert len(snap["value"]) <= 10
    assert snap["type"] == "str"


def test_snapshot_is_json_safe():
    import json

    snap = snapshot_value({"weird": object(), "big": list(range(50))}, preview_items=5)
    json.dumps(snap)

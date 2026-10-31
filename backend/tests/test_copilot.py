"""Behavior tests for the AI co-pilot.

Contract under test: the co-pilot explains one selected step from the
trace only (never invented values), cites that step and line, and the
API exposes explain-step and ask-the-trace endpoints over stored traces.
The model call is injected in unit tests; no test needs a Groq key, and
no test asserts anything a stubbed model did not actually return.
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from app import copilot
from app.main import app
from app.trace_schema import Trace, TraceResult, TraceStep

client = TestClient(app)

GOOD_ROOM = "ABCDEF"

# A seeded bug: fetch_user returns None, the next line indexes it.
BUGGY_SRC = "def fetch_user():\n    return None\nuser = fetch_user()\nname = user[\"name\"]\n"


def make_trace() -> Trace:
    return Trace(
        language="python",
        room_id=GOOD_ROOM,
        source_lines=BUGGY_SRC.splitlines(),
        steps=[
            TraceStep(i=0, line=1, event="call", stack=["fetch_user"], locals={}),
            TraceStep(i=1, line=2, event="return", stack=["fetch_user"], locals={}),
            TraceStep(i=2, line=3, event="line", stack=[], locals={"user": None}),
            TraceStep(i=3, line=4, event="exception", stack=[], locals={"user": None}),
        ],
        result=TraceResult(
            status="error",
            steps_captured=4,
            error="TypeError: 'NoneType' object is not subscriptable",
        ),
    )


def test_prompt_contains_only_the_selected_step_and_source():
    messages = copilot.build_explain_prompt(make_trace(), 3)
    user_content = json.loads(messages[-1]["content"])
    assert user_content["step_index"] == 3
    assert user_content["line"] == 4
    assert user_content["source_line"] == 'name = user["name"]'
    assert user_content["locals"] == {"user": None}
    assert user_content["source_lines"] == BUGGY_SRC.splitlines()
    assert user_content["result_error"] == "TypeError: 'NoneType' object is not subscriptable"
    # No other step's locals leak into the prompt.
    assert "fetch_user" not in json.dumps(user_content["locals"])
    assert messages[0]["role"] == "system"
    assert "only" in messages[0]["content"].lower()


def test_prompt_includes_the_question_when_asked():
    messages = copilot.build_explain_prompt(make_trace(), 2, question="Why is user None?")
    user_content = json.loads(messages[-1]["content"])
    assert user_content["question"] == "Why is user None?"


def test_explain_rejects_out_of_range_step():
    trace = make_trace()
    with pytest.raises(ValueError):
        copilot.explain_step(trace, 99)
    with pytest.raises(ValueError):
        copilot.explain_step(trace, -1)


def test_explain_rejects_oversize_question():
    with pytest.raises(ValueError):
        copilot.explain_step(make_trace(), 2, question="x" * 10_001)


def test_explain_without_groq_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(copilot.CopilotUnavailable):
        copilot.explain_step(make_trace(), 2)


def test_explain_with_fake_model_cites_step_and_line():
    seen = {}

    def fake_model(messages):
        seen["messages"] = messages
        return "user is None here, so indexing it fails."

    result = copilot.explain_step(make_trace(), 3, call_model=fake_model)
    assert "Step 3" in result
    assert "line 4" in result
    prompt_locals = json.loads(seen["messages"][-1]["content"])["locals"]
    assert prompt_locals == {"user": None}


def _execute_buggy_trace() -> str:
    resp = client.post(
        "/execute",
        json={"source": BUGGY_SRC, "language": "python", "room_id": GOOD_ROOM},
    )
    assert resp.status_code == 200
    return resp.json()["trace_id"]


def test_explain_endpoint_returns_cited_explanation(monkeypatch):
    trace_id = _execute_buggy_trace()
    stored = client.get(f"/traces/{trace_id}").json()
    bug_step = next(
        s["i"]
        for s in stored["steps"]
        if "user" in s["locals"] and s["locals"]["user"] is None
    )

    def fake_explain(trace, step_index, question=None):
        assert step_index == bug_step
        return f"Step {bug_step} (line {trace.steps[bug_step].line}): user is None here."

    monkeypatch.setattr(copilot, "explain_step", fake_explain)
    resp = client.post(
        "/explain", json={"trace_id": trace_id, "step_index": bug_step}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["trace_id"] == trace_id
    assert body["step_index"] == bug_step
    assert f"Step {bug_step}" in body["explanation"]
    assert body["line"] == stored["steps"][bug_step]["line"]


def test_ask_endpoint_requires_a_question(monkeypatch):
    trace_id = _execute_buggy_trace()
    resp = client.post("/ask", json={"trace_id": trace_id, "step_index": 0})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_ask_endpoint_passes_question_to_copilot(monkeypatch):
    trace_id = _execute_buggy_trace()
    seen = {}

    def fake_explain(trace, step_index, question=None):
        seen["question"] = question
        return f"Step {step_index} (line 1): answer."

    monkeypatch.setattr(copilot, "explain_step", fake_explain)
    resp = client.post(
        "/ask",
        json={"trace_id": trace_id, "step_index": 0, "question": "What happened here?"},
    )
    assert resp.status_code == 200
    assert seen["question"] == "What happened here?"
    assert resp.json()["explanation"].startswith("Step 0")


def test_explain_endpoint_404_for_unknown_trace(monkeypatch):
    monkeypatch.setattr(copilot, "explain_step", lambda *a, **k: "Step 0 (line 1): x.")
    resp = client.post("/explain", json={"trace_id": "0" * 32, "step_index": 0})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_explain_endpoint_400_for_out_of_range_step(monkeypatch):
    trace_id = _execute_buggy_trace()
    monkeypatch.setattr(copilot, "explain_step", lambda *a, **k: "Step 0 (line 1): x.")
    resp = client.post("/explain", json={"trace_id": trace_id, "step_index": 999})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_explain_endpoint_503_when_copilot_unavailable(monkeypatch):
    trace_id = _execute_buggy_trace()

    def unavailable(*a, **k):
        raise copilot.CopilotUnavailable("Groq key not configured")

    monkeypatch.setattr(copilot, "explain_step", unavailable)
    resp = client.post("/explain", json={"trace_id": trace_id, "step_index": 0})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "copilot_unavailable"


def test_explain_endpoint_504_on_model_timeout(monkeypatch):
    trace_id = _execute_buggy_trace()

    def timeout(*a, **k):
        raise copilot.CopilotTimeout("model did not answer in time")

    monkeypatch.setattr(copilot, "explain_step", timeout)
    resp = client.post("/explain", json={"trace_id": trace_id, "step_index": 0})
    assert resp.status_code == 504
    assert resp.json()["error"]["code"] == "copilot_timeout"


def test_seeded_bug_step_is_the_none_assignment():
    """The seeded bug's first None step is where the explanation must point.

    This pins the fixture itself: the trace really does show user turning
    None at the fetch_user assignment, so a future tracer regression that
    moves or drops that step fails here, not in front of a user.
    """
    trace_id = _execute_buggy_trace()
    stored = client.get(f"/traces/{trace_id}").json()
    assert stored["result"]["status"] == "error"
    assert "NoneType" in (stored["result"]["error"] or "")
    bug_steps = [
        s for s in stored["steps"] if "user" in s["locals"] and s["locals"]["user"] is None
    ]
    assert bug_steps, "no step shows user as None"
    # settrace fires before a line executes, so the assignment on line 3
    # only becomes visible in locals on the next line event, line 4, which
    # is also the line that indexes the None value.
    assert bug_steps[0]["line"] == 4
    assert bug_steps[0]["locals"]["user"] is None
    # The failing line really does index that same variable.
    assert 'user["name"]' in stored["source_lines"][3]

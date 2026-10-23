"""Behavior tests for the execution API.

Contract under test: POST /execute runs code in the sandbox and stores the
trace; GET /traces/{id} fetches it; every failure uses the same error
shape {"error": {"code", "message"}}; /execute is rate-limited per IP.
"""

import time
from collections import deque

from fastapi.testclient import TestClient

from app import rate_limit
from app.main import app

client = TestClient(app)

GOOD_ROOM = "ABCDEF"
PYTHON_SRC = "x = 1\ny = x + 2\n"


def execute(source=PYTHON_SRC, language="python", room_id=GOOD_ROOM):
    return client.post("/execute", json={"source": source, "language": language, "room_id": room_id})


def test_execute_python_returns_trace_with_id():
    resp = execute()
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["trace_id"]) == 32
    trace = body["trace"]
    assert trace["language"] == "python"
    assert trace["room_id"] == GOOD_ROOM
    assert trace["result"]["status"] == "ok"
    assert trace["steps"][-1]["locals"]["y"] == 3


def test_execute_stores_trace_for_later_fetch():
    trace_id = execute().json()["trace_id"]
    resp = client.get(f"/traces/{trace_id}")
    assert resp.status_code == 200
    assert resp.json()["steps"][-1]["locals"]["y"] == 3


def test_fetch_unknown_trace_id_is_404_with_error_shape():
    resp = client.get("/traces/" + "0" * 32)
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    assert resp.json()["error"]["message"]


def test_execute_rejects_unknown_language():
    resp = execute(language="ruby")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_execute_rejects_bad_room_code():
    resp = execute(room_id="nope!")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_execute_rejects_empty_source():
    resp = execute(source="   ")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_execute_rejects_oversize_source():
    resp = execute(source="x = 1\n" * 20_000)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "validation_error"


def test_execute_user_error_is_trace_result_not_api_error():
    resp = execute(source="x = 1\ny = x / 0\n")
    assert resp.status_code == 200
    trace = resp.json()["trace"]
    assert trace["result"]["status"] == "error"
    assert "division by zero" in trace["result"]["error"]


def test_rate_limiter_blocks_when_bucket_full():
    rate_limit._hits["testclient"] = deque([time.monotonic()] * 20)
    try:
        resp = execute()
    finally:
        rate_limit.reset_rate_limiter()
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"


def test_rate_limiter_allows_under_limit():
    assert rate_limit.check_rate_limit("10.0.0.1") is True
    rate_limit.reset_rate_limiter()


def test_health_still_ok():
    assert client.get("/health").json() == {"status": "ok"}

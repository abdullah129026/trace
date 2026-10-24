"""Behavior tests for rooms, the room event socket, and the Yjs relay.

Contract under test:
- POST /rooms mints a room with a server-generated code.
- GET /rooms/{code} reports members and the latest trace; unknown codes 404.
- WS /rooms/{code}/events pushes member join/leave and trace events so a
  shared run reaches every member of the room.
- POST /execute with a room code broadcasts the finished trace to the room.
- WS /yjs/{code} is the collaborative editing relay; bad codes are rejected.
"""

import re
import time
from collections import deque

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import rate_limit, room_events, rooms
from app.config import ROOM_CODE_ALPHABET, ROOM_CODE_LENGTH
from app.main import app

CODE_RE = re.compile(f"^[{ROOM_CODE_ALPHABET}]{{{ROOM_CODE_LENGTH}}}$")
PYTHON_SRC = "x = 1\ny = x + 2\n"


@pytest.fixture(autouse=True)
def clean_state():
    rooms.reset()
    rate_limit.reset_rate_limiter()
    room_events.reset()
    yield
    rooms.reset()
    rate_limit.reset_rate_limiter()
    room_events.reset()


def make_room(client) -> str:
    resp = client.post("/rooms")
    assert resp.status_code == 200
    return resp.json()["code"]


def test_create_room_returns_well_formed_code():
    with TestClient(app) as client:
        code = make_room(client)
        assert CODE_RE.match(code), f"bad room code: {code!r}"


def test_create_room_mints_distinct_codes():
    with TestClient(app) as client:
        codes = {make_room(client) for _ in range(5)}
        assert len(codes) == 5


def test_get_room_reports_empty_new_room():
    with TestClient(app) as client:
        code = make_room(client)
        resp = client.get(f"/rooms/{code}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == code
        assert body["members"] == 0
        assert body["last_trace_id"] is None


def test_get_room_rejects_malformed_code():
    with TestClient(app) as client:
        resp = client.get("/rooms/nope!")
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "validation_error"


def test_get_unknown_room_is_404_with_error_shape():
    with TestClient(app) as client:
        resp = client.get("/rooms/ZZZZZZ")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


def test_create_room_rate_limiter_blocks_when_bucket_full():
    with TestClient(app) as client:
        rate_limit._room_hits["testclient"] = deque([time.monotonic()] * 30)
        resp = client.post("/rooms")
        assert resp.status_code == 429
        assert resp.json()["error"]["code"] == "rate_limited"


def test_event_socket_hello_reports_member_count():
    with TestClient(app) as client:
        code = make_room(client)
        with client.websocket_connect(f"/rooms/{code}/events") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "hello"
            assert hello["members"] == 1
            assert hello["last_trace_id"] is None


def test_event_socket_broadcasts_join_and_leave():
    with TestClient(app) as client:
        code = make_room(client)
        with client.websocket_connect(f"/rooms/{code}/events") as ws1:
            assert ws1.receive_json()["members"] == 1
            with client.websocket_connect(f"/rooms/{code}/events") as ws2:
                assert ws2.receive_json()["members"] == 2
                joined = ws1.receive_json()
                assert joined == {"type": "member_joined", "members": 2}
            left = ws1.receive_json()
            assert left == {"type": "member_left", "members": 1}


def test_event_socket_to_unknown_room_is_refused():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/rooms/ZZZZZZ/events"):
                pass


def test_execute_broadcasts_trace_to_room_members():
    with TestClient(app) as client:
        code = make_room(client)
        with client.websocket_connect(f"/rooms/{code}/events") as ws:
            ws.receive_json()  # hello
            resp = client.post(
                "/execute",
                json={"source": PYTHON_SRC, "language": "python", "room_id": code},
            )
            assert resp.status_code == 200
            trace_id = resp.json()["trace_id"]
            event = ws.receive_json()
            assert event["type"] == "trace"
            assert event["trace_id"] == trace_id
            assert event["summary"]["language"] == "python"
            assert event["summary"]["status"] == "ok"
            assert event["summary"]["steps_captured"] > 0
        info = client.get(f"/rooms/{code}").json()
        assert info["last_trace_id"] == trace_id


def test_execute_without_a_room_still_runs_standalone():
    # Day 2 behavior preserved: room_id is a label; broadcast only happens
    # when the room actually exists.
    with TestClient(app) as client:
        resp = client.post(
            "/execute",
            json={"source": PYTHON_SRC, "language": "python", "room_id": "QWERTY"},
        )
        assert resp.status_code == 200
        assert resp.json()["trace"]["result"]["status"] == "ok"


def test_yjs_relay_rejects_malformed_code():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/yjs/nope"):
                pass


def test_yjs_relay_rejects_unknown_room():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/yjs/ZZZZZZ"):
                pass

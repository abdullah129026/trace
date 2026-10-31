"""FastAPI application entrypoint: health, rooms, execution API, trace fetch.

The Yjs collaboration relay (pycrdt-websocket, ADR-003) is mounted as a raw
ASGI app at /yjs/{code}; the room event socket at /rooms/{code}/events
carries member join/leave and finished-trace broadcasts.
"""

import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pycrdt.websocket import ASGIServer, WebsocketServer
from pydantic import BaseModel, field_validator
from starlette.concurrency import run_in_threadpool

from . import __version__, copilot, rate_limit, room_events, rooms, store
from .config import MAX_QUESTION_CHARS, MAX_SOURCE_BYTES, ROOM_CODE_ALPHABET, ROOM_CODE_LENGTH, SUPPORTED_LANGUAGES
from .sandbox import SandboxError, run_trace

log = logging.getLogger("trace.api")

ROOM_CODE_RE = re.compile(f"^[{ROOM_CODE_ALPHABET}]{{{ROOM_CODE_LENGTH}}}$")

_yjs_server = WebsocketServer()
_yjs_asgi = ASGIServer(_yjs_server)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with _yjs_server:
        yield


app = FastAPI(title="Trace API", version=__version__, lifespan=lifespan)

# The frontend is served from a different origin (Vercel) than the API
# (Render), so the browser needs CORS. The API is public by design in v1:
# rooms are joined by code, there are no accounts, and /execute is
# rate-limited per IP. No credentials are used, so a wildcard origin is
# the honest v1 setting.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def yjs_relay_app(scope, receive, send):
    """Raw ASGI mount for the Yjs sync protocol.

    Mounted at /yjs, so the room code arrives as the remaining path. Only
    well-formed codes for existing rooms are admitted; anything else gets a
    closed socket instead of a relay.
    """
    if scope["type"] != "websocket":
        await send(
            {
                "type": "http.response.start",
                "status": 404,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b'{"error":{"code":"not_found","message":"not found"}}',
            }
        )
        return
    route_path = scope["path"]
    root = scope.get("root_path") or ""
    if root and route_path.startswith(root):
        route_path = route_path[len(root):]
    code = route_path.strip("/")
    if "/" in code or not ROOM_CODE_RE.match(code):
        await send({"type": "websocket.close", "code": 4400})
        return
    if rooms.get(code) is None:
        await send({"type": "websocket.close", "code": 4404})
        return
    await _yjs_asgi(dict(scope, path=code), receive, send)


app.mount("/yjs", yjs_relay_app)


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # One consistent error shape for every 400, instead of FastAPI's
    # default 422 detail array.
    first = exc.errors()[0] if exc.errors() else {}
    return error_response(400, "validation_error", f"invalid request: {first.get('msg', 'validation failed')}")


def _validate_room_code(value: str, field: str) -> str:
    if not ROOM_CODE_RE.match(value):
        raise ValueError(f"{field} must be {ROOM_CODE_LENGTH} chars from {ROOM_CODE_ALPHABET}")
    return value


class ExecuteRequest(BaseModel):
    source: str
    language: str
    room_id: str

    @field_validator("source")
    @classmethod
    def source_non_empty_and_bounded(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source must not be empty")
        if len(value.encode("utf-8")) > MAX_SOURCE_BYTES:
            raise ValueError(f"source exceeds {MAX_SOURCE_BYTES} byte cap")
        return value

    @field_validator("language")
    @classmethod
    def language_supported(cls, value: str) -> str:
        if value not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported language: {value!r} (supported: {', '.join(SUPPORTED_LANGUAGES)})")
        return value

    @field_validator("room_id")
    @classmethod
    def room_id_well_formed(cls, value: str) -> str:
        return _validate_room_code(value, "room_id")


class CopilotRequest(BaseModel):
    trace_id: str
    step_index: int
    question: str | None = None

    @field_validator("question")
    @classmethod
    def question_bounded(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > MAX_QUESTION_CHARS:
            raise ValueError(f"question exceeds {MAX_QUESTION_CHARS} character cap")
        return value


class AskRequest(CopilotRequest):
    question: str

    @field_validator("question")
    @classmethod
    def question_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must not be empty")
        if len(value) > MAX_QUESTION_CHARS:
            raise ValueError(f"question exceeds {MAX_QUESTION_CHARS} character cap")
        return value


async def _explain(body: CopilotRequest, request: Request) -> dict:
    trace = store.load_trace(body.trace_id)
    if trace is None:
        return error_response(404, "not_found", f"no trace with id {body.trace_id!r}")
    if body.step_index < 0 or body.step_index >= len(trace.steps):
        return error_response(400, "validation_error", f"step_index {body.step_index} out of range")
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limit.check_copilot_rate_limit(client_ip):
        return error_response(429, "rate_limited", "too many co-pilot requests; slow down and try again")
    try:
        # The model call blocks; keep it off the event loop.
        explanation = await run_in_threadpool(
            copilot.explain_step, trace, body.step_index, body.question
        )
    except ValueError as exc:
        return error_response(400, "validation_error", f"invalid request: {exc}")
    except copilot.CopilotTimeout:
        return error_response(504, "copilot_timeout", "the co-pilot did not answer in time; try again")
    except copilot.CopilotUnavailable:
        return error_response(
            503, "copilot_unavailable", "the co-pilot is not available right now; try again later"
        )
    # Log counts only: never the question, the trace, or the explanation.
    log.info("explained trace=%s step=%d", body.trace_id, body.step_index)
    step = trace.steps[body.step_index]
    return {
        "trace_id": body.trace_id,
        "step_index": body.step_index,
        "line": step.line,
        "explanation": explanation,
    }


@app.post("/explain")
async def explain(body: CopilotRequest, request: Request) -> dict:
    return await _explain(body, request)


@app.post("/ask")
async def ask(body: AskRequest, request: Request) -> dict:
    return await _explain(body, request)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/rooms")
def create_room(request: Request) -> dict:
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limit.check_room_create_rate_limit(client_ip):
        return error_response(429, "rate_limited", "too many room creations; slow down and try again")
    room = rooms.create()
    log.info("room created code=%s", room.code)
    return {"code": room.code}


@app.get("/rooms/{code}")
def get_room(code: str) -> dict:
    try:
        _validate_room_code(code, "code")
    except ValueError as exc:
        return error_response(400, "validation_error", f"invalid request: {exc}")
    room = rooms.get(code)
    if room is None:
        return error_response(404, "not_found", f"no room with code {code!r}")
    return {
        "code": room.code,
        "members": room_events.member_count(code),
        "last_trace_id": room.last_trace_id,
    }


@app.websocket("/rooms/{code}/events")
async def room_events_socket(websocket: WebSocket, code: str):
    if not ROOM_CODE_RE.match(code) or rooms.get(code) is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    members = room_events.subscribe(code, websocket)
    await websocket.send_json(
        {
            "type": "hello",
            "members": members,
            "last_trace_id": rooms.get(code).last_trace_id if rooms.get(code) else None,
        }
    )
    await room_events.broadcast(code, {"type": "member_joined", "members": members}, exclude=websocket)
    try:
        while True:
            # The socket is server-push only in v1; we read to notice the
            # disconnect. Incoming payloads are ignored.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        members = room_events.unsubscribe(code, websocket)
        await room_events.broadcast(code, {"type": "member_left", "members": members}, exclude=websocket)


@app.post("/execute")
async def execute(body: ExecuteRequest, request: Request) -> dict:
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limit.check_rate_limit(client_ip):
        return error_response(429, "rate_limited", "too many execution requests; slow down and try again")
    try:
        # run_trace blocks on the sandbox subprocess; keep it off the loop.
        trace = await run_in_threadpool(run_trace, body.source, body.language, body.room_id)
    except SandboxError as exc:
        # Infrastructure failure, not user code: generic message to the
        # client, detail in the server log (which never carries user code).
        log.warning("sandbox failure language=%s room=%s detail=%s", body.language, body.room_id, exc)
        return error_response(500, "sandbox_failure", "execution failed inside the sandbox; try again")
    trace_id = store.save_trace(trace)
    # Structured log, counts only: user code contents are never logged.
    log.info(
        "executed language=%s room=%s status=%s steps=%d",
        trace.language,
        trace.room_id,
        trace.result.status,
        trace.result.steps_captured,
    )
    room = rooms.get(body.room_id)
    if room is not None:
        room.last_trace_id = trace_id
        await room_events.broadcast(
            body.room_id,
            {
                "type": "trace",
                "trace_id": trace_id,
                "summary": {
                    "language": trace.language,
                    "status": trace.result.status,
                    "steps_captured": trace.result.steps_captured,
                    "truncated": trace.result.truncated,
                },
            },
        )
    return {"trace_id": trace_id, "trace": trace.model_dump()}


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str):
    trace = store.load_trace(trace_id)
    if trace is None:
        return error_response(404, "not_found", f"no trace with id {trace_id!r}")
    return trace.model_dump()

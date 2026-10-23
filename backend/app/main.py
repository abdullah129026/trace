"""FastAPI application entrypoint: health, execution API, trace fetch."""

import logging
import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from . import __version__, rate_limit, store
from .config import MAX_SOURCE_BYTES, ROOM_CODE_ALPHABET, ROOM_CODE_LENGTH, SUPPORTED_LANGUAGES
from .sandbox import SandboxError, run_trace

log = logging.getLogger("trace.api")

ROOM_CODE_RE = re.compile(f"^[{ROOM_CODE_ALPHABET}]{{{ROOM_CODE_LENGTH}}}$")

app = FastAPI(title="Trace API", version=__version__)


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # One consistent error shape for every 400, instead of FastAPI's
    # default 422 detail array.
    first = exc.errors()[0] if exc.errors() else {}
    return error_response(400, "validation_error", f"invalid request: {first.get('msg', 'validation failed')}")


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
        if not ROOM_CODE_RE.match(value):
            raise ValueError(f"room_id must be {ROOM_CODE_LENGTH} chars from {ROOM_CODE_ALPHABET}")
        return value


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/execute")
def execute(body: ExecuteRequest, request: Request) -> dict:
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limit.check_rate_limit(client_ip):
        return error_response(429, "rate_limited", "too many execution requests; slow down and try again")
    try:
        trace = run_trace(body.source, body.language, room_id=body.room_id)
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
    return {"trace_id": trace_id, "trace": trace.model_dump()}


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str):
    trace = store.load_trace(trace_id)
    if trace is None:
        return error_response(404, "not_found", f"no trace with id {trace_id!r}")
    return trace.model_dump()

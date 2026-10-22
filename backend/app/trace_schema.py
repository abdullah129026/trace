"""Trace schema v1. The single contract both language tracers must satisfy.

Snapshots are JSON-safe values with explicit truncation markers, never
silent drops: a truncated value always carries "__trace_truncated__": True
and names its type.
"""

from typing import Any, Literal

from pydantic import BaseModel

from .config import SUPPORTED_LANGUAGES

SCHEMA_VERSION = 1

TRUNCATED_KEY = "__trace_truncated__"

_CONTAINERS = (dict, list, tuple, set, frozenset)


def snapshot_value(
    value: Any,
    *,
    max_chars: int = 2_000,
    preview_items: int = 5,
    max_depth: int = 3,
    _depth: int = 0,
    _seen: frozenset[int] | None = None,
) -> Any:
    """Convert an arbitrary Python value into a JSON-safe snapshot.

    Primitives pass through. Containers become a summary with type, length
    and a shallow preview. Anything deeper than max_depth, or cut off by
    the preview/size caps, becomes a truncation marker that names its type.
    """
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and abs(value) != float("inf") else repr(value)
    if isinstance(value, str):
        if len(value) <= max_chars:
            return value
        return {"type": "str", "value": value[:max_chars], TRUNCATED_KEY: True}

    seen = _seen or frozenset()
    if isinstance(value, _CONTAINERS):
        if id(value) in seen:
            return {"type": type(value).__name__, TRUNCATED_KEY: True, "circular": True}
        if _depth >= max_depth:
            return {"type": type(value).__name__, TRUNCATED_KEY: True}
        seen = seen | {id(value)}

    def child(v: Any) -> Any:
        return snapshot_value(v, max_chars=max_chars, preview_items=preview_items, max_depth=max_depth, _depth=_depth + 1, _seen=seen)

    def cut(v: Any) -> bool:
        return isinstance(v, dict) and v.get(TRUNCATED_KEY) is True

    if isinstance(value, dict):
        preview = {str(k): child(v) for k, v in list(value.items())[:preview_items]}
        return {
            "type": "dict",
            "length": len(value),
            "preview": preview,
            TRUNCATED_KEY: len(value) > preview_items or any(cut(v) for v in preview.values()),
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        preview = [child(v) for v in list(value)[:preview_items]]
        return {
            "type": type(value).__name__,
            "length": len(value),
            "preview": preview,
            TRUNCATED_KEY: len(value) > preview_items or any(cut(v) for v in preview),
        }

    text = repr(value)
    if len(text) > max_chars:
        return {"type": type(value).__name__, "repr": text[:max_chars], TRUNCATED_KEY: True}
    return {"type": type(value).__name__, "repr": text, TRUNCATED_KEY: False}


class TraceStep(BaseModel):
    i: int
    line: int
    event: Literal["line", "call", "return", "exception"] = "line"
    stack: list[str] = []
    locals: dict[str, Any] = {}
    stdout_so_far: str = ""


class TraceResult(BaseModel):
    status: Literal["ok", "error", "truncated"]
    steps_captured: int
    truncated: bool = False
    error: str | None = None


class Trace(BaseModel):
    version: Literal[1] = SCHEMA_VERSION
    language: str
    room_id: str
    source_lines: list[str]
    steps: list[TraceStep]
    result: TraceResult

    def model_post_init(self, __context: Any) -> None:
        if self.language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"unsupported language: {self.language!r}")

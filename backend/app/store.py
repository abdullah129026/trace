"""In-memory trace store (LRU).

Deliberate v1 simplification: no database, traces live for the session.
The room-store interface coming on Day 3 is the upgrade path to
Redis/Postgres. The cap is a named constant in config.py.
"""

import uuid
from collections import OrderedDict

from .config import TRACE_STORE_CAP
from .trace_schema import Trace

_store: OrderedDict[str, Trace] = {}


def save_trace(trace: Trace) -> str:
    """Store a trace, evicting the oldest when over cap. Returns its id."""
    trace_id = uuid.uuid4().hex
    _store[trace_id] = trace
    while len(_store) > TRACE_STORE_CAP:
        _store.popitem(last=False)
    return trace_id


def load_trace(trace_id: str) -> Trace | None:
    return _store.get(trace_id)


def reset_store() -> None:
    """Test helper: empty the store."""
    _store.clear()

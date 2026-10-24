"""Room registry: a small RoomStore interface with an in-memory v1 backend.

Rooms are created explicitly (POST /rooms) and live for the session; the
oldest are evicted past ROOM_STORE_CAP. This is the deliberate v1
simplification from the build prompt: the interface is the upgrade path to
Redis/Postgres, the in-memory class is the implementation.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from .config import ROOM_CODE_ALPHABET, ROOM_CODE_LENGTH, ROOM_STORE_CAP


@dataclass
class Room:
    code: str
    created_at: float
    last_trace_id: str | None = None


class RoomStore(Protocol):
    def create(self) -> Room: ...
    def get(self, code: str) -> Room | None: ...
    def reset(self) -> None: ...


class InMemoryRoomStore:
    """Thread-safe in-memory rooms. Evicts oldest-first past the cap."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rooms: dict[str, Room] = {}

    def create(self) -> Room:
        with self._lock:
            for _ in range(10):
                code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))
                if code not in self._rooms:
                    break
            else:
                raise RuntimeError("room code space exhausted")
            room = Room(code=code, created_at=time.time())
            self._rooms[code] = room
            while len(self._rooms) > ROOM_STORE_CAP:
                oldest = min(self._rooms.values(), key=lambda r: r.created_at)
                del self._rooms[oldest.code]
            return room

    def get(self, code: str) -> Room | None:
        with self._lock:
            return self._rooms.get(code)

    def reset(self) -> None:
        """Test helper: empty the registry."""
        with self._lock:
            self._rooms.clear()


_store: RoomStore = InMemoryRoomStore()


def create() -> Room:
    return _store.create()


def get(code: str) -> Room | None:
    return _store.get(code)


def reset() -> None:
    _store.reset()

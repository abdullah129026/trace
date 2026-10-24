"""Per-room WebSocket fan-out for member and trace events.

Single process, one registry. Subscribe/unsubscribe are synchronous and take
a threading lock (nothing awaited inside); broadcast snapshots the socket set
under the lock and sends outside it. Dead sockets are pruned when a send
fails and on disconnect, so the member count never drifts.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from starlette.websockets import WebSocket

log = logging.getLogger("trace.room_events")

_lock = threading.Lock()
_subscribers: dict[str, set[WebSocket]] = {}


def subscribe(code: str, ws: WebSocket) -> int:
    """Add ws to the room's fan-out set. Returns the new member count."""
    with _lock:
        members = _subscribers.setdefault(code, set())
        members.add(ws)
        return len(members)


def unsubscribe(code: str, ws: WebSocket) -> int:
    """Remove ws from the room's fan-out set. Returns the new member count."""
    with _lock:
        members = _subscribers.get(code)
        if members is None:
            return 0
        members.discard(ws)
        if not members:
            del _subscribers[code]
            return 0
        return len(members)


def member_count(code: str) -> int:
    with _lock:
        members = _subscribers.get(code)
        return len(members) if members else 0


async def broadcast(code: str, message: dict[str, Any], exclude: WebSocket | None = None) -> None:
    """Send message to every socket in the room; prune dead ones.

    exclude skips one socket, used for join/leave notices where the subject
    already learned its own state from the hello message.
    """
    with _lock:
        targets = [ws for ws in _subscribers.get(code, ()) if ws is not exclude]
    for ws in targets:
        try:
            await ws.send_json(message)
        except Exception:
            # Socket died without a clean disconnect; drop it so the
            # member count stays honest. Never logs user data: message
            # carries trace ids and counts only.
            log.debug("pruning dead event socket in room %s", code)
            unsubscribe(code, ws)


def reset() -> None:
    """Test helper: drop every subscription."""
    with _lock:
        _subscribers.clear()

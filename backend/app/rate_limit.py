"""In-memory per-IP sliding-window rate limiter for /execute.

v1 keeps this in the process (one instance, no sticky sessions yet). The
limits are named constants in config.py. Day 6 verifies the deployed
behavior; the Redis hook from the prompt replaces this at 10x.
"""

import time
from collections import deque

from . import config

_hits: dict[str, deque[float]] = {}
_room_hits: dict[str, deque[float]] = {}
_copilot_hits: dict[str, deque[float]] = {}


def _check(ip: str, limit: int, buckets: dict[str, deque[float]]) -> bool:
    """Record a hit for ip in buckets. Returns True when allowed."""
    now = time.monotonic()
    window = config.RATE_LIMIT_WINDOW_SECONDS
    bucket = buckets.setdefault(ip, deque())
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def check_rate_limit(ip: str) -> bool:
    """Record an /execute hit for ip. Returns True when allowed."""
    return _check(ip, config.RATE_LIMIT_EXECUTE_PER_MINUTE, _hits)


def check_room_create_rate_limit(ip: str) -> bool:
    """Record a POST /rooms hit for ip. Returns True when allowed."""
    return _check(ip, config.RATE_LIMIT_ROOM_CREATE_PER_MINUTE, _room_hits)


def check_copilot_rate_limit(ip: str) -> bool:
    """Record a co-pilot (/explain, /ask) hit for ip. Returns True when allowed."""
    return _check(ip, config.RATE_LIMIT_COPILOT_PER_MINUTE, _copilot_hits)


def reset_rate_limiter() -> None:
    """Test helper: clear all buckets."""
    _hits.clear()
    _room_hits.clear()
    _copilot_hits.clear()

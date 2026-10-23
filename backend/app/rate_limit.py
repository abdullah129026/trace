"""In-memory per-IP sliding-window rate limiter for /execute.

v1 keeps this in the process (one instance, no sticky sessions yet). The
limits are named constants in config.py. Day 6 verifies the deployed
behavior; the Redis hook from the prompt replaces this at 10x.
"""

import time
from collections import deque

from . import config

_hits: dict[str, deque[float]] = {}


def check_rate_limit(ip: str) -> bool:
    """Record a hit for ip. Returns True when the request is allowed."""
    now = time.monotonic()
    window = config.RATE_LIMIT_WINDOW_SECONDS
    bucket = _hits.setdefault(ip, deque())
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= config.RATE_LIMIT_EXECUTE_PER_MINUTE:
        return False
    bucket.append(now)
    return True


def reset_rate_limiter() -> None:
    """Test helper: clear all buckets."""
    _hits.clear()

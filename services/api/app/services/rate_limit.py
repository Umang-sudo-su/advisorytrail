"""Small in-memory rate limiter for the endpoints attackers probe most.

One API process keeps its own counters. That is deliberate: the deployment runs a
single API container, and a shared store would be a new dependency.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, List

from fastapi import HTTPException, status

_BUCKETS: Dict[str, List[float]] = {}
_LOCK = threading.Lock()
_MAX_BUCKETS = 20_000


def enforce(key: str, limit: int, window_seconds: int, detail: str | None = None) -> None:
    """Raises HTTP 429 once ``key`` exceeds ``limit`` hits inside the window."""
    now = time.monotonic()

    with _LOCK:
        stamps = [stamp for stamp in _BUCKETS.get(key, []) if now - stamp < window_seconds]

        if len(stamps) >= limit:
            retry_after = max(1, int(window_seconds - (now - stamps[0])) + 1)
            _BUCKETS[key] = stamps
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail or f"Too many requests. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        stamps.append(now)
        _BUCKETS[key] = stamps

        # Keep memory bounded if an attacker cycles through many keys.
        if len(_BUCKETS) > _MAX_BUCKETS:
            for stale in [item for item, values in _BUCKETS.items() if not values or now - values[-1] > window_seconds]:
                _BUCKETS.pop(stale, None)


def reset() -> None:
    """Clears every bucket. Used by tests."""
    with _LOCK:
        _BUCKETS.clear()

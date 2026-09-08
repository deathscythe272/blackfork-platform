"""A per-identity rate limit at the door (T1-GW-05).

A looping agent must not be able to flood the gateway, and one agent's flood must not
slow another. Each identity gets its own bucket: GATEWAY_RATE_LIMIT calls per
GATEWAY_RATE_WINDOW_SECONDS (default 120 per 60 s), refilled continuously. A call over
the limit is refused before policy runs, and refused calls are audited like any other
deny so the flood itself is on the record.

The buckets live in the gateway process. With one instance, which is how the gateway
runs today, that is the whole picture; a second instance would need a shared store,
and the page says so. Serves: BR-7, BR-8.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


@dataclass
class Verdict:
    allowed: bool
    remaining: int
    retry_after_s: float = 0.0


class Limiter:
    def __init__(self, limit: int, window_s: float):
        if limit < 1 or window_s <= 0:
            raise ValueError("limit must be at least 1 and the window positive")
        self.limit = limit
        self.window_s = window_s
        self._rate = limit / window_s  # tokens per second
        self._buckets: dict[str, tuple[float, float]] = {}  # identity -> (tokens, last refill time)
        self._lock = threading.Lock()

    def check(self, identity: str, now: float | None = None) -> Verdict:
        now = time.monotonic() if now is None else now
        with self._lock:
            tokens, last = self._buckets.get(identity, (float(self.limit), now))
            tokens = min(float(self.limit), tokens + (now - last) * self._rate)
            if tokens >= 1.0:
                self._buckets[identity] = (tokens - 1.0, now)
                return Verdict(True, int(tokens - 1.0))
            self._buckets[identity] = (tokens, now)
            return Verdict(False, 0, retry_after_s=round((1.0 - tokens) / self._rate, 2))


def limiter_from_env(env: dict[str, str] | None = None) -> Limiter:
    env = os.environ if env is None else env
    return Limiter(int(env.get("GATEWAY_RATE_LIMIT", "120")), float(env.get("GATEWAY_RATE_WINDOW_SECONDS", "60")))

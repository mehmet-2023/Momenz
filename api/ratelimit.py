from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class InMemoryRateLimiter:
    """Tek instance için sliding-window limiter.

    Cloud Run'da birden fazla instance olursa her instance kendi sayacını
    tutar. Sıkı limit gerekirse D1 tabanlı bir sayaca geçilebilir.
    """

    def __init__(self, max_events: int, window_seconds: float = 60.0) -> None:
        self.max_events = max(1, int(max_events))
        self.window = float(window_seconds)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allows(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_events:
                return False
            bucket.append(now)
            if len(self._events) > 10_000:
                for stale in [k for k, v in self._events.items() if not v]:
                    self._events.pop(stale, None)
            return True

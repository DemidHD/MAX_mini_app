"""Простой sliding-window rate limiter для одного процесса приложения.

Текущее Docker-развёртывание запускает один uvicorn worker. При переходе на
несколько процессов или реплик хранилище счётчиков нужно вынести в Redis либо
PostgreSQL, сохранив этот же интерфейс.
"""

import asyncio
import math
import time
from collections import deque
from collections.abc import Callable

from app.core.errors import RateLimitError


class SlidingWindowRateLimiter:
    """Атомарно ограничивает число событий для каждого ключа за окно времени."""

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("Параметры rate limiter должны быть положительными")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()
        self._checks = 0

    async def check(self, key: str) -> None:
        now = self._clock()
        cutoff = now - self.window_seconds
        async with self._lock:
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()

            if len(events) >= self.limit:
                retry_after = max(1, math.ceil(events[0] + self.window_seconds - now))
                raise RateLimitError(retry_after)

            events.append(now)
            self._checks += 1
            if self._checks % 256 == 0:
                self._remove_stale_buckets(cutoff)

    async def reset(self) -> None:
        """Очищает состояние; используется при изолированном тестировании."""
        async with self._lock:
            self._events.clear()
            self._checks = 0

    def _remove_stale_buckets(self, cutoff: float) -> None:
        for key, events in list(self._events.items()):
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                del self._events[key]

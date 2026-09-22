"""Ограничение частоты запросов для публичных критичных операций."""

import asyncio

from app.core.errors import RateLimitError
from app.core.rate_limit import SlidingWindowRateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


async def test_rate_limiter_resets_after_window() -> None:
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(limit=1, window_seconds=10, clock=clock)

    await limiter.check("client")
    try:
        await limiter.check("client")
    except RateLimitError as error:
        assert error.details == {"retry_after_seconds": 10}
    else:
        raise AssertionError("Второй запрос должен быть ограничен")

    clock.value = 10.0
    await limiter.check("client")


async def test_rate_limiter_is_atomic_for_concurrent_requests() -> None:
    limiter = SlidingWindowRateLimiter(limit=5, window_seconds=60)

    results = await asyncio.gather(
        *(limiter.check("client") for _ in range(10)), return_exceptions=True
    )

    assert sum(result is None for result in results) == 5
    assert sum(isinstance(result, RateLimitError) for result in results) == 5

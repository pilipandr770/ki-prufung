import asyncio
import time


class RateLimiter:
    """Token bucket rate limiter for async code."""

    def __init__(self, requests_per_minute: int = 45):
        self._rpm = requests_per_minute
        self._tokens = float(requests_per_minute)
        self._max_tokens = float(requests_per_minute)
        self._refill_rate = requests_per_minute / 60.0  # tokens per second
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            self._refill()
            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self._refill_rate
                await asyncio.sleep(wait_time)
                self._refill()
            self._tokens -= 1.0

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._max_tokens, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

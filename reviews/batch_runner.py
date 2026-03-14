import asyncio
from typing import Callable
from anthropic import AsyncAnthropic
from personas.models import Persona
from scraper.models import ScrapedProduct
from utils.rate_limiter import RateLimiter
from .models import Review
from .generator import ReviewGenerator
from config import settings


class BatchRunner:
    def __init__(
        self,
        generator: ReviewGenerator | None = None,
        batch_size: int | None = None,
        max_concurrent_batches: int | None = None,
    ):
        self._generator = generator or ReviewGenerator()
        self._batch_size = batch_size or settings.batch_size
        self._max_concurrent = max_concurrent_batches or settings.max_concurrent_batches

    async def run(
        self,
        personas: list[Persona],
        product: ScrapedProduct,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> list[Review]:
        limiter = RateLimiter(settings.requests_per_minute)
        semaphore = asyncio.Semaphore(self._max_concurrent)
        total = len(personas)
        completed = 0
        results: list[Review | None] = [None] * total
        errors: list[str] = []

        async def process_one(idx: int, persona: Persona) -> None:
            nonlocal completed
            async with semaphore:
                try:
                    review = await self._generator.generate_one(persona, product, limiter)
                    results[idx] = review
                except Exception as e:
                    errors.append(str(e))
                finally:
                    completed += 1
                    if on_progress:
                        on_progress(completed, total)

        # Split into batches for better memory management
        chunks = [
            personas[i: i + self._batch_size]
            for i in range(0, len(personas), self._batch_size)
        ]

        for chunk_start, chunk in enumerate(chunks):
            start_idx = chunk_start * self._batch_size
            tasks = [
                asyncio.create_task(process_one(start_idx + i, persona))
                for i, persona in enumerate(chunk)
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        good = [r for r in results if r is not None]
        if not good and errors:
            raise RuntimeError(
                f"Alle {total} Review-Generierungen fehlgeschlagen. "
                f"Erster Fehler: {errors[0]}"
            )
        return good

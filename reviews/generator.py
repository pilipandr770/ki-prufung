import json
import re
import uuid
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from personas.models import Persona
from scraper.models import ScrapedProduct
from utils.rate_limiter import RateLimiter
from .models import Review
from .prompt_builder import get_system_prompt, build_user_prompt
from config import settings


class ReviewGenerator:
    def __init__(self, client: AsyncAnthropic | None = None):
        self._client = client or AsyncAnthropic(api_key=settings.anthropic_api_key)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def generate_one(
        self,
        persona: Persona,
        product: ScrapedProduct,
        limiter: RateLimiter,
    ) -> Review:
        await limiter.acquire()

        language = getattr(persona, "language", "de")
        response = await self._client.messages.create(
            model=settings.claude_model,
            max_tokens=450,
            system=get_system_prompt(language),
            messages=[{"role": "user", "content": build_user_prompt(persona, product)}],
        )

        text = response.content[0].text
        return self._parse_response(text, persona, product)

    def _parse_response(self, text: str, persona: Persona, product: ScrapedProduct) -> Review:
        stars = max(1, min(5, round(persona.star_rating_tendency)))
        review_text = text.strip()

        # Primary: parse JSON response
        try:
            json_match = re.search(r'\{[^{}]+\}', text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                stars = max(1, min(5, int(data["stars"])))
                review_text = str(data.get("review", text)).strip()
        except (json.JSONDecodeError, ValueError, KeyError, TypeError):
            # Fallback: legacy regex format (BEWERTUNG / REZENSION)
            star_match = re.search(r'(?:BEWERTUNG|stars)[:\s]*([1-5])', text, re.IGNORECASE)
            if star_match:
                stars = int(star_match.group(1))
            review_match = re.search(r'(?:REZENSION|review)[:\s]*(.+)', text, re.DOTALL | re.IGNORECASE)
            if review_match:
                review_text = review_match.group(1).strip()

        return Review(
            id=str(uuid.uuid4()),
            persona_id=persona.id,
            persona_name=persona.display_name,
            persona_traits=persona.trait_labels,
            product_name=product.name,
            star_rating=stars,
            review_text=review_text[:1500],
        )

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScrapedPage:
    url: str
    title: str
    text_content: str
    meta_description: str = ""
    structured_data: dict = field(default_factory=dict)


@dataclass
class ScrapedProduct:
    name: str
    description: str
    price: Optional[str] = None
    category: Optional[str] = None
    features: list[str] = field(default_factory=list)
    raw_pages: list[ScrapedPage] = field(default_factory=list)
    extra_context: str = ""  # aggregated text from sub-pages

    def summary(self, max_chars: int = 1200) -> str:
        """Build a rich product summary for LLM prompts."""
        parts = [f"Product/Website: {self.name}"]
        if self.price:
            parts.append(f"Price: {self.price}")
        if self.category:
            parts.append(f"Category: {self.category}")

        # Full description (up to 600 chars)
        if self.description:
            parts.append(f"Description: {self.description[:600]}")

        # Features / highlights
        if self.features:
            parts.append("Key features: " + " | ".join(self.features[:12]))

        # Extra context from sub-pages (fills remaining budget)
        if self.extra_context:
            used = sum(len(p) for p in parts)
            remaining = max_chars - used - 30
            if remaining > 100:
                parts.append(f"Additional info: {self.extra_context[:remaining]}")

        return "\n".join(parts)[:max_chars]

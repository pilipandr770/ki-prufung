from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Review:
    id: str
    persona_id: str
    persona_name: str
    persona_traits: list[str]
    product_name: str
    star_rating: int
    review_text: str
    sentiment_score: float = 0.0
    word_count: int = 0
    generated_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        if not self.word_count:
            self.word_count = len(self.review_text.split())

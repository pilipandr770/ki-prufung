from dataclasses import dataclass, field
from datetime import datetime
import pandas as pd
from reviews.models import Review
from scraper.models import ScrapedProduct
from analysis.sentiment import score_text
from analysis.statistics import (
    compute_rating_distribution,
    compute_sentiment_distribution,
    compute_average_rating,
    compute_persona_breakdown,
    compute_top_keywords,
    compute_average_by_trait,
)
from .charts import rating_bar_chart, sentiment_pie_chart, trait_avg_chart, keywords_chart


@dataclass
class ReportContext:
    product: ScrapedProduct
    reviews: list[Review]
    total_reviews: int
    avg_rating: float
    rating_dist: dict[int, int]
    sentiment_dist: dict[str, int]
    persona_breakdown: pd.DataFrame
    top_keywords: list[tuple[str, int]]
    trait_avg_ratings: dict[str, float]
    chart_rating_html: str
    chart_sentiment_html: str
    chart_traits_html: str
    chart_keywords_html: str
    sample_reviews: list[Review]
    generated_at: str = field(default_factory=lambda: datetime.now().strftime("%d.%m.%Y %H:%M"))


def build_report_context(product: ScrapedProduct, reviews: list[Review], language: str = "de") -> ReportContext:
    # Score sentiments
    for r in reviews:
        r.sentiment_score = score_text(r.review_text, language)

    rating_dist = compute_rating_distribution(reviews)
    sentiment_dist = compute_sentiment_distribution(reviews, language)
    avg_rating = compute_average_rating(reviews)
    persona_breakdown = compute_persona_breakdown(reviews)
    top_keywords = compute_top_keywords(reviews, n=20, language=language)
    trait_avg = compute_average_by_trait(reviews)

    # Sample reviews: diverse selection (varied ratings, long texts)
    sorted_reviews = sorted(reviews, key=lambda r: r.word_count, reverse=True)
    sample: list[Review] = []
    seen_ratings: set[int] = set()
    for r in sorted_reviews:
        if r.star_rating not in seen_ratings or len(sample) < 20:
            sample.append(r)
            seen_ratings.add(r.star_rating)
        if len(sample) >= 25:
            break

    return ReportContext(
        product=product,
        reviews=reviews,
        total_reviews=len(reviews),
        avg_rating=avg_rating,
        rating_dist=rating_dist,
        sentiment_dist=sentiment_dist,
        persona_breakdown=persona_breakdown,
        top_keywords=top_keywords,
        trait_avg_ratings=trait_avg,
        chart_rating_html=rating_bar_chart(rating_dist),
        chart_sentiment_html=sentiment_pie_chart(sentiment_dist),
        chart_traits_html=trait_avg_chart(trait_avg),
        chart_keywords_html=keywords_chart(top_keywords),
        sample_reviews=sample,
    )

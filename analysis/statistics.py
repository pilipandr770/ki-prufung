import re
from collections import Counter
import pandas as pd
from reviews.models import Review
from .sentiment import classify_sentiment
from personas.languages import SENTIMENT_LABELS

_STOPWORDS: dict[str, set[str]] = {
    "de": {
        "der", "die", "das", "und", "in", "zu", "von", "mit", "auf", "für",
        "ist", "es", "ein", "eine", "einer", "eines", "ich", "sie", "wir",
        "hat", "haben", "war", "aber", "auch", "als", "an", "aus", "bei",
        "nach", "noch", "dem", "den", "des", "im", "ins", "am", "zum", "zur",
        "nicht", "sehr", "so", "da", "dass", "wenn", "wie", "was", "dann",
        "mich", "mir", "ihn", "ihm", "ihr", "uns", "euch", "man", "sich",
    },
    "en": {
        "the", "and", "for", "are", "was", "this", "that", "with", "have",
        "from", "not", "but", "they", "had", "his", "her", "you", "your",
        "its", "our", "been", "more", "also", "some", "than", "very", "just",
        "would", "when", "which", "there", "their", "what", "about", "into",
        "will", "did", "get", "got", "can", "one", "all", "has",
    },
    "fr": {
        "le", "la", "les", "de", "du", "des", "un", "une", "et", "en",
        "est", "je", "il", "elle", "nous", "vous", "ils", "elles", "mon",
        "ma", "son", "sa", "ce", "qui", "que", "pas", "mais", "sur", "par",
        "avé", "avec", "pour", "dans", "au", "aux", "ou", "si", "très",
    },
    "pl": {
        "i", "w", "z", "na", "do", "się", "to", "jest", "nie", "co",
        "jak", "ale", "po", "przez", "ten", "ta", "te", "tego", "tej",
        "tym", "tych", "o", "tak", "był", "była", "było", "przy", "ze",
    },
}

# Backwards-compatible alias
GERMAN_STOPWORDS = _STOPWORDS["de"]


def compute_rating_distribution(reviews: list[Review]) -> dict[int, int]:
    dist = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for r in reviews:
        dist[r.star_rating] = dist.get(r.star_rating, 0) + 1
    return dist


def compute_sentiment_distribution(reviews: list[Review], language: str = "de") -> dict[str, int]:
    labels = SENTIMENT_LABELS.get(language, SENTIMENT_LABELS["de"])
    dist = {labels["positive"]: 0, labels["neutral"]: 0, labels["negative"]: 0}
    for r in reviews:
        label = classify_sentiment(r.sentiment_score, language)
        dist[label] = dist.get(label, 0) + 1
    return dist


def compute_average_rating(reviews: list[Review]) -> float:
    if not reviews:
        return 0.0
    return round(sum(r.star_rating for r in reviews) / len(reviews), 2)


def compute_persona_breakdown(reviews: list[Review]) -> pd.DataFrame:
    rows = []
    for r in reviews:
        for trait in r.persona_traits:
            rows.append({
                "trait": trait,
                "star_rating": r.star_rating,
                "sentiment": r.sentiment_score,
            })

    if not rows:
        return pd.DataFrame(columns=["trait", "avg_rating", "count", "avg_sentiment"])

    df = pd.DataFrame(rows)
    breakdown = df.groupby("trait").agg(
        avg_rating=("star_rating", "mean"),
        count=("star_rating", "count"),
        avg_sentiment=("sentiment", "mean"),
    ).reset_index()
    breakdown["avg_rating"] = breakdown["avg_rating"].round(2)
    breakdown["avg_sentiment"] = breakdown["avg_sentiment"].round(3)
    return breakdown.sort_values("count", ascending=False)


def compute_top_keywords(reviews: list[Review], n: int = 20, language: str = "de") -> list[tuple[str, int]]:
    stopwords = _STOPWORDS.get(language, _STOPWORDS["de"])
    all_words: list[str] = []
    for r in reviews:
        words = re.findall(r'\b[\wà-ɏ]{3,}\b', r.review_text.lower())
        all_words.extend(w for w in words if w not in stopwords)
    counter = Counter(all_words)
    return counter.most_common(n)


def compute_average_by_trait(reviews: list[Review]) -> dict[str, float]:
    trait_ratings: dict[str, list[int]] = {}
    for r in reviews:
        for trait in r.persona_traits:
            trait_ratings.setdefault(trait, []).append(r.star_rating)
    return {
        trait: round(sum(ratings) / len(ratings), 2)
        for trait, ratings in trait_ratings.items()
    }

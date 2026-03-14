import re
from personas.languages import SENTIMENT_LABELS

# ── German ────────────────────────────────────────────────────────────────────
_POSITIVE_DE = {
    "ausgezeichnet", "hervorragend", "empfehle", "empfehlenswert", "toll", "super",
    "zufrieden", "zufriedenstellend", "schnell", "günstig", "preiswert", "perfekt",
    "wunderbar", "fantastisch", "großartig", "prima", "klasse", "top", "gut",
    "qualität", "hochwertig", "zuverlässig", "robust", "praktisch", "nützlich",
    "bequem", "komfortabel", "einfach", "unkompliziert", "schnelle lieferung",
    "pünktlich", "genau", "passt", "funktioniert", "begeistert", "erfreut",
    "empfohlen", "wiederbestellen", "kaufe wieder", "gerne wieder", "sehr gut",
    "sehr zufrieden", "bestens", "einwandfrei", "tadellos", "makellos",
}
_NEGATIVE_DE = {
    "enttäuschend", "enttäuscht", "schlecht", "mangelhaft", "defekt", "kaputt",
    "langsam", "teuer", "überteuert", "probleme", "problem", "fehler",
    "unzufrieden", "schlechte qualität", "billig", "minderwertig", "nutzlos",
    "unnötig", "schwierig", "kompliziert", "umständlich", "nervig", "ärgerlich",
    "zurückgegeben", "reklamiert", "beschwert", "nicht funktioniert",
    "kaputtgegangen", "verschwendung", "geldverschwendung", "zeitverschwendung",
    "würde nicht empfehlen", "kein kauf", "finger weg", "vorsicht",
    "schrottware", "enttäuschung", "katastrophe", "desaster", "horror",
}
_NEGATION_DE = {"nicht", "kein", "keine", "keinen", "keinem", "nie", "niemals", "kaum"}

# ── English ───────────────────────────────────────────────────────────────────
_POSITIVE_EN = {
    "excellent", "outstanding", "recommend", "recommended", "great", "superb",
    "satisfied", "fast", "affordable", "cheap", "perfect", "wonderful",
    "fantastic", "brilliant", "amazing", "good", "quality", "premium",
    "reliable", "sturdy", "practical", "useful", "comfortable", "easy",
    "straightforward", "quick delivery", "punctual", "accurate", "works",
    "impressed", "happy", "pleased", "delighted", "love", "loved",
    "best", "flawless", "excellent value", "highly recommend", "would buy again",
}
_NEGATIVE_EN = {
    "disappointing", "disappointed", "bad", "poor", "defective", "broken",
    "slow", "expensive", "overpriced", "problem", "problems", "error",
    "unsatisfied", "cheap quality", "useless", "unnecessary", "difficult",
    "complicated", "annoying", "frustrating", "returned", "complained",
    "waste", "waste of money", "waste of time", "would not recommend",
    "do not buy", "avoid", "terrible", "awful", "disaster", "horrible",
    "rubbish", "junk", "scam", "ripoff",
}
_NEGATION_EN = {"not", "no", "never", "barely", "hardly", "without", "lack"}

# ── French ────────────────────────────────────────────────────────────────────
_POSITIVE_FR = {
    "excellent", "parfait", "recommande", "recommandé", "super", "bien",
    "satisfait", "rapide", "abordable", "bon marché", "merveilleux",
    "fantastique", "génial", "qualité", "fiable", "robuste", "pratique",
    "utile", "confortable", "facile", "livraison rapide", "ponctuel",
    "fonctionne", "impressionné", "heureux", "content", "ravi",
    "meilleur", "impeccable", "très bien", "très satisfait",
}
_NEGATIVE_FR = {
    "décevant", "déçu", "mauvais", "médiocre", "défectueux", "cassé",
    "lent", "cher", "trop cher", "problème", "problèmes", "erreur",
    "insatisfait", "mauvaise qualité", "inutile", "difficile", "compliqué",
    "agaçant", "retourné", "gaspillage", "perte d'argent",
    "déconseille", "ne pas acheter", "éviter", "terrible", "horrible",
    "catastrophe", "désastre", "arnaque",
}
_NEGATION_FR = {"ne", "pas", "jamais", "aucun", "aucune", "sans", "ni"}

# ── Polish ────────────────────────────────────────────────────────────────────
_POSITIVE_PL = {
    "doskonały", "świetny", "polecam", "polecany", "super", "dobry",
    "zadowolony", "szybki", "tani", "przystępny", "idealny", "wspaniały",
    "fantastyczny", "jakość", "niezawodny", "solidny", "praktyczny",
    "użyteczny", "wygodny", "łatwy", "szybka dostawa", "punktualny",
    "działa", "wrażenie", "szczęśliwy", "zadowolona", "zachwycony",
    "najlepszy", "bez zarzutu", "bardzo dobry", "bardzo zadowolony",
}
_NEGATIVE_PL = {
    "rozczarowujący", "rozczarowany", "zły", "słaby", "wadliwy", "zepsuty",
    "wolny", "drogi", "za drogi", "problem", "problemy", "błąd",
    "niezadowolony", "zła jakość", "bezużyteczny", "trudny", "skomplikowany",
    "irytujący", "zwrócony", "strata", "strata pieniędzy",
    "nie polecam", "nie kupować", "unikać", "straszny", "okropny",
    "katastrofa", "koszmar", "oszustwo",
}
_NEGATION_PL = {"nie", "bez", "nigdy", "żaden", "żadna", "ani"}

_LEXICONS = {
    "de": (_POSITIVE_DE, _NEGATIVE_DE, _NEGATION_DE),
    "en": (_POSITIVE_EN, _NEGATIVE_EN, _NEGATION_EN),
    "fr": (_POSITIVE_FR, _NEGATIVE_FR, _NEGATION_FR),
    "pl": (_POSITIVE_PL, _NEGATIVE_PL, _NEGATION_PL),
}


def _score_with_lexicon(
    text: str,
    positives: set[str],
    negatives: set[str],
    negations: set[str],
) -> float:
    if not text:
        return 0.0
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    pos_count = 0
    neg_count = 0
    for phrase in positives:
        if ' ' in phrase and phrase in text_lower:
            pos_count += 2
    for phrase in negatives:
        if ' ' in phrase and phrase in text_lower:
            neg_count += 2
    for i, word in enumerate(words):
        context = words[max(0, i - 3): i]
        negated = any(n in context for n in negations)
        if word in positives and ' ' not in word:
            neg_count += 1 if negated else 0
            pos_count += 0 if negated else 1
        elif word in negatives and ' ' not in word:
            pos_count += 1 if negated else 0
            neg_count += 0 if negated else 1
    total = pos_count + neg_count
    if total == 0:
        return 0.0
    return round(max(-1.0, min(1.0, (pos_count - neg_count) / total)), 3)


def score_text(text: str, language: str = "de") -> float:
    """Return sentiment score in [-1.0, 1.0] for any supported language."""
    pos, neg, negations = _LEXICONS.get(language, _LEXICONS["de"])
    return _score_with_lexicon(text, pos, neg, negations)


# Backwards-compatible alias
def score_german_text(text: str) -> float:
    return score_text(text, language="de")


def classify_sentiment(score: float, language: str = "de") -> str:
    labels = SENTIMENT_LABELS.get(language, SENTIMENT_LABELS["de"])
    if score > 0.15:
        return labels["positive"]
    if score < -0.15:
        return labels["negative"]
    return labels["neutral"]

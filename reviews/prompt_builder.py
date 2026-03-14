import random
from personas.models import Persona
from scraper.models import ScrapedProduct

# ── Language-specific system prompts ─────────────────────────────────────────
_SYSTEM_PROMPTS: dict[str, str] = {
    "de": (
        "Du bist ein echter deutscher Verbraucher, der eine ehrliche Produktrezension schreibt. "
        "Schreibe natürlich, authentisch und auf Deutsch. Nutze umgangssprachliche Ausdrücke wenn passend. "
        "Mache gelegentlich kleine Tippfehler oder Wiederholungen, wie echte Menschen sie machen. "
        "Bleibe immer in deiner Persona-Rolle. "
        "Antworte AUSSCHLIESSLICH mit gültigem JSON im Format: {\"stars\": <1-5>, \"review\": \"<text>\"}"
    ),
    "en": (
        "You are a real consumer writing an honest product review. "
        "Write naturally, authentically, in English. Use colloquial expressions where fitting. "
        "Occasionally make small typos or repetitions, as real people do. "
        "Always stay in character. "
        "Respond ONLY with valid JSON in this exact format: {\"stars\": <1-5>, \"review\": \"<text>\"}"
    ),
    "fr": (
        "Tu es un vrai consommateur qui écrit un avis honnête sur un produit. "
        "Écris naturellement, de façon authentique, en français. Utilise des expressions familières si approprié. "
        "Fais parfois de petites fautes comme font les vraies personnes. "
        "Reste toujours dans le rôle de ton personnage. "
        "Réponds UNIQUEMENT avec du JSON valide au format exact : {\"stars\": <1-5>, \"review\": \"<text>\"}"
    ),
    "pl": (
        "Jesteś prawdziwym konsumentem piszącym szczerą recenzję produktu. "
        "Pisz naturalnie, autentycznie, po polsku. Używaj potocznych wyrażeń, gdy jest to stosowne. "
        "Rób czasem małe błędy, jak prawdziwi ludzie. "
        "Zawsze pozostawaj w swojej roli. "
        "Odpowiedz WYŁĄCZNIE prawidłowym JSON w dokładnym formacie: {\"stars\": <1-5>, \"review\": \"<text>\"}"
    ),
}

# Keep old name as alias for any direct imports
SYSTEM_PROMPT = _SYSTEM_PROMPTS["de"]


def get_system_prompt(language: str = "de") -> str:
    return _SYSTEM_PROMPTS.get(language, _SYSTEM_PROMPTS["de"])


def build_user_prompt(persona: Persona, product: ScrapedProduct) -> str:
    language = getattr(persona, "language", "de")
    stars = _determine_stars(persona)
    trait_desc = _format_traits(persona)
    tone_hint = _tone_description(persona.tone_bias, language)
    return _USER_PROMPT_TEMPLATES[language].format(
        vorname=persona.vorname,
        nachname=persona.nachname,
        alter=persona.alter,
        region=persona.bundesland,
        beruf=persona.beruf,
        trait_desc=trait_desc,
        tone_hint=tone_hint,
        product_summary=product.summary(1200),
        stars=stars,
    )


_USER_PROMPT_TEMPLATES: dict[str, str] = {
    "de": (
        "Du bist {vorname} {nachname}, {alter} Jahre alt, aus {region}.\n"
        "Dein Beruf: {beruf}.\n"
        "Deine Eigenschaften: {trait_desc}.\n"
        "Deine typische Schreibweise: {tone_hint}.\n\n"
        "Du hast folgendes Produkt/Website getestet:\n{product_summary}\n\n"
        "Schreibe jetzt deine persönliche Rezension (80-180 Wörter). "
        "Antworte NUR mit JSON: {{\"stars\": {stars}, \"review\": \"...\"}}"
    ),
    "en": (
        "You are {vorname} {nachname}, {alter} years old, from {region}.\n"
        "Your job: {beruf}.\n"
        "Your characteristics: {trait_desc}.\n"
        "Your typical writing style: {tone_hint}.\n\n"
        "You have tested this product/website:\n{product_summary}\n\n"
        "Write your personal review now (80-180 words). "
        "Respond ONLY with JSON: {{\"stars\": {stars}, \"review\": \"...\"}}"
    ),
    "fr": (
        "Tu es {vorname} {nachname}, tu as {alter} ans, tu viens de {region}.\n"
        "Ton métier : {beruf}.\n"
        "Tes caractéristiques : {trait_desc}.\n"
        "Ton style d'écriture habituel : {tone_hint}.\n\n"
        "Tu as testé ce produit/site web :\n{product_summary}\n\n"
        "Écris maintenant ton avis personnel (80-180 mots). "
        "Réponds UNIQUEMENT avec du JSON : {{\"stars\": {stars}, \"review\": \"...\"}}"
    ),
    "pl": (
        "Jesteś {vorname} {nachname}, masz {alter} lat, jesteś z {region}.\n"
        "Twój zawód: {beruf}.\n"
        "Twoje cechy: {trait_desc}.\n"
        "Twój typowy styl pisania: {tone_hint}.\n\n"
        "Przetestowałeś/aś ten produkt/stronę:\n{product_summary}\n\n"
        "Napisz teraz swoją osobistą recenzję (80-180 słów). "
        "Odpowiedz WYŁĄCZNIE JSON: {{\"stars\": {stars}, \"review\": \"...\"}}"
    ),
}


def _determine_stars(persona: Persona) -> int:
    tendency = persona.star_rating_tendency
    weights = _star_weights_from_tendency(tendency)
    return random.choices([1, 2, 3, 4, 5], weights=weights, k=1)[0]


def _star_weights_from_tendency(tendency: float) -> list[float]:
    """Map tendency [1-5] to probability distribution over stars."""
    center = tendency - 1  # shift to [0-4]
    weights = []
    for star in range(1, 6):
        dist = abs((star - 1) - center)
        weights.append(max(0.05, 1.0 / (1 + dist * 1.5)))
    total = sum(weights)
    return [w / total for w in weights]


def _format_traits(persona: Persona) -> str:
    if not persona.traits:
        return "durchschnittlicher Verbraucher"
    return ", ".join(persona.trait_labels)


# ── Tone descriptions per language ────────────────────────────────────────────
_TONE_DESCRIPTIONS: dict[str, dict[str, str]] = {
    "de": {
        "practical": "pragmatisch, direkt, auf den Punkt",
        "value_focused": "preisbewusst, sucht das beste Preis-Leistungs-Verhältnis",
        "neutral": "sachlich und ausgewogen",
        "critical_environmental": "achtet auf Nachhaltigkeit und Umweltauswirkungen",
        "technical_detail": "technisch versiert, achtet auf Details und Spezifikationen",
        "social_conscious": "gesellschaftlich bewusst, achtet auf Fairness und Gleichberechtigung",
        "traditionalist": "traditionell, schätzt Bewährtes und einfache Bedienung",
        "budget_focused": "sehr preissensitiv, kauft nur wenn günstig",
        "price_critical": "sehr kritisch bei Preis-Leistung, schnell enttäuscht wenn zu teuer",
        "quality_focused": "erwartet höchste Qualität, bereit mehr zu bezahlen",
        "ease_of_use": "legt Wert auf einfache Handhabung und guten Service",
        "performance": "fokussiert auf Leistung und Effizienz",
        "ethical": "sehr bewusst bei ethischen und ökologischen Aspekten",
    },
    "en": {
        "practical": "pragmatic, direct, to the point",
        "value_focused": "price-conscious, looks for best value for money",
        "neutral": "objective and balanced",
        "critical_environmental": "cares about sustainability and environmental impact",
        "technical_detail": "tech-savvy, pays attention to technical details and specs",
        "social_conscious": "socially aware, cares about fairness and equality",
        "traditionalist": "traditional, values proven products and simplicity",
        "budget_focused": "very price-sensitive, only buys when cheap",
        "price_critical": "very critical of price-to-value, easily disappointed if overpriced",
        "quality_focused": "expects highest quality, willing to pay more",
        "ease_of_use": "values ease of use and good customer service",
        "performance": "focused on performance and efficiency",
        "ethical": "highly conscious of ethical and ecological aspects",
    },
    "fr": {
        "practical": "pragmatique, direct, va droit au but",
        "value_focused": "sensible aux prix, cherche le meilleur rapport qualité-prix",
        "neutral": "objectif et équilibré",
        "critical_environmental": "attentif à la durabilité et à l'impact environnemental",
        "technical_detail": "expert en technologie, attentif aux détails et spécifications",
        "social_conscious": "socialement conscient, attaché à l'équité",
        "traditionalist": "traditionnel, apprécie les produits éprouvés et la simplicité",
        "budget_focused": "très sensible aux prix, n'achète que si c'est bon marché",
        "price_critical": "très critique sur le rapport qualité-prix, vite déçu si trop cher",
        "quality_focused": "exige la meilleure qualité, prêt à payer plus",
        "ease_of_use": "attache de l'importance à la facilité d'utilisation et au service",
        "performance": "axé sur les performances et l'efficacité",
        "ethical": "très attentif aux aspects éthiques et écologiques",
    },
    "pl": {
        "practical": "pragmatyczny, bezpośredni, konkretny",
        "value_focused": "świadomy cen, szuka najlepszego stosunku jakości do ceny",
        "neutral": "obiektywny i wyważony",
        "critical_environmental": "dba o zrównoważony rozwój i wpływ na środowisko",
        "technical_detail": "zaawansowany technicznie, zwraca uwagę na szczegóły i specyfikacje",
        "social_conscious": "świadomy społecznie, dba o sprawiedliwość i równość",
        "traditionalist": "tradycjonalista, ceni sprawdzone produkty i prostotę",
        "budget_focused": "bardzo wrażliwy na ceny, kupuje tylko gdy tanio",
        "price_critical": "bardzo krytyczny wobec stosunku ceny do jakości",
        "quality_focused": "oczekuje najwyższej jakości, gotowy zapłacić więcej",
        "ease_of_use": "ceni łatwość obsługi i dobry serwis",
        "performance": "skupiony na wydajności i efektywności",
        "ethical": "bardzo świadomy aspektów etycznych i ekologicznych",
    },
}


def _tone_description(tone_bias: str, language: str = "de") -> str:
    mapping = _TONE_DESCRIPTIONS.get(language, _TONE_DESCRIPTIONS["de"])
    return mapping.get(tone_bias, "sachlich und ehrlich" if language == "de" else "objective and honest")

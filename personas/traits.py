from typing import FrozenSet

TRAIT_POOL: list[dict] = [
    {"id": "uebergewichtig",   "label": "Übergewichtig",        "weight": 0.08, "tone_bias": "practical",             "star_modifier": 0.0,  "age_min": 18, "age_max": 75},
    {"id": "mutter_vieler",    "label": "Mutter vieler Kinder", "weight": 0.07, "tone_bias": "value_focused",         "star_modifier": -0.2, "age_min": 25, "age_max": 50},
    {"id": "gross",            "label": "Groß (1,90m+)",        "weight": 0.05, "tone_bias": "neutral",               "star_modifier": 0.0,  "age_min": 18, "age_max": 70},
    {"id": "gruener_aktivist", "label": "Grüner Aktivist",      "weight": 0.06, "tone_bias": "critical_environmental","star_modifier": -0.3, "age_min": 18, "age_max": 55},
    {"id": "programmierer",    "label": "Programmierer/in",     "weight": 0.09, "tone_bias": "technical_detail",      "star_modifier": 0.1,  "age_min": 20, "age_max": 55},
    {"id": "feministin",       "label": "Feministin",           "weight": 0.07, "tone_bias": "social_conscious",      "star_modifier": -0.1, "age_min": 18, "age_max": 60},
    {"id": "senior",           "label": "Senior (65+)",         "weight": 0.10, "tone_bias": "traditionalist",        "star_modifier": 0.2,  "age_min": 65, "age_max": 85},
    {"id": "student",          "label": "Student/in",           "weight": 0.10, "tone_bias": "budget_focused",        "star_modifier": -0.2, "age_min": 18, "age_max": 28},
    {"id": "sparfuechsin",     "label": "Sparfüchsin/-fuchs",   "weight": 0.11, "tone_bias": "price_critical",        "star_modifier": -0.4, "age_min": 18, "age_max": 75},
    {"id": "luxuskaeufer",     "label": "Luxuskäufer/in",       "weight": 0.06, "tone_bias": "quality_focused",       "star_modifier": 0.5,  "age_min": 30, "age_max": 70},
    {"id": "rentner",          "label": "Rentner/in",           "weight": 0.08, "tone_bias": "ease_of_use",           "star_modifier": 0.3,  "age_min": 60, "age_max": 85},
    {"id": "sportler",         "label": "Aktiver Sportler/in",  "weight": 0.07, "tone_bias": "performance",           "star_modifier": 0.1,  "age_min": 18, "age_max": 55},
    {"id": "veganer",          "label": "Veganer/in",           "weight": 0.06, "tone_bias": "ethical",               "star_modifier": -0.2, "age_min": 18, "age_max": 50},
    {"id": "fleischliebhaber", "label": "Fleischliebhaber/in",  "weight": 0.05, "tone_bias": "practical",             "star_modifier": 0.1,  "age_min": 18, "age_max": 70},
    {"id": "handwerker",       "label": "Handwerker/in",        "weight": 0.07, "tone_bias": "practical",             "star_modifier": 0.0,  "age_min": 20, "age_max": 65},
    {"id": "technik_muffel",   "label": "Technik-Muffel",       "weight": 0.08, "tone_bias": "ease_of_use",           "star_modifier": -0.1, "age_min": 35, "age_max": 80},
    {"id": "alleinerziehend",  "label": "Alleinerziehende/r",   "weight": 0.06, "tone_bias": "value_focused",         "star_modifier": -0.3, "age_min": 22, "age_max": 50},
    {"id": "haustierbesitzer", "label": "Haustierbesitzer/in",  "weight": 0.07, "tone_bias": "neutral",               "star_modifier": 0.1,  "age_min": 18, "age_max": 75},
    {"id": "globetrotter",     "label": "Vielreisende/r",       "weight": 0.05, "tone_bias": "quality_focused",       "star_modifier": 0.2,  "age_min": 25, "age_max": 65},
    {"id": "heimwerker",       "label": "Heimwerker/in",        "weight": 0.06, "tone_bias": "practical",             "star_modifier": 0.0,  "age_min": 28, "age_max": 70},
]

# Pairs that cannot coexist on the same persona
INCOMPATIBLE_PAIRS: list[FrozenSet[str]] = [
    frozenset(["luxuskaeufer", "sparfuechsin"]),
    frozenset(["veganer", "fleischliebhaber"]),
    frozenset(["senior", "student"]),
    frozenset(["senior", "alleinerziehend"]),
    frozenset(["rentner", "student"]),
]

BUNDESLAENDER = [
    "Bayern", "Nordrhein-Westfalen", "Baden-Württemberg", "Niedersachsen",
    "Hessen", "Sachsen", "Rheinland-Pfalz", "Berlin", "Schleswig-Holstein",
    "Brandenburg", "Sachsen-Anhalt", "Thüringen", "Hamburg", "Mecklenburg-Vorpommern",
    "Saarland", "Bremen",
]

# Bundesland population weights (approximate)
BUNDESLAND_WEIGHTS = [
    0.155, 0.215, 0.134, 0.096, 0.076, 0.049, 0.049, 0.044, 0.035,
    0.030, 0.027, 0.026, 0.022, 0.020, 0.012, 0.008,
]

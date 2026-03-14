"""Language-specific configuration for persona generation and review prompts."""

LANGUAGE_CONFIG: dict[str, dict] = {
    "de": {
        "label": "Deutsch 🇩🇪",
        "faker_locale": "de_DE",
        "regions": [
            "Bayern", "Nordrhein-Westfalen", "Baden-Württemberg", "Niedersachsen",
            "Hessen", "Sachsen", "Rheinland-Pfalz", "Berlin", "Schleswig-Holstein",
            "Brandenburg", "Sachsen-Anhalt", "Thüringen", "Hamburg",
            "Mecklenburg-Vorpommern", "Saarland", "Bremen",
        ],
        "region_weights": [
            0.155, 0.215, 0.134, 0.096, 0.076, 0.049, 0.049, 0.044, 0.035,
            0.030, 0.027, 0.026, 0.022, 0.020, 0.012, 0.008,
        ],
        "country": "Deutschland",
        "region_label": "Bundesland",
    },
    "en": {
        "label": "English 🇬🇧",
        "faker_locale": "en_GB",
        "regions": [
            "Greater London", "South East England", "North West England",
            "Yorkshire", "West Midlands", "East of England",
            "South West England", "East Midlands", "North East England",
            "Scotland", "Wales", "Northern Ireland",
        ],
        "region_weights": [
            0.135, 0.140, 0.110, 0.086, 0.088, 0.097, 0.087, 0.075, 0.040,
            0.089, 0.050, 0.030,
        ],
        "country": "United Kingdom",
        "region_label": "Region",
    },
    "fr": {
        "label": "Français 🇫🇷",
        "faker_locale": "fr_FR",
        "regions": [
            "Île-de-France", "Auvergne-Rhône-Alpes", "Nouvelle-Aquitaine",
            "Occitanie", "Hauts-de-France", "Grand Est", "Provence-Alpes-Côte d'Azur",
            "Normandie", "Bretagne", "Pays de la Loire", "Bourgogne-Franche-Comté",
            "Centre-Val de Loire", "Corse",
        ],
        "region_weights": [
            0.190, 0.130, 0.100, 0.090, 0.090, 0.080, 0.080,
            0.050, 0.050, 0.050, 0.040, 0.030, 0.010,
        ],
        "country": "France",
        "region_label": "Région",
    },
    "pl": {
        "label": "Polski 🇵🇱",
        "faker_locale": "pl_PL",
        "regions": [
            "Mazowieckie", "Śląskie", "Wielkopolskie", "Dolnośląskie",
            "Małopolskie", "Łódzkie", "Pomorskie", "Kujawsko-Pomorskie",
            "Lubelskie", "Podkarpackie", "Warmińsko-Mazurskie", "Zachodniopomorskie",
            "Opolskie", "Lubuskie", "Podlaskie", "Świętokrzyskie",
        ],
        "region_weights": [
            0.138, 0.117, 0.088, 0.074, 0.087, 0.066, 0.060, 0.053,
            0.057, 0.055, 0.037, 0.044, 0.027, 0.028, 0.031, 0.038,
        ],
        "country": "Polska",
        "region_label": "Województwo",
    },
}

# Internal keys: "positive", "negative", "neutral"
SENTIMENT_LABELS: dict[str, dict[str, str]] = {
    "de": {"positive": "positiv", "negative": "negativ", "neutral": "neutral"},
    "en": {"positive": "positive", "negative": "negative", "neutral": "neutral"},
    "fr": {"positive": "positif", "negative": "négatif", "neutral": "neutre"},
    "pl": {"positive": "pozytywna", "negative": "negatywna", "neutral": "neutralna"},
}

import random
import uuid
from faker import Faker
from .models import Persona
from .traits import TRAIT_POOL, B2B_TRAIT_POOL, INCOMPATIBLE_PAIRS
from .languages import LANGUAGE_CONFIG
from config import settings

_RECHTSFORMEN = ["GmbH", "UG (haftungsbeschränkt)", "AG", "GbR", "e.K.", "OHG", "KG"]
_DE_CITIES = [
    "Berlin", "Hamburg", "München", "Köln", "Frankfurt am Main", "Stuttgart",
    "Düsseldorf", "Leipzig", "Dortmund", "Essen", "Bremen", "Dresden",
    "Hannover", "Nürnberg", "Duisburg", "Bochum", "Wuppertal", "Bielefeld",
]


def _fake_vat() -> str:
    """Format-valid but fake German VAT number DE + 9 digits."""
    return f"DE{random.randint(100_000_000, 999_999_999)}"


def _fake_zip() -> str:
    return f"{random.randint(10000, 99999)}"


class PersonaGenerator:
    def __init__(self, seed: int | None = None, language: str = "de", mode: str = "b2c"):
        self._rng = random.Random(seed)
        self._language = language
        self._mode = mode  # "b2c" | "b2b"
        lang_cfg = LANGUAGE_CONFIG.get(language, LANGUAGE_CONFIG["de"])
        self._regions = lang_cfg["regions"]
        self._region_weights = lang_cfg["region_weights"]
        self._fake = Faker(lang_cfg["faker_locale"])
        if seed is not None:
            Faker.seed(seed)

    def generate(self, count: int) -> list[Persona]:
        return [self._make_persona() for _ in range(count)]

    def _make_persona(self) -> Persona:
        traits = self._pick_traits()
        age = self._pick_age(traits)
        tone_bias = self._dominant_tone(traits)
        star_tendency = self._derive_star_tendency(traits)
        persona_id = str(uuid.uuid4())
        email = f"test-{persona_id[:8]}@{settings.test_email_domain}"

        kwargs: dict = dict(
            id=persona_id,
            vorname=self._fake.first_name(),
            nachname=self._fake.last_name(),
            alter=age,
            bundesland=self._rng.choices(self._regions, weights=self._region_weights, k=1)[0],
            beruf=self._fake.job(),
            language=self._language,
            email=email,
            traits=traits,
            tone_bias=tone_bias,
            star_rating_tendency=star_tendency,
            mode=self._mode,
        )

        if self._mode == "b2b":
            city = self._rng.choice(_DE_CITIES)
            kwargs.update(
                company_name=self._fake.company(),
                rechtsform=self._rng.choice(_RECHTSFORMEN),
                vat_number=_fake_vat(),
                company_address=self._fake.street_address(),
                company_zip=_fake_zip(),
                company_city=city,
            )

        return Persona(**kwargs)

    def _pick_traits(self) -> list[dict]:
        n_traits = self._rng.choices([1, 2, 3], weights=[0.4, 0.4, 0.2], k=1)[0]
        pool = list(TRAIT_POOL)
        weights = [t["weight"] for t in pool]
        chosen: list[dict] = []
        chosen_ids: set[str] = set()

        attempts = 0
        while len(chosen) < n_traits and attempts < 50:
            attempts += 1
            candidate = self._rng.choices(pool, weights=weights, k=1)[0]
            cid = candidate["id"]
            if cid in chosen_ids:
                continue
            if any(frozenset([cid, existing]) in INCOMPATIBLE_PAIRS for existing in chosen_ids):
                continue
            chosen.append(candidate)
            chosen_ids.add(cid)

        return chosen

    def _pick_age(self, traits: list[dict]) -> int:
        age_min = max((t.get("age_min", 18) for t in traits), default=18)
        age_max = min((t.get("age_max", 80) for t in traits), default=80)
        if age_min > age_max:
            age_min, age_max = 18, 80
        return self._rng.randint(age_min, age_max)

    def _dominant_tone(self, traits: list[dict]) -> str:
        if not traits:
            return "neutral"
        return self._rng.choice(traits)["tone_bias"]

    def _derive_star_tendency(self, traits: list[dict]) -> float:
        base = 3.5
        modifier = sum(t.get("star_modifier", 0.0) for t in traits)
        return max(1.0, min(5.0, base + modifier))

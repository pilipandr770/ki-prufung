from dataclasses import dataclass, field
import secrets


def _default_password() -> str:
    """Generate a strong random password for the test persona."""
    return secrets.token_urlsafe(14)


@dataclass
class Persona:
    id: str
    vorname: str
    nachname: str
    alter: int
    bundesland: str
    beruf: str
    language: str = "de"
    email: str = ""          # set by PersonaGenerator
    password: str = field(default_factory=_default_password)
    traits: list[dict] = field(default_factory=list)
    tone_bias: str = "neutral"
    star_rating_tendency: float = 3.5

    @property
    def trait_labels(self) -> list[str]:
        return [t["label"] for t in self.traits]

    @property
    def display_name(self) -> str:
        return f"{self.vorname} {self.nachname}, {self.alter}J., {self.bundesland}"

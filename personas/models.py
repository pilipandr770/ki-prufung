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
    # B2B-specific fields (populated only in b2b mode)
    mode: str = "b2c"          # "b2c" | "b2b"
    company_name: str = ""
    rechtsform: str = ""
    vat_number: str = ""
    company_address: str = ""
    company_zip: str = ""
    company_city: str = ""

    @property
    def trait_labels(self) -> list[str]:
        return [t["label"] for t in self.traits]

    @property
    def display_name(self) -> str:
        return f"{self.vorname} {self.nachname}, {self.alter}J., {self.bundesland}"

    @property
    def b2b_context(self) -> str:
        """Returns company data string for Claude prompts (B2B mode only)."""
        if self.mode != "b2b" or not self.company_name:
            return ""
        return (
            f"Firmenname: {self.company_name} {self.rechtsform} | "
            f"USt-IdNr.: {self.vat_number} | "
            f"Adresse: {self.company_address}, {self.company_zip} {self.company_city}"
        )

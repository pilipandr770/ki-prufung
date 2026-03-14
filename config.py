from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")
    claude_model: str = "claude-sonnet-4-6"
    max_reviews: int = 2000
    batch_size: int = 50
    max_concurrent_batches: int = 5
    max_pages_to_scrape: int = 30
    scrape_timeout_ms: int = 30_000
    requests_per_minute: int = 45
    report_output_dir: str = "./reports"

    # ─ E-Mail infrastructure for AI persona testing ─────────────────────────
    test_email_domain: str = Field(default="andrii-it.de", env="TEST_EMAIL_DOMAIN")
    imap_host: str = Field(default="", env="IMAP_HOST")
    imap_port: int = Field(default=993, env="IMAP_PORT")
    imap_user: str = Field(default="info@andrii-it.de", env="IMAP_USER")
    imap_password: str = Field(default="", env="IMAP_PASSWORD")
    imap_use_ssl: bool = Field(default=True, env="IMAP_USE_SSL")
    email_wait_timeout_s: int = Field(default=120, env="EMAIL_WAIT_TIMEOUT_S")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def imap_configured(self) -> bool:
        return bool(self.imap_host and self.imap_password)


settings = Settings()

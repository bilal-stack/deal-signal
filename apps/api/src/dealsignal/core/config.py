"""Application settings, read once from the environment."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["local", "ci", "production"]

PLACEHOLDER_KEYS = frozenset({"", "replace-me", "sk-ant-...", "changeme"})
"""Values copied from .env.example. Treated as no key at all, so a job says a key
is missing instead of crawling every site and then failing to authenticate."""


class Settings(BaseSettings):
    """Every value the application needs, with safe local defaults.

    Secrets have no default on purpose: a missing key fails at start-up with a
    clear message rather than halfway through a crawl.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Environment = "local"
    log_level: str = "INFO"
    log_format: Literal["console", "json"] = "console"

    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://dealsignal:dealsignal@localhost:5433/dealsignal"
    )
    database_pool_size: int = 10
    database_echo: bool = False

    redis_url: RedisDsn = RedisDsn("redis://localhost:6380/0")

    # Only needed when a frontend on another origin calls the API; the bundled web app
    # is served by the API itself. NoDecode lets the validator below accept the plain
    # comma-separated form rather than JSON.
    api_cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    anthropic_api_key: str = ""
    companies_house_api_key: str = ""

    overture_release: str = ""
    """Pin a release like "2026-08-20.0". Empty means: ask the bucket for the newest."""

    overture_dataset_url: str = ""
    """Override the parquet location, for an offline copy or a mirror."""

    crawler_user_agent: str = "DealSignalBot/0.1"
    crawler_requests_per_domain_per_second: float = 1.0
    crawler_max_pages_per_site: int = 6
    crawler_timeout_seconds: float = 15.0

    @field_validator("api_cors_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value: object) -> object:
        """Accept a comma-separated string or a JSON list, because both get written."""
        if not isinstance(value, str):
            return value
        text = value.strip()
        if text.startswith("["):
            return json.loads(text)
        return [origin.strip() for origin in text.split(",") if origin.strip()]

    @property
    def has_anthropic_key(self) -> bool:
        return self.anthropic_api_key.strip() not in PLACEHOLDER_KEYS

    @property
    def has_companies_house_key(self) -> bool:
        return self.companies_house_api_key.strip() not in PLACEHOLDER_KEYS


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings are read once per process and cached."""
    return Settings()

from __future__ import annotations

import pytest

from dealsignal.core.config import Settings


def test_cors_origins_accept_a_comma_separated_string() -> None:
    settings = Settings(api_cors_origins="http://localhost:3000, https://example.com")

    assert settings.api_cors_origins == ["http://localhost:3000", "https://example.com"]


def test_cors_origins_accept_a_list() -> None:
    settings = Settings(api_cors_origins=["http://localhost:3000"])

    assert settings.api_cors_origins == ["http://localhost:3000"]


def test_cors_origins_parse_from_a_real_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A plain comma-separated value must not be JSON-decoded before the validator."""
    monkeypatch.setenv("API_CORS_ORIGINS", "http://localhost:3000,https://example.com")

    settings = Settings()

    assert settings.api_cors_origins == ["http://localhost:3000", "https://example.com"]


def test_a_json_list_in_the_environment_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_CORS_ORIGINS", '["http://localhost:3000"]')

    assert Settings().api_cors_origins == ["http://localhost:3000"]


@pytest.mark.parametrize("value", ["", "replace-me", "sk-ant-...", "  replace-me  "])
def test_a_placeholder_key_counts_as_no_key(value: str) -> None:
    """Otherwise a job crawls every website and then fails to authenticate on each."""
    assert Settings(anthropic_api_key=value).has_anthropic_key is False


def test_a_real_looking_key_counts() -> None:
    assert Settings(anthropic_api_key="sk-ant-api03-abc123").has_anthropic_key is True

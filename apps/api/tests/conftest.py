"""Shared fixtures. Unit tests never touch the network or a database."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from dealsignal.core.config import Settings
from dealsignal.main import create_app


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="ci", log_format="json", anthropic_api_key="test-key")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client

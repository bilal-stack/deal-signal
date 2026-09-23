from __future__ import annotations

import pytest

from dealsignal.core.errors import (
    DealSignalError,
    ExternalServiceError,
    NotFoundError,
    SourceBlockedError,
)


def test_not_found_carries_a_404() -> None:
    error = NotFoundError("Company 1 was not found.")

    assert error.status_code == 404
    assert error.code == "not_found"
    assert str(error) == "Company 1 was not found."


def test_external_service_error_names_the_source() -> None:
    error = ExternalServiceError("Companies House did not answer.", source="companies_house")

    assert error.source == "companies_house"
    assert error.retryable is True
    assert error.status_code == 502


def test_blocked_source_is_an_external_service_error() -> None:
    error = SourceBlockedError("robots.txt disallows this path.", source="website")

    assert isinstance(error, ExternalServiceError)
    assert error.code == "source_blocked"


def test_every_domain_error_shares_one_base() -> None:
    with pytest.raises(DealSignalError):
        raise NotFoundError("missing")

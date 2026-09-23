"""Domain exceptions.

Services raise these; the API layer turns them into HTTP responses in one place
(`dealsignal.core.exception_handlers`). Nothing in the codebase raises HTTPException
outside the routers, so business rules stay independent of the web framework.
"""

from __future__ import annotations

from typing import Any


class DealSignalError(Exception):
    """Base class for every error this application raises on purpose.

    `message` is written for the person using the tool, not for a log file.
    """

    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(DealSignalError):
    status_code = 404
    code = "not_found"


class ValidationError(DealSignalError):
    status_code = 422
    code = "validation_error"


class ConflictError(DealSignalError):
    status_code = 409
    code = "conflict"


class ExternalServiceError(DealSignalError):
    """An outside system failed: a data source, or the model API.

    Carries the source name so the UI can say which part is unavailable instead of
    showing a raw provider error. Never swallow one of these into a success response.
    """

    status_code = 502
    code = "external_service_error"

    def __init__(
        self,
        message: str,
        *,
        source: str,
        retryable: bool = True,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.source = source
        self.retryable = retryable


class SourceBlockedError(ExternalServiceError):
    """A source refused us: robots.txt, a log-in wall, a CAPTCHA or a rate limit.

    We back off and fall back to other sources. We never attempt to get around it.
    """

    code = "source_blocked"

"""One place where exceptions become HTTP responses.

Every error body has the same shape, so the frontend can render failures the same
way everywhere:

    {"error": {"code": "...", "message": "...", "details": {...}}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from dealsignal.core.errors import DealSignalError
from dealsignal.core.logging import get_logger

log = get_logger(__name__)

UNEXPECTED_ERROR_MESSAGE = (
    "Something went wrong on our side. The step was not completed, so nothing was saved."
)


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


async def _handle_domain_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DealSignalError)
    log.warning("domain_error", code=exc.code, message=exc.message, details=exc.details)
    return JSONResponse(
        status_code=exc.status_code,
        content=_body(exc.code, exc.message, exc.details),
    )


async def _handle_request_validation(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        status_code=422,
        content=_body(
            "invalid_request",
            "Some values were not accepted.",
            {"fields": exc.errors()},
        ),
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error", path=request.url.path, error=str(exc))
    return JSONResponse(status_code=500, content=_body("internal_error", UNEXPECTED_ERROR_MESSAGE))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DealSignalError, _handle_domain_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation)
    app.add_exception_handler(Exception, _handle_unexpected)

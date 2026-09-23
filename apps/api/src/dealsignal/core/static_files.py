"""Serving the UI so an update is never half applied."""

from __future__ import annotations

from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

REVALIDATE = "no-cache"


class RevalidatedStaticFiles(StaticFiles):
    """Static files the browser must check with us before reusing.

    Without a Cache-Control header, browsers cache by guesswork, and after an update
    a returning user can run the new page with an old app.js. "no-cache" keeps the
    copy but asks first; an unchanged file costs a 304 with no body.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = REVALIDATE
        return response

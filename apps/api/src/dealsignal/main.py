"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from dealsignal import __version__
from dealsignal.core.config import Settings, get_settings
from dealsignal.core.exception_handlers import register_exception_handlers
from dealsignal.core.logging import configure_logging, get_logger
from dealsignal.core.middleware import register_middleware
from dealsignal.core.static_files import RevalidatedStaticFiles
from dealsignal.db.session import dispose_engine, init_engine
from dealsignal.routers import (
    buy_boxes,
    companies,
    duplicates,
    health,
    jobs,
    meta,
    outreach,
    pipeline,
)
from dealsignal.workers.queue import close_queue, open_queue

log = get_logger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

API_TITLE = "DealSignal API"
API_DESCRIPTION = (
    "Finds small businesses that match a Buy Box, cleans their data, and scores how "
    "well they fit and how likely the owner is to sell."
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Tests call this with their own settings."""
    settings = settings or get_settings()
    configure_logging(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_engine(settings)
        app.state.jobs = await open_queue(settings)
        log.info("api_started", environment=settings.environment, version=__version__)
        try:
            yield
        finally:
            await close_queue(app.state.jobs)
            await dispose_engine()
            log.info("api_stopped")

    app = FastAPI(
        title=API_TITLE,
        description=API_DESCRIPTION,
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.state.settings = settings

    if settings.api_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.api_cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    register_middleware(app)
    register_exception_handlers(app)

    app.include_router(health.router)
    app.include_router(buy_boxes.router)
    app.include_router(companies.router)
    app.include_router(duplicates.router)
    app.include_router(pipeline.router)
    app.include_router(jobs.router)
    app.include_router(meta.router)
    app.include_router(outreach.router)

    # The UI is a single static page served by this same process: no build step,
    # no second container, and it can only ever call the API it ships with.
    app.mount("/app", RevalidatedStaticFiles(directory=STATIC_DIR, html=True), name="app")

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/app/")

    return app


app = create_app()

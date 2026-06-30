from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ticketmaster.database import close_db, init_db
from ticketmaster.redis import close_redis, init_redis
from ticketmaster.routers import bookings, events, reservations, search


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: connect DB and Redis. Shutdown: disconnect."""
    await init_db()
    await init_redis()
    yield
    await close_redis()
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Ticketmaster MVP",
        description="Event ticketing REST API — browse, search, reserve, and book seats.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Mount routers
    app.include_router(events.router)
    app.include_router(search.search_router)
    app.include_router(reservations.router)
    app.include_router(bookings.router)

    # Health check
    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def main() -> None:
    """Entry point for `ticketmaster` CLI script."""
    import uvicorn

    from ticketmaster.config import settings

    uvicorn.run(
        "ticketmaster.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
        reload=False,
    )


app = create_app()

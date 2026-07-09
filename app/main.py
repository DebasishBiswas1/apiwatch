"""
main.py — app factory, lifespan, health routes, router mounting.

The lifespan context manager now owns three resources:
  1. The database engine (connection pool)
  2. The APScheduler instance
  3. Future: Redis connection pool (Phase 2)

Everything before yield = startup.
Everything after yield = shutdown.
Order matters: start the scheduler after the DB engine is ready,
stop the scheduler before disposing the engine — jobs may need
the DB during shutdown's grace period.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.worker.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("Starting up APIWatch...")

    # Start the background polling scheduler.
    # This registers the poll_all_endpoints job with the asyncio event loop.
    # The first poll fires 60 seconds after startup — not immediately.
    # Why not immediately? The app needs to finish starting up and be
    # fully ready to serve requests before any background work begins.
    await start_scheduler()
    logger.info("Background scheduler started")

    yield  # ← app is running and serving requests here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("Shutting down APIWatch...")

    # Stop the scheduler first — prevent new jobs from starting.
    await stop_scheduler()

    # Then dispose the engine — close all pooled DB connections.
    # Order: scheduler before engine because in-flight jobs may still
    # need DB access during the brief shutdown window.
    await engine.dispose()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── Health routes ─────────────────────────────────────────────────────────
    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/db", tags=["health"])
    async def health_db() -> dict[str, str]:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"database": "reachable"}

    # ── API routers ───────────────────────────────────────────────────────────
    from app.api.v1.auth import router as auth_router
    from app.api.v1.endpoints import router as endpoints_router

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(endpoints_router, prefix="/api/v1")

    return app


app = create_app()
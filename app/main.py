from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.models import HTTPBearer
from fastapi.security import HTTPBearer as HTTPBearerScheme
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal, engine


# ── Lifespan ──────────────────────────────────────────────────────────────────
# The modern replacement for @app.on_event("startup") / ("shutdown").
# Everything BEFORE yield runs once when the server starts.
# Everything AFTER yield runs once when the server shuts down.
#
# Why dispose the engine on shutdown?
#   engine.dispose() closes all idle connections in the pool and waits
#   for active ones to finish. Without it, abrupt shutdowns (Ctrl+C,
#   container restart) leave Postgres holding half-open connections until
#   its own timeout expires. In development with --reload this happens
#   on every file save — connections accumulate fast.
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — nothing to warm up yet in step 1a.
    yield
    # Shutdown — release every pooled connection cleanly.
    await engine.dispose()


# ── App factory ───────────────────────────────────────────────────────────────
# Why a factory function instead of module-level app = FastAPI()?
#   Importing a module that calls FastAPI() at module level triggers all
#   setup code immediately — including anything that touches config or the DB.
#   Tests that import this module would need a live database just to import.
#   A factory makes the app an artifact of calling a function, so imports
#   are side-effect-free and tests can build isolated app instances.
def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── Health: liveness ──────────────────────────────────────────────────────
    # Answers: "Is the process alive?"
    # Must NOT touch any external dependency (database, cache, etc.).
    # Orchestrators (Kubernetes, Docker) use this to decide whether to
    # RESTART the container. If this hits the DB and the DB is briefly slow,
    # the orchestrator kills a perfectly healthy app — a restart storm.
    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    # ── Health: readiness ─────────────────────────────────────────────────────
    # Answers: "Can this instance actually serve traffic right now?"
    # Legitimately touches the database — that is the point.
    # Orchestrators use this to decide whether to ROUTE traffic to this
    # instance. Failing readiness removes it from the load balancer without
    # restarting it.
    #
    # text("SELECT 1"): SQLAlchemy 2.0 requires explicit text() wrapping for
    # raw SQL strings. This is a deliberate safety feature — it prevents
    # accidentally passing an unescaped string where a query is expected.
    # "SELECT 1" is the cheapest possible query: no table scan, no I/O.
    @app.get("/health/db", tags=["health"])
    async def health_db() -> dict[str, str]:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"database": "reachable"}
    
    # ── API routers ───────────────────────────────────────────────────────────
    # We import routers here (inside create_app) rather than at module
    # level to avoid circular imports — routers import from models and
    # security, which import from config, all of which need to be fully
    # loaded before wiring happens.
    #
    # prefix="/api/v1" means all routes are versioned from the start.
    # Versioning now costs nothing and saves enormous pain later if you
    # ever need to introduce breaking changes — v2 routes can coexist
    # with v1 without disrupting existing clients.
    from app.api.v1.auth import router as auth_router
    from app.api.v1.endpoints import router as endpoints_router 
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(endpoints_router, prefix="/api/v1")

    return app


# Module-level app instance — this is what uvicorn looks for.
# "uvicorn app.main:app" means: in module app.main, find the name app.
app = create_app()

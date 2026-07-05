from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
# Created once. Lives for the entire application lifetime.
# Owns the connection pool — reuses established TCP connections to Postgres
# instead of opening a new one on every request.
#
# echo=True in local: prints every SQL statement to stdout.
#   Use this to see exactly what SQLAlchemy sends to the database.
#   Set ENVIRONMENT=production to silence it.
#
# pool_pre_ping=True: before lending a pooled connection to a session,
#   send a lightweight "SELECT 1" to verify the connection is still alive.
#   Without this, a connection that Postgres dropped (idle timeout, restart)
#   surfaces as a cryptic error on a real query instead of being detected here.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.ENVIRONMENT == "local",
    pool_pre_ping=True,
)

# ── Session factory ───────────────────────────────────────────────────────────
# async_sessionmaker is a callable that produces AsyncSession instances.
# It is NOT a session itself. Think of it as a configured stamp:
# call SessionLocal() → get a fresh session bound to the engine above.
#
# expire_on_commit=False:
#   Default SQLAlchemy behaviour expires all object attributes after commit(),
#   so the next attribute read fires a fresh SELECT to refresh them.
#   In async code that lazy refresh often fires AFTER the session has closed,
#   raising a "DetachedInstanceError". Setting False keeps the committed
#   object's in-memory state intact — safe to return from a route handler.
SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Per-request dependency ────────────────────────────────────────────────────
# An async generator used as a FastAPI dependency (Depends(get_db)).
# Yields exactly one session per request.
# The "async with" block guarantees the session is closed — and its
# connection returned to the pool — even if the route handler raises.
# This is the ONLY correct way to manage session lifetime in FastAPI.
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session

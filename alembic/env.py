"""
Alembic migration environment — async version.

Why rewrite the default env.py?
  alembic init generates a synchronous env.py that uses a sync engine.
  Our app uses an async engine (create_async_engine + asyncpg).
  Running a sync migration against an async engine fails.
  We must use AsyncEngine.connect() inside an asyncio.run() call.

Key concepts:
  - target_metadata: tells Alembic what the models SHOULD look like.
    Autogenerate diffs this against the live DB to produce migrations.
  - include_schemas: False — we use the shared-schema pattern, one
    Postgres schema (public) for all tenants.
  - compare_type: True — Alembic also detects column TYPE changes,
    not just additions/removals.
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.db.base import Base

# Import all models so Base.metadata knows about every table.
# Without this import, autogenerate sees an empty metadata and
# generates a migration that drops all your tables.
import app.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# This is the critical line — tells Alembic what tables SHOULD exist.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Offline mode: generate SQL without connecting to the DB.
    Useful for reviewing migration SQL before applying it.
    """
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Online async mode: connects to the live DB and runs migrations.
    create_async_engine uses our settings DATABASE_URL — same as the app.
    """
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

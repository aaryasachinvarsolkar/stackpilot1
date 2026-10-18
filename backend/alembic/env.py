"""Alembic environment.

* URL: an explicit `sqlalchemy.url` (set by tooling/tests) wins, otherwise the app's DATABASE_URL.
* Works with the async drivers the app uses (aiosqlite, asyncpg).
* SQLite: DDL is made transactional (explicit BEGIN) so a failing migration rolls back completely
  instead of leaving a half-applied schema.
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import event, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.models import Base  # importing app.models registers every table on Base.metadata

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    return config.get_main_option("sqlalchemy.url") or settings.DATABASE_URL


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    is_sqlite = (url or str(connection.engine.url)).startswith("sqlite")
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=is_sqlite,
        transactional_ddl=True if is_sqlite else None,
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"} if connection is None else None,
    )


def run_migrations_offline() -> None:
    _configure(url=_database_url())
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = _database_url()
    engine = create_async_engine(url, poolclass=pool.NullPool)

    if url.startswith("sqlite"):
        # pysqlite never opens a transaction before DDL, so every statement would autocommit.
        # Taking over transaction control makes each migration atomic.
        @event.listens_for(engine.sync_engine, "connect")
        def _manual_transactions(dbapi_connection, _record):
            dbapi_connection.isolation_level = None

        @event.listens_for(engine.sync_engine, "begin")
        def _emit_begin(conn):
            conn.exec_driver_sql("BEGIN")

    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())

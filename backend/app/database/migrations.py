"""Migration helpers and the startup guard.

The application never migrates an existing database by itself. It only:
 * creates the schema when the database is completely empty (nothing to lose), and
 * refuses to start when an existing database is not at the code's expected revision,
   telling the operator which explicit command to run.
"""
import asyncio
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
BASELINE_REVISION = "0001"


class DatabaseNotReady(RuntimeError):
    """The database exists but is not at the revision this code requires."""


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    if url:
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


async def current_revision(engine: AsyncEngine) -> tuple[set[str], str | None]:
    """Return (application tables present, stamped revision or None)."""
    async with engine.connect() as conn:
        tables = await conn.run_sync(lambda c: set(inspect(c).get_table_names()))
        revision = None
        if "alembic_version" in tables:
            revision = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar()
    return tables - {"alembic_version"}, revision


async def upgrade_to_head(url: str) -> None:
    """Run `alembic upgrade head` (in a worker thread: Alembic drives its own event loop)."""
    await asyncio.to_thread(command.upgrade, alembic_config(url), "head")


async def ensure_database_ready(engine: AsyncEngine) -> None:
    head = head_revision()
    app_tables, revision = await current_revision(engine)

    if not app_tables and revision is None:
        logger.info("Empty database: creating schema at revision %s", head)
        await upgrade_to_head(engine.url.render_as_string(hide_password=False))
        return

    if revision == head:
        return

    if revision is None:
        raise DatabaseNotReady(
            "The database has tables but is not under migration control. After checking it matches the "
            f"baseline schema and taking a verified backup, run: alembic stamp {BASELINE_REVISION}; "
            "then: alembic upgrade head   (from the backend folder). Nothing was changed."
        )
    raise DatabaseNotReady(
        f"The database is at revision {revision!r} but this version of the code requires {head!r}. "
        "After taking a verified backup, run: alembic upgrade head   (from the backend folder). "
        "Nothing was changed."
    )

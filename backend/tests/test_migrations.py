"""Alembic migrations and the startup guard, tested on throwaway SQLite files only.

The legacy fixtures reproduce the shape of the developer database (pre-Alembic schema, naive
text timestamps, JSON as text, seeded-looking rows with missing folders). Real data is never used.
"""
import asyncio
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine

from app.database.migrations import (
    BACKEND_DIR,
    DatabaseNotReady,
    alembic_config,
    ensure_database_ready,
    head_revision,
)
from app.models import Base

FIXTURE_SQL = Path(__file__).parent / "fixtures" / "pre_alembic_schema.sql"

ORIGINAL_COLUMNS = {
    "projects": "id,name,description,root_path,is_indexed,languages,file_count,last_indexed_at,created_at,updated_at",
    "conversations": "id,project_id,title,created_at,updated_at",
    "messages": "id,conversation_id,sender,content,citations,plan_steps,created_at,updated_at",
    "project_files": "id,project_id,file_path,file_name,file_size_bytes,language,last_scanned_at,created_at,updated_at",
}
NEW_INDEXES = {
    "ux_projects_name_lower",
    "ux_project_files_project_path",
    "ix_conversations_project_id",
    "ix_messages_conversation_id",
}


def url_for(path: Path) -> str:
    return f"sqlite+aiosqlite:///{path.as_posix()}"


async def alembic_run(fn, db: Path, *args, script_location: Path | None = None):
    cfg = alembic_config(url_for(db))
    if script_location:
        cfg.set_main_option("script_location", str(script_location))
    await asyncio.to_thread(fn, cfg, *args)


def make_legacy_db(path: Path, rows: bool = True, names=("seeded-one", "seeded-two", "kept-three")) -> None:
    """A database exactly as the pre-Alembic app left it: no alembic_version table."""
    conn = sqlite3.connect(path)
    conn.executescript(FIXTURE_SQL.read_text(encoding="utf-8"))
    if rows:
        ts = "2026-09-23 09:44:42.224668"
        for i, name in enumerate(names):
            conn.execute(
                "INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    f"pid-{i}",
                    name,
                    f"invented description {i}",
                    f"C:\\somewhere\\workspaces\\{name}",
                    1 if i < 2 else 0,
                    json.dumps(["Python", "SQLAlchemy"]),
                    24 + i,
                    ts if i < 2 else None,
                    ts,
                    ts,
                ),
            )
        conn.execute("INSERT INTO conversations VALUES ('c1','pid-0','Chat',?,?)", (ts, ts))
        conn.execute("INSERT INTO messages VALUES ('m1','c1','user','héllo ✓','[]','[]',?,?)", (ts, ts))
        conn.execute("INSERT INTO project_files VALUES ('f1','pid-0','app/main.py','main.py',10,'python',?,?,?)", (ts, ts, ts))
    conn.commit()
    conn.close()


def snapshot(path: Path) -> dict:
    """Every original column of every row, per table (a value-for-value fingerprint)."""
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return {
            t: conn.execute(f"SELECT {cols} FROM {t} ORDER BY id").fetchall() for t, cols in ORIGINAL_COLUMNS.items()
        }
    finally:
        conn.close()


def table_shape(path: Path) -> dict:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        shape = {}
        for (t,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('alembic_version') AND name NOT LIKE 'sqlite_%'"):
            cols = [tuple(r[1:]) for r in conn.execute(f"PRAGMA table_info({t})")]
            fks = sorted(tuple(r[2:]) for r in conn.execute(f"PRAGMA foreign_key_list({t})"))
            shape[t] = (cols, fks)
        return shape
    finally:
        conn.close()


def names(path: Path, kind: str) -> set[str]:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type=?", (kind,)) if not r[0].startswith("sqlite_")}
    finally:
        conn.close()


def columns(path: Path, table: str) -> list[str]:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    finally:
        conn.close()


def revision_of(path: Path) -> str | None:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='alembic_version'").fetchone():
            return None
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integrity_ok(path: Path) -> None:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        conn.close()


# --- baseline ----------------------------------------------------------------------------

async def test_baseline_revision_reproduces_the_pre_alembic_schema_exactly(tmp_path):
    legacy = tmp_path / "legacy.db"
    make_legacy_db(legacy, rows=False)
    fresh = tmp_path / "fresh.db"
    await alembic_run(command.upgrade, fresh, "0001")
    assert table_shape(fresh) == table_shape(legacy)


async def test_there_is_a_single_linear_history_ending_at_0002():
    assert head_revision() == "0002"


@pytest.mark.filterwarnings("ignore:.*expression-based index.*")
async def test_head_schema_matches_the_orm_models_with_no_drift(tmp_path):
    # Alembic cannot reflect the case-insensitive name index on SQLite, so that index is covered by
    # explicit behaviour tests in test_integrity.py instead of by this comparison.
    db = tmp_path / "fresh.db"
    await alembic_run(command.upgrade, db, "head")
    engine = create_engine(f"sqlite:///{db.as_posix()}")
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn, opts={"compare_type": True})
            diff = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()
    assert diff == [], f"models and migrations disagree: {diff}"


# --- upgrading an existing (legacy) database ---------------------------------------------

async def test_legacy_database_is_stamped_then_upgraded_without_changing_any_value(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    before = snapshot(db)
    assert revision_of(db) is None

    await alembic_run(command.stamp, db, "0001")
    assert revision_of(db) == "0001"
    assert snapshot(db) == before, "stamping must not touch data"

    await alembic_run(command.upgrade, db, "head")
    assert revision_of(db) == "0002"
    assert snapshot(db) == before, "every original value of every row must be identical after upgrade"
    integrity_ok(db)

    conn = sqlite3.connect(db)
    try:
        assert {r[0] for r in conn.execute("SELECT origin FROM projects")} == {"unclassified"}
        assert conn.execute("SELECT count(*) FROM projects WHERE archived_at IS NOT NULL OR last_scanned_at IS NOT NULL").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM project_files WHERE file_hash IS NOT NULL").fetchone()[0] == 0
    finally:
        conn.close()
    assert NEW_INDEXES <= names(db, "index")


async def test_upgrade_does_not_invent_or_correct_metadata(tmp_path):
    """Phase 3a must not alter the invented stored values; correcting them is a separate approval."""
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    await alembic_run(command.stamp, db, "0001")
    await alembic_run(command.upgrade, db, "head")
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT is_indexed, file_count, languages, description FROM projects ORDER BY id").fetchall()
    finally:
        conn.close()
    assert rows[0] == (1, 24, json.dumps(["Python", "SQLAlchemy"]), "invented description 0")


async def test_upgrade_twice_is_a_no_op(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    await alembic_run(command.stamp, db, "0001")
    await alembic_run(command.upgrade, db, "head")
    after_first = (snapshot(db), table_shape(db))
    await alembic_run(command.upgrade, db, "head")
    assert (snapshot(db), table_shape(db)) == after_first
    assert revision_of(db) == "0002"


async def test_downgrade_restores_the_original_schema_and_every_value(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    original_shape = table_shape(db)
    before = snapshot(db)
    await alembic_run(command.stamp, db, "0001")
    await alembic_run(command.upgrade, db, "head")

    await alembic_run(command.downgrade, db, "0001")
    assert revision_of(db) == "0001"
    assert snapshot(db) == before
    assert table_shape(db) == original_shape
    assert not (NEW_INDEXES & names(db, "index"))
    integrity_ok(db)


# --- safety nets -------------------------------------------------------------------------

async def test_preflight_refuses_names_that_differ_only_by_case_and_changes_nothing(tmp_path):
    db = tmp_path / "dups.db"
    make_legacy_db(db, names=("Foo", "foo", "bar"))
    await alembic_run(command.stamp, db, "0001")
    before_hash, before = file_hash(db), snapshot(db)

    with pytest.raises(Exception) as exc:
        await alembic_run(command.upgrade, db, "head")
    assert "aborted before changing anything" in str(exc.value)

    assert revision_of(db) == "0001"
    assert snapshot(db) == before
    assert columns(db, "projects") == ORIGINAL_COLUMNS["projects"].split(",")
    assert file_hash(db) == before_hash, "the database file must be byte-identical after an aborted migration"


async def test_a_failing_migration_rolls_back_completely(tmp_path):
    scripts = tmp_path / "scripts"
    (scripts / "versions").mkdir(parents=True)
    shutil.copy(BACKEND_DIR / "alembic" / "env.py", scripts / "env.py")
    shutil.copy(BACKEND_DIR / "alembic" / "script.py.mako", scripts / "script.py.mako")
    (scripts / "versions" / "9001_boom.py").write_text(
        "from alembic import op\nimport sqlalchemy as sa\n"
        "revision='9001'\ndown_revision=None\nbranch_labels=None\ndepends_on=None\n"
        "def upgrade():\n"
        "    op.create_table('half_done', sa.Column('id', sa.Integer(), primary_key=True))\n"
        "    op.execute('INSERT INTO half_done VALUES (1)')\n"
        "    raise RuntimeError('simulated failure after DDL')\n"
        "def downgrade():\n    pass\n",
        encoding="utf-8",
    )
    db = tmp_path / "rollback.db"
    with pytest.raises(Exception) as exc:
        await alembic_run(command.upgrade, db, "head", script_location=scripts)
    assert "simulated failure" in str(exc.value)

    conn = sqlite3.connect(db)
    try:
        leftover = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    finally:
        conn.close()
    assert "half_done" not in leftover, f"partial DDL survived the failure: {leftover}"
    assert revision_of(db) is None


# --- startup guard -----------------------------------------------------------------------

async def _engine(path: Path):
    return create_async_engine(url_for(path))


async def test_guard_builds_the_schema_on_a_completely_empty_database(tmp_path):
    db = tmp_path / "empty.db"
    engine = await _engine(db)
    try:
        await ensure_database_ready(engine)
    finally:
        await engine.dispose()
    assert revision_of(db) == "0002"
    assert {"projects", "project_files", "conversations", "messages"} <= names(db, "table")


async def test_guard_refuses_an_unstamped_legacy_database_and_leaves_it_untouched(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    before = file_hash(db)
    engine = await _engine(db)
    try:
        with pytest.raises(DatabaseNotReady) as exc:
            await ensure_database_ready(engine)
    finally:
        await engine.dispose()
    assert "alembic stamp 0001" in str(exc.value)
    assert file_hash(db) == before


async def test_guard_refuses_a_database_behind_head_and_leaves_it_untouched(tmp_path):
    db = tmp_path / "behind.db"
    make_legacy_db(db)
    await alembic_run(command.stamp, db, "0001")
    before = file_hash(db)
    engine = await _engine(db)
    try:
        with pytest.raises(DatabaseNotReady) as exc:
            await ensure_database_ready(engine)
    finally:
        await engine.dispose()
    assert "alembic upgrade head" in str(exc.value)
    assert file_hash(db) == before


async def test_guard_accepts_a_database_at_head(tmp_path):
    db = tmp_path / "ok.db"
    make_legacy_db(db)
    await alembic_run(command.stamp, db, "0001")
    await alembic_run(command.upgrade, db, "head")
    before = file_hash(db)
    engine = await _engine(db)
    try:
        await ensure_database_ready(engine)
    finally:
        await engine.dispose()
    assert file_hash(db) == before

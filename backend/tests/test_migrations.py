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


async def test_there_is_a_single_linear_history_ending_at_0004():
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(alembic_config())
    assert head_revision() == "0004"
    assert script.get_heads() == ["0004"], "there must be exactly one head (no branches)"
    assert [r.revision for r in script.walk_revisions()] == ["0004", "0003", "0002", "0001"]
    assert [r.down_revision for r in script.walk_revisions()] == ["0003", "0002", "0001", None]



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
    assert revision_of(db) == "0004"
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
    assert revision_of(db) == "0004"



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
    assert revision_of(db) == "0004"
    assert {"projects", "project_files", "conversations", "messages", "code_chunks", "embeddings"} <= names(db, "table")
    assert {"status", "grounding"} <= set(columns(db, "messages"))



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


# --- 0003: grounded answers (messages.status, messages.grounding) -----------------------------------------------------------
# Every database here is a throwaway file under pytest's tmp_path. Migration 0003 is never run against real data.

NEW_MESSAGE_COLUMNS = ["status", "grounding"]


def message_column_info(path: Path) -> dict:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return {r[1]: {"type": r[2].upper(), "notnull": r[3], "default": r[4]} for r in conn.execute("PRAGMA table_info(messages)")}
    finally:
        conn.close()


async def db_at_0002(tmp_path: Path, name: str = "at0002.db") -> Path:
    db = tmp_path / name
    make_legacy_db(db)
    await alembic_run(command.stamp, db, "0001")
    await alembic_run(command.upgrade, db, "0002")
    assert revision_of(db) == "0002"
    return db


def all_shapes_except_messages(path: Path) -> dict:
    return {t: shape for t, shape in table_shape(path).items() if t != "messages"}


async def test_0003_adds_exactly_two_nullable_columns_with_the_agreed_types(tmp_path):
    db = await db_at_0002(tmp_path)
    before_columns = columns(db, "messages")
    await alembic_run(command.upgrade, db, "0003")
    assert revision_of(db) == "0003"
    assert columns(db, "messages") == before_columns + NEW_MESSAGE_COLUMNS
    info = message_column_info(db)
    assert info["status"]["type"] == "VARCHAR(24)" and info["status"]["notnull"] == 0 and info["status"]["default"] is None
    assert info["grounding"]["type"] == "JSON" and info["grounding"]["notnull"] == 0 and info["grounding"]["default"] is None


async def test_0003_changes_no_other_table_and_no_existing_message_column(tmp_path):
    db = await db_at_0002(tmp_path)
    others_before, shape_before = all_shapes_except_messages(db), dict(table_shape(db)["messages"][0] and {"cols": table_shape(db)["messages"][0]})
    snap_before = snapshot(db)
    await alembic_run(command.upgrade, db, "0003")
    assert all_shapes_except_messages(db) == others_before
    assert table_shape(db)["messages"][0][: len(shape_before["cols"])] == shape_before["cols"]
    assert snapshot(db) == snap_before, "every value of every original column must be identical"
    assert NEW_INDEXES <= names(db, "index"), "the indexes of 0002 must survive"
    integrity_ok(db)


async def test_existing_messages_become_legacy_with_null_status_and_grounding_and_nothing_is_back_filled(tmp_path):
    db = await db_at_0002(tmp_path)
    await alembic_run(command.upgrade, db, "0003")
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("SELECT id, content, status, grounding FROM messages").fetchall()
    finally:
        conn.close()
    assert rows == [("m1", "héllo ✓", None, None)]


async def test_0003_contains_no_data_statements():
    source = (BACKEND_DIR / "alembic" / "versions" / "0003_message_grounding.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in ("op.execute", "UPDATE", "INSERT", "DELETE", "bulk_insert", "drop_table", "create_table", "drop_index", "create_index"):
        assert forbidden not in code, f"0003 must only add and remove its two columns, but contains {forbidden!r}"


async def test_new_columns_store_and_return_json_and_unicode(tmp_path):
    db = await db_at_0002(tmp_path)
    await alembic_run(command.upgrade, db, "0003")
    payload = {"version": 1, "citations": [{"excerpt_id": "E1", "path": "app/ü.py", "start_line": 3, "status": "verified"}]}
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO messages (id, conversation_id, sender, content, citations, plan_steps, created_at, updated_at, status, grounding) "
            "VALUES ('m2','c1','assistant','answer','[]','[]','2026-10-21 00:00:00','2026-10-21 00:00:00','answered_verified',?)",
            (json.dumps(payload),),
        )
        conn.commit()
        status, grounding = conn.execute("SELECT status, grounding FROM messages WHERE id='m2'").fetchone()
    finally:
        conn.close()
    assert status == "answered_verified" and json.loads(grounding) == payload


async def test_downgrade_removes_only_the_two_new_columns_and_keeps_all_other_data(tmp_path):
    db = await db_at_0002(tmp_path)
    shape_0002, snap_0002 = table_shape(db), snapshot(db)
    await alembic_run(command.upgrade, db, "0003")
    conn = sqlite3.connect(db)  # a grounded message written while at 0003 must lose only its two new values
    try:
        conn.execute(
            "INSERT INTO messages (id, conversation_id, sender, content, citations, plan_steps, created_at, updated_at, status, grounding) "
            "VALUES ('m2','c1','assistant','kept text','[]','[]','2026-10-21 00:00:00','2026-10-21 00:00:00','answered_unverified','{\"version\": 1}')"
        )
        conn.commit()
    finally:
        conn.close()

    await alembic_run(command.downgrade, db, "0002")

    assert revision_of(db) == "0002"
    assert table_shape(db) == shape_0002, "the schema must be exactly what it was at 0002"
    assert columns(db, "messages") == ORIGINAL_COLUMNS["messages"].split(",")
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT content FROM messages WHERE id='m2'").fetchone() == ("kept text",)
    finally:
        conn.close()
    assert {k: v for k, v in snapshot(db).items() if k != "messages"} == {k: v for k, v in snap_0002.items() if k != "messages"}
    assert [r for r in snapshot(db)["messages"] if r[0] == "m1"] == snap_0002["messages"]
    assert NEW_INDEXES <= names(db, "index")
    integrity_ok(db)


async def test_upgrade_downgrade_upgrade_round_trips(tmp_path):
    db = await db_at_0002(tmp_path)
    shape_0002 = table_shape(db)
    await alembic_run(command.upgrade, db, "head")
    shape_0004 = table_shape(db)
    await alembic_run(command.downgrade, db, "0002")
    assert table_shape(db) == shape_0002
    await alembic_run(command.upgrade, db, "head")
    assert table_shape(db) == shape_0004 and revision_of(db) == "0004"
    integrity_ok(db)


async def test_full_downgrade_from_head_still_restores_the_original_schema(tmp_path):
    db = tmp_path / "legacy.db"
    make_legacy_db(db)
    original_shape, before = table_shape(db), snapshot(db)
    await alembic_run(command.stamp, db, "0001")
    await alembic_run(command.upgrade, db, "head")
    await alembic_run(command.downgrade, db, "0001")
    assert table_shape(db) == original_shape and snapshot(db) == before and revision_of(db) == "0001"


async def test_guard_refuses_a_database_still_at_0002_and_leaves_it_untouched(tmp_path):
    """After this release the app will not start on a 0002 database until `alembic upgrade head` is run on purpose."""
    db = await db_at_0002(tmp_path)
    before = file_hash(db)
    engine = await _engine(db)
    try:
        with pytest.raises(DatabaseNotReady) as exc:
            await ensure_database_ready(engine)
    finally:
        await engine.dispose()
    assert "alembic upgrade head" in str(exc.value)
    assert file_hash(db) == before, "the guard must never migrate by itself"
    assert "status" not in columns(db, "messages")


async def test_models_declare_the_new_columns_as_nullable():
    from app.models.conversation import Message

    status, grounding = Message.__table__.c.status, Message.__table__.c.grounding
    assert status.nullable and grounding.nullable
    assert status.type.length == 24 and type(grounding.type).__name__ == "JSON"
    assert Message.__table__.c.plan_steps.nullable is False, "plan_steps stays as it was"


async def test_every_migration_test_in_this_file_uses_a_throwaway_database(tmp_path):
    """The real database is never a migration target: alembic_config always receives an explicit tmp url."""
    db = await db_at_0002(tmp_path)
    assert tmp_path in db.parents
    assert Path(BACKEND_DIR / "stackpilot.db").resolve() != db.resolve()


# --- 0004: AST code_chunks and embeddings ---------------------------------------------------

async def test_0004_creates_code_chunks_and_embeddings_tables(tmp_path):
    db = tmp_path / "test0004.db"
    await alembic_run(command.upgrade, db, "0004")
    assert revision_of(db) == "0004"
    assert {"code_chunks", "embeddings"} <= names(db, "table")
    assert {"file_id", "project_id", "chunk_index", "chunk_type", "symbol_name", "start_line", "end_line", "content", "metadata_json"} <= set(columns(db, "code_chunks"))
    assert {"chunk_id", "model_name", "dimensions", "vector"} <= set(columns(db, "embeddings"))
    assert "ux_code_chunks_file_chunk_index" in names(db, "index")
    assert "ux_embeddings_chunk_model" in names(db, "index")
    assert "ux_project_files_id_project_id" in names(db, "index")


async def test_0004_composite_foreign_key_prevents_mismatched_project_file(tmp_path):
    """Enforce that code_chunks cannot associate with a file from a different project."""
    db = tmp_path / "fk_test.db"
    await alembic_run(command.upgrade, db, "0004")
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        # Create 2 projects
        now = "2026-10-21 12:00:00"
        conn.execute("INSERT INTO projects (id, name, root_path, is_indexed, languages, file_count, created_at, updated_at) VALUES ('p1', 'proj1', '/tmp/p1', 0, '[]', 0, ?, ?)", (now, now))
        conn.execute("INSERT INTO projects (id, name, root_path, is_indexed, languages, file_count, created_at, updated_at) VALUES ('p2', 'proj2', '/tmp/p2', 0, '[]', 0, ?, ?)", (now, now))
        # Create file in p1
        conn.execute("INSERT INTO project_files (id, project_id, file_path, file_name, file_size_bytes, language, last_scanned_at, created_at, updated_at) VALUES ('f1', 'p1', 'main.py', 'main.py', 10, 'python', ?, ?, ?)", (now, now, now))
        conn.commit()

        # Valid chunk: file f1 in project p1
        conn.execute("INSERT INTO code_chunks (id, project_id, file_id, chunk_index, chunk_type, symbol_name, start_line, end_line, content, metadata_json, created_at, updated_at) VALUES ('c1', 'p1', 'f1', 0, 'function', 'test', 1, 5, 'def test(): pass', '{}', ?, ?)", (now, now))
        conn.commit()

        # Invalid chunk: file f1 associated with mismatched project p2
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO code_chunks (id, project_id, file_id, chunk_index, chunk_type, symbol_name, start_line, end_line, content, metadata_json, created_at, updated_at) VALUES ('c2', 'p2', 'f1', 0, 'function', 'test2', 1, 5, 'def test2(): pass', '{}', ?, ?)", (now, now))
            conn.commit()
    finally:
        conn.close()


async def test_0004_allows_multiple_models_per_chunk_and_rejects_duplicates(tmp_path):
    """Embeddings table allows multiple models per chunk, but rejects duplicate model for same chunk."""
    db = tmp_path / "embed_test.db"
    await alembic_run(command.upgrade, db, "0004")
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        now = "2026-10-21 12:00:00"
        conn.execute("INSERT INTO projects (id, name, root_path, is_indexed, languages, file_count, created_at, updated_at) VALUES ('p1', 'proj1', '/tmp/p1', 0, '[]', 0, ?, ?)", (now, now))
        conn.execute("INSERT INTO project_files (id, project_id, file_path, file_name, file_size_bytes, language, last_scanned_at, created_at, updated_at) VALUES ('f1', 'p1', 'main.py', 'main.py', 10, 'python', ?, ?, ?)", (now, now, now))
        conn.execute("INSERT INTO code_chunks (id, project_id, file_id, chunk_index, chunk_type, symbol_name, start_line, end_line, content, metadata_json, created_at, updated_at) VALUES ('c1', 'p1', 'f1', 0, 'function', 'test', 1, 5, 'def test(): pass', '{}', ?, ?)", (now, now))
        conn.commit()

        # Insert model 1
        conn.execute("INSERT INTO embeddings (id, chunk_id, model_name, dimensions, vector, created_at) VALUES ('e1', 'c1', 'openai-small', 1536, '[0.1, 0.2]', ?)", (now,))
        # Insert model 2 for same chunk (allowed)
        conn.execute("INSERT INTO embeddings (id, chunk_id, model_name, dimensions, vector, created_at) VALUES ('e2', 'c1', 'gemini-embed', 768, '[0.3, 0.4]', ?)", (now,))
        conn.commit()

        # Duplicate model 1 for same chunk (rejected by unique constraint ux_embeddings_chunk_model)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO embeddings (id, chunk_id, model_name, dimensions, vector, created_at) VALUES ('e3', 'c1', 'openai-small', 1536, '[0.5, 0.6]', ?)", (now,))
            conn.commit()
    finally:
        conn.close()


async def test_0004_downgrade_to_0003_removes_tables_and_preserves_other_data(tmp_path):
    db = tmp_path / "downgrade_test.db"
    await alembic_run(command.upgrade, db, "0004")
    assert revision_of(db) == "0004"
    assert {"code_chunks", "embeddings"} <= names(db, "table")

    await alembic_run(command.downgrade, db, "0003")
    assert revision_of(db) == "0003"
    assert "code_chunks" not in names(db, "table")
    assert "embeddings" not in names(db, "table")
    assert "ux_project_files_id_project_id" not in names(db, "index")
    integrity_ok(db)


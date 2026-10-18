"""Database-level integrity added in Phase 3a: enforced foreign keys, cascades, UTC timestamps,
lazy loading and the new unique indexes. Everything runs on the per-session sandbox database."""
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.exc import IntegrityError

from app.database import AsyncSessionLocal, engine
from app.models import Conversation, Message, Project, ProjectFile
from app.models.base import UTCDateTime


def _project(name: str | None = None, **kw) -> Project:
    return Project(
        id=str(uuid.uuid4()),
        name=name or f"i-{uuid.uuid4().hex[:8]}",
        root_path="/nowhere",
        is_indexed=False,
        languages=[],
        file_count=0,
        **kw,
    )


# --- foreign keys & cascade --------------------------------------------------------------

async def test_sqlite_foreign_keys_are_enforced_on_application_connections():
    async with engine.connect() as conn:
        assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 1


async def test_orphan_rows_are_rejected():
    async with AsyncSessionLocal() as session:
        session.add(Message(conversation_id="no-such-conversation", sender="user", content="x", citations=[], plan_steps=[]))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_deleting_a_project_through_the_api_cascades_to_every_child_row(async_client, project):
    async with AsyncSessionLocal() as session:
        conv = Conversation(id=str(uuid.uuid4()), project_id=project["id"], title="t")
        session.add(conv)
        await session.flush()
        session.add(Message(conversation_id=conv.id, sender="user", content="hi", citations=[], plan_steps=[]))
        session.add(ProjectFile(project_id=project["id"], file_path="a.py", file_name="a.py", file_size_bytes=1, language="python"))
        await session.commit()

    assert (await async_client.delete(f"/api/projects/{project['id']}")).status_code == 204

    async with AsyncSessionLocal() as session:
        pid = {"p": project["id"]}
        assert (await session.execute(text("SELECT count(*) FROM projects WHERE id=:p"), pid)).scalar() == 0
        assert (await session.execute(text("SELECT count(*) FROM conversations WHERE project_id=:p"), pid)).scalar() == 0
        assert (await session.execute(text("SELECT count(*) FROM project_files WHERE project_id=:p"), pid)).scalar() == 0
        assert (await session.execute(text("SELECT count(*) FROM messages WHERE content='hi'"))).scalar() == 0


# --- loading behaviour -------------------------------------------------------------------

async def test_loading_projects_does_not_load_files_or_conversations(project):
    async with AsyncSessionLocal() as session:
        session.add(ProjectFile(project_id=project["id"], file_path="x.py", file_name="x.py", file_size_bytes=1, language="python"))
        session.add(Conversation(id=str(uuid.uuid4()), project_id=project["id"], title="t"))
        await session.commit()

    statements: list[str] = []

    def count(conn, cursor, statement, *a):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", count)
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(select(Project))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count)
    assert len(statements) == 1, statements


# --- UTC timestamps ----------------------------------------------------------------------

async def test_api_timestamps_carry_an_explicit_utc_offset(async_client, project):
    created = (await async_client.get(f"/api/projects/{project['id']}")).json()["created_at"]
    parsed = datetime.fromisoformat(created)
    assert parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0)


async def test_naive_text_stored_by_the_legacy_app_is_read_back_as_utc():
    pid = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                "INSERT INTO projects (id,name,root_path,is_indexed,languages,file_count,last_indexed_at,created_at,updated_at,origin) "
                "VALUES (:id,:n,'/x',0,'[]',0,'2026-09-23 09:44:42.220945','2026-09-23 09:44:42.224668','2026-09-23 09:44:42.224673','unclassified')"
            ),
            {"id": pid, "n": f"legacy-{pid[:6]}"},
        )
        await session.commit()
        row = await session.get(Project, pid)
    assert row.created_at == datetime(2026, 9, 23, 9, 44, 42, 224668, tzinfo=timezone.utc)
    assert row.last_indexed_at.tzinfo is not None


def test_utc_type_converts_offsets_and_refuses_naive_values():
    t = UTCDateTime()
    ist = timezone(timedelta(hours=5, minutes=30))
    stored = t.process_bind_param(datetime(2026, 1, 1, 12, 0, tzinfo=ist), None)
    assert stored == datetime(2026, 1, 1, 6, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        t.process_bind_param(datetime(2026, 1, 1, 12, 0), None)


# --- new columns and unique indexes ------------------------------------------------------

async def test_origin_is_user_for_new_projects_and_unclassified_when_not_supplied(async_client, project):
    assert (await async_client.get(f"/api/projects/{project['id']}")).json()["origin"] == "user"
    async with AsyncSessionLocal() as session:
        p = _project()
        session.add(p)
        await session.commit()
        await session.refresh(p)
    assert p.origin == "unclassified"


async def test_project_names_are_unique_ignoring_case_at_the_database_level():
    async with AsyncSessionLocal() as session:
        session.add(_project("CaseName"))
        await session.commit()
    async with AsyncSessionLocal() as session:
        session.add(_project("casename"))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_api_rejects_case_variants_of_an_existing_name_with_409(async_client):
    assert (await async_client.post("/api/projects", json={"name": "ApiCase", "source_type": "blank"})).status_code == 201
    assert (await async_client.post("/api/projects", json={"name": "apicase", "source_type": "blank"})).status_code == 409


async def test_a_file_path_can_only_be_registered_once_per_project(project):
    def row():
        return ProjectFile(project_id=project["id"], file_path="dup.py", file_name="dup.py", file_size_bytes=1, language="python")

    async with AsyncSessionLocal() as session:
        session.add(row())
        await session.commit()
    async with AsyncSessionLocal() as session:
        session.add(row())
        with pytest.raises(IntegrityError):
            await session.commit()

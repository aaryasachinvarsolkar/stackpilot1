"""Verified defects from the Phase 0 audit, expressed as tests.

Each test asserts the CORRECT behaviour and is marked as a strict xfail because the
defect still exists. They are not skipped or weakened: once the underlying bug is
fixed the test XPASSes, strict mode turns that into a failure, and the xfail marker
must be removed so the test becomes a normal regression guard.

All filesystem activity stays inside the per-session sandbox directory.
"""
from pathlib import Path

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.project import Project


def known_bug(ref: str, why: str):
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"{ref}: {why}")


async def _create(client, name: str) -> dict:
    res = await client.post("/api/projects", json={"name": name, "source_type": "blank"})
    assert res.status_code == 201, res.text
    return res.json()


# --- Behaviour that works today and must be preserved -----------------------------------

async def test_reading_a_scaffolded_file_inside_the_project_works(async_client):
    proj = await _create(async_client, "kb-control-read")
    res = await async_client.get(f"/api/projects/{proj['id']}/files/content", params={"path": "app/main.py"})
    assert res.status_code == 200
    assert "FastAPI(" in res.json()["content"]


async def test_writing_a_file_inside_the_project_persists_to_disk(async_client):
    proj = await _create(async_client, "kb-control-write")
    res = await async_client.put(
        f"/api/projects/{proj['id']}/files/content", json={"path": "notes/hello.txt", "content": "hi"}
    )
    assert res.status_code == 200
    assert (Path(proj["root_path"]) / "notes" / "hello.txt").read_text(encoding="utf-8") == "hi"


# --- Known defects ----------------------------------------------------------------------

@known_bug("F1", "absolute path escapes the project root on read")
async def test_f1_cannot_read_absolute_path_outside_project(async_client, sandbox):
    secret = sandbox / "outside-secret.txt"
    secret.write_text("TOP-SECRET", encoding="utf-8")
    proj = await _create(async_client, "kb-f1-read")
    res = await async_client.get(f"/api/projects/{proj['id']}/files/content", params={"path": str(secret)})
    assert res.status_code in (400, 403, 404), f"got {res.status_code}"
    assert "TOP-SECRET" not in res.text


@known_bug("F1", "absolute path escapes the project root on write")
async def test_f1_cannot_write_absolute_path_outside_project(async_client, sandbox):
    target = sandbox / "outside-written.txt"
    proj = await _create(async_client, "kb-f1-write")
    res = await async_client.put(
        f"/api/projects/{proj['id']}/files/content", json={"path": str(target), "content": "pwned"}
    )
    assert res.status_code in (400, 403, 404), f"got {res.status_code}"
    assert not target.exists(), "file was written outside the project root"


@known_bug("F2", "project name is used unvalidated as a directory name")
async def test_f2_project_name_cannot_escape_workspaces(async_client, sandbox):
    res = await async_client.post("/api/projects", json={"name": "../kb-escaped", "source_type": "blank"})
    assert res.status_code in (400, 422), f"got {res.status_code}"
    assert not (sandbox / "kb-escaped").exists(), "directory created outside workspaces/"


@known_bug("F3", "saving to an unknown project reports success")
async def test_f3_save_to_unknown_project_is_404(async_client):
    res = await async_client.put(
        "/api/projects/does-not-exist/files/content", json={"path": "a.txt", "content": "x"}
    )
    assert res.status_code == 404, f"got {res.status_code}: {res.text}"


@known_bug("F3b", "unknown project returns invented demo tree")
async def test_f3b_tree_of_unknown_project_is_404(async_client):
    res = await async_client.get("/api/projects/does-not-exist/files/tree")
    assert res.status_code == 404, f"got {res.status_code}"


@known_bug("F3b", "unknown file returns invented content")
async def test_f3b_missing_file_is_404(async_client):
    proj = await _create(async_client, "kb-f3b-missing")
    res = await async_client.get(
        f"/api/projects/{proj['id']}/files/content", params={"path": "no/such/file.py"}
    )
    assert res.status_code == 404, f"got {res.status_code}"


@known_bug("F4", "chat answers for an unknown project with canned text")
async def test_f4_chat_on_unknown_project_is_404(async_client):
    res = await async_client.post("/api/projects/does-not-exist/chat", json={"message": "hello"})
    assert res.status_code == 404, f"got {res.status_code}"


@known_bug("F7", "GET /api/projects creates fake seed projects")
async def test_f7_listing_projects_does_not_create_rows(async_client):
    async with AsyncSessionLocal() as session:  # sandbox DB only
        for row in (await session.execute(select(Project))).scalars().all():
            await session.delete(row)
        await session.commit()
    res = await async_client.get("/api/projects")
    assert res.status_code == 200
    assert res.json() == [], f"listing an empty registry returned {len(res.json())} invented projects"


@known_bug("F6", "FastAPI starter routes.py uses @app without defining it")
def test_f6_fastapi_starter_routes_is_importable():
    from app.api.projects import DEFAULT_STARTER_FILES

    source = DEFAULT_STARTER_FILES["FastAPI + Python"]["app/api/routes.py"]
    try:
        exec(compile(source, "starter/app/api/routes.py", "exec"), {})
    except NameError as exc:
        raise AssertionError(f"starter code fails on import: {exc}") from exc

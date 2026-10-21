"""Regression tests for the defects found in the Phase 0 audit and fixed in Phase 2.

These began life as strict-xfail tests asserting the CORRECT behaviour (F1, F2, F3, F3b, F4, F6,
F7). Phase 2 fixed each defect, the strict xfails turned into failures (XPASS), and the markers
were then removed. The assertions below are unchanged except F6, which now runs a freshly
generated starter project for real instead of exec'ing a template string.

All filesystem activity stays inside the per-session sandbox directory.
"""
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.project import Project


async def _create(client, name: str) -> dict:
    res = await client.post("/api/projects", json={"name": name, "source_type": "blank"})
    assert res.status_code == 201, res.text
    return res.json()


# --- Behaviour that always worked and must be preserved ---------------------------------

async def test_reading_a_scaffolded_file_inside_the_project_works(async_client):
    proj = await _create(async_client, "kb-control-read")
    res = await async_client.get(f"/api/projects/{proj['id']}/files/content", params={"path": "app/main.py"})
    assert res.status_code == 200
    assert "FastAPI(" in res.json()["content"]


async def test_updating_a_file_inside_the_project_persists_to_disk(async_client, save):
    proj = await _create(async_client, "kb-control-write")
    res = await save(proj, "app/main.py", "hi")
    assert res.status_code == 200
    assert (Path(proj["root_path"]) / "app" / "main.py").read_bytes() == b"hi"


# --- Fixed defects ----------------------------------------------------------------------

async def test_f1_cannot_read_absolute_path_outside_project(async_client, sandbox):
    secret = sandbox / "outside-secret.txt"
    secret.write_text("TOP-SECRET", encoding="utf-8")
    proj = await _create(async_client, "kb-f1-read")
    res = await async_client.get(f"/api/projects/{proj['id']}/files/content", params={"path": str(secret)})
    assert res.status_code in (400, 403, 404), f"got {res.status_code}"
    assert "TOP-SECRET" not in res.text


async def test_f1_cannot_write_absolute_path_outside_project(async_client, sandbox):
    target = sandbox / "outside-written.txt"
    proj = await _create(async_client, "kb-f1-write")
    res = await async_client.put(
        f"/api/projects/{proj['id']}/files/content", json={"path": str(target), "content": "pwned"}
    )
    assert res.status_code in (400, 403, 404), f"got {res.status_code}"
    assert not target.exists(), "file was written outside the project root"


async def test_f2_project_name_cannot_escape_workspaces(async_client, sandbox):
    res = await async_client.post("/api/projects", json={"name": "../kb-escaped", "source_type": "blank"})
    assert res.status_code in (400, 422), f"got {res.status_code}"
    assert not (sandbox / "kb-escaped").exists(), "directory created outside workspaces/"


async def test_f3_save_to_unknown_project_is_404(async_client):
    res = await async_client.put(
        "/api/projects/does-not-exist/files/content", json={"path": "a.txt", "content": "x"}
    )
    assert res.status_code == 404, f"got {res.status_code}: {res.text}"


async def test_f3b_tree_of_unknown_project_is_404(async_client):
    res = await async_client.get("/api/projects/does-not-exist/files/tree")
    assert res.status_code == 404, f"got {res.status_code}"


async def test_f3b_missing_file_is_404(async_client):
    proj = await _create(async_client, "kb-f3b-missing")
    res = await async_client.get(
        f"/api/projects/{proj['id']}/files/content", params={"path": "no/such/file.py"}
    )
    assert res.status_code == 404, f"got {res.status_code}"


async def test_f4_chat_on_unknown_project_is_404(async_client):
    res = await async_client.post("/api/projects/does-not-exist/chat", json={"message": "hello"})
    assert res.status_code == 404, f"got {res.status_code}"


async def test_f7_listing_projects_does_not_create_rows(async_client):
    async with AsyncSessionLocal() as session:  # sandbox DB only
        for row in (await session.execute(select(Project))).scalars().all():
            await session.delete(row)
        await session.commit()
    res = await async_client.get("/api/projects")
    assert res.status_code == 200
    assert res.json() == [], f"listing an empty registry returned {len(res.json())} invented projects"


async def test_f6_generated_fastapi_starter_actually_runs(async_client):
    """Generate a real starter project, import its app in a subprocess and call its routes."""
    proj = await _create(async_client, "kb-f6-starter")
    code = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "c = TestClient(app)\n"
        "assert c.get('/').json()['status'] == 'online'\n"
        "assert c.get('/items').json()[0]['name'] == 'Item Alpha'\n"
        "print('STARTER-OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        cwd=proj["root_path"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "STARTER-OK" in result.stdout

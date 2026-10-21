import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.project import Project


def _name() -> str:
    return f"p-{uuid.uuid4().hex[:10]}"


async def test_list_projects_returns_only_real_registered_projects(async_client: AsyncClient, project):
    response = await async_client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    mine = [p for p in data if p["id"] == project["id"]]
    assert len(mine) == 1
    assert {"id", "name", "languages", "file_count", "workspace_exists", "root_path"} <= mine[0].keys()
    assert all(p["name"] not in {"task-manager-service", "auth-microservice"} for p in data)  # no seeding


async def test_create_and_get_project(async_client: AsyncClient):
    name = _name()
    payload = {
        "name": name,
        "description": "Real-time analytics engine with FastAPI",
        "source_type": "blank",
        "template": "FastAPI + Python",
    }
    create_res = await async_client.post("/api/projects", json=payload)
    assert create_res.status_code == 201
    created = create_res.json()
    assert created["name"] == name
    assert "Python" in created["languages"]
    assert created["workspace_exists"] is True
    # file_count must equal the number of files actually written to disk
    on_disk = [p for p in Path(created["root_path"]).rglob("*") if p.is_file()]
    assert created["file_count"] == len(on_disk) > 0

    get_res = await async_client.get(f"/api/projects/{created['id']}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == created["id"]
    assert get_res.json()["name"] == name
    # lookup by name keeps working
    assert (await async_client.get(f"/api/projects/{name}")).json()["id"] == created["id"]


async def test_create_duplicate_project_error(async_client: AsyncClient):
    payload = {"name": _name(), "source_type": "blank"}
    assert (await async_client.post("/api/projects", json=payload)).status_code == 201
    assert (await async_client.post("/api/projects", json=payload)).status_code == 409


async def test_delete_project(async_client: AsyncClient):
    created = (await async_client.post("/api/projects", json={"name": _name(), "source_type": "blank"})).json()

    del_res = await async_client.delete(f"/api/projects/{created['id']}")
    assert del_res.status_code == 204
    assert (await async_client.get(f"/api/projects/{created['id']}")).status_code == 404
    assert (await async_client.delete(f"/api/projects/{created['id']}")).status_code == 404


async def test_delete_unregisters_but_never_deletes_files(async_client: AsyncClient, project):
    root = Path(project["root_path"])
    assert (root / "app" / "main.py").is_file()
    assert (await async_client.delete(f"/api/projects/{project['id']}")).status_code == 204
    assert (root / "app" / "main.py").is_file(), "delete must preserve the user's files"


async def test_get_unknown_project_is_404(async_client: AsyncClient):
    assert (await async_client.get("/api/projects/does-not-exist")).status_code == 404


@pytest.mark.parametrize(
    "bad_name",
    ["../escape", "a/b", "a\\b", "has space", ".hidden", "name.", "con", "NUL", "", "x" * 101, "a:b"],
)
async def test_invalid_project_names_are_rejected_and_create_nothing(async_client, sandbox, bad_name):
    before = sorted(p.name for p in (sandbox / "workspaces").glob("*")) if (sandbox / "workspaces").exists() else []
    res = await async_client.post("/api/projects", json={"name": bad_name, "source_type": "blank"})
    assert res.status_code == 422, res.text
    after = sorted(p.name for p in (sandbox / "workspaces").glob("*")) if (sandbox / "workspaces").exists() else []
    assert before == after
    assert not (sandbox / "escape").exists()


async def test_unknown_template_is_rejected(async_client):
    res = await async_client.post("/api/projects", json={"name": _name(), "template": "Rails"})
    assert res.status_code == 422


@pytest.mark.parametrize("source", ["upload", "git"])
async def test_unimplemented_sources_return_501_and_create_nothing(async_client, sandbox, source):
    name = _name()
    res = await async_client.post("/api/projects", json={"name": name, "source_type": source})
    assert res.status_code == 501
    assert not (sandbox / "workspaces" / name).exists()
    assert (await async_client.get(f"/api/projects/{name}")).status_code == 404


async def test_existing_folder_on_disk_is_never_adopted_or_overwritten(async_client, sandbox):
    name = _name()
    folder = sandbox / "workspaces" / name
    folder.mkdir(parents=True)
    precious = folder / "app" / "main.py"
    precious.parent.mkdir()
    precious.write_text("USER DATA", encoding="utf-8")

    res = await async_client.post("/api/projects", json={"name": name, "source_type": "blank"})
    assert res.status_code == 409
    assert precious.read_text(encoding="utf-8") == "USER DATA"
    assert (await async_client.get(f"/api/projects/{name}")).status_code == 404


async def test_file_count_is_measured_on_disk_not_taken_from_the_database(async_client, project):
    base = project["file_count"]
    # A file appears on disk behind the application's back (the file API only updates existing files).
    extra = Path(project["root_path"]) / "extra" / "new.txt"
    extra.parent.mkdir()
    extra.write_bytes(b"x")
    assert (await async_client.get(f"/api/projects/{project['id']}")).json()["file_count"] == base + 1


async def test_project_whose_folder_is_missing_reports_zero_files_and_workspace_exists_false(async_client, sandbox):
    async with AsyncSessionLocal() as session:
        row = Project(
            id=str(uuid.uuid4()),
            name=_name(),
            root_path=str(sandbox / "workspaces" / "never-created"),
            is_indexed=True,
            languages=["Python"],
            file_count=999,  # stale stored value must not be reported
        )
        session.add(row)
        await session.commit()
        pid = row.id
    data = (await async_client.get(f"/api/projects/{pid}")).json()
    assert data["file_count"] == 0
    assert data["workspace_exists"] is False


async def test_failed_database_write_removes_only_the_folder_just_created(async_client, sandbox, monkeypatch):
    name = _name()

    async def boom(self):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(AsyncSession, "commit", boom)
    res = await async_client.post("/api/projects", json={"name": name, "source_type": "blank"})
    monkeypatch.undo()

    assert res.status_code == 500
    assert not (sandbox / "workspaces" / name).exists()
    async with AsyncSessionLocal() as session:
        assert (await session.execute(select(Project).where(Project.name == name))).first() is None


async def test_listing_projects_is_read_only(async_client):
    async with AsyncSessionLocal() as session:
        for row in (await session.execute(select(Project))).scalars().all():
            await session.delete(row)
        await session.commit()

    assert (await async_client.get("/api/projects")).json() == []
    async with AsyncSessionLocal() as session:
        assert (await session.execute(select(Project))).first() is None

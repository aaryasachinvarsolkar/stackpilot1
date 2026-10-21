import hashlib
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.project import Project


def files_url(project: dict, suffix: str) -> str:
    return f"/api/projects/{project['id']}/files/{suffix}"


# --- tree --------------------------------------------------------------------------------

async def test_get_file_tree(async_client: AsyncClient, project):
    """The tree is the project's real folder: nested, with name/path on every node."""
    res = await async_client.get(files_url(project, "tree"))
    assert res.status_code == 200
    tree = res.json()
    assert isinstance(tree, list) and len(tree) > 0
    assert all("name" in n and "path" in n for n in tree)
    app_dir = next(n for n in tree if n["name"] == "app")
    assert app_dir["type"] == "directory"
    assert "app/main.py" in [c["path"] for c in app_dir["children"] if c["type"] == "file"]


async def test_tree_reflects_disk_and_hides_ignored_entries(async_client: AsyncClient, project):
    root = Path(project["root_path"])
    (root / "node_modules").mkdir()
    (root / "node_modules" / "junk.js").write_text("x", encoding="utf-8")
    (root / ".env").write_text("SECRET=1", encoding="utf-8")
    (root / "added.txt").write_text("hi", encoding="utf-8")

    names = [n["name"] for n in (await async_client.get(files_url(project, "tree"))).json()]
    assert "added.txt" in names
    assert "node_modules" not in names
    assert ".env" not in names


async def test_empty_project_folder_gives_empty_tree_not_demo_data(async_client: AsyncClient, project):
    root = Path(project["root_path"])
    for p in sorted(root.rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    res = await async_client.get(files_url(project, "tree"))
    assert res.status_code == 200
    assert res.json() == []


async def test_project_with_missing_folder_is_404_and_nothing_is_created(async_client: AsyncClient, sandbox):
    folder = sandbox / "workspaces" / "ghost-folder"
    async with AsyncSessionLocal() as session:
        row = Project(
            id=str(uuid.uuid4()), name="ghost-project", root_path=str(folder), is_indexed=False, languages=[], file_count=0
        )
        session.add(row)
        await session.commit()
        pid = row.id

    base = f"/api/projects/{pid}/files"
    assert (await async_client.get(f"{base}/tree")).status_code == 404
    assert (await async_client.get(f"{base}/content", params={"path": "a.py"})).status_code == 404
    assert (await async_client.put(f"{base}/content", json={"path": "a.py", "content": "x"})).status_code == 404
    assert not folder.exists(), "saving must not conjure a missing project folder"


# --- read --------------------------------------------------------------------------------

async def test_get_file_content(async_client: AsyncClient, project):
    res = await async_client.get(files_url(project, "content"), params={"path": "app/api/routes.py"})
    assert res.status_code == 200
    data = res.json()
    assert data["path"] == "app/api/routes.py"
    assert data["file_name"] == "routes.py"
    assert "@router.get" in data["content"]
    assert data["line_count"] > 0
    assert data["language"] == "python"


async def test_missing_file_is_404_not_invented_content(async_client: AsyncClient, project):
    res = await async_client.get(files_url(project, "content"), params={"path": "no/such/file.py"})
    assert res.status_code == 404


async def test_reading_a_directory_is_404(async_client: AsyncClient, project):
    assert (await async_client.get(files_url(project, "content"), params={"path": "app"})).status_code == 404


async def test_binary_file_is_415(async_client: AsyncClient, project):
    (Path(project["root_path"]) / "blob.bin").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    res = await async_client.get(files_url(project, "content"), params={"path": "blob.bin"})
    assert res.status_code == 415


async def test_non_utf8_file_is_415_instead_of_being_silently_corrupted(async_client: AsyncClient, project):
    (Path(project["root_path"]) / "latin1.txt").write_bytes(b"caf\xe9")
    res = await async_client.get(files_url(project, "content"), params={"path": "latin1.txt"})
    assert res.status_code == 415


async def test_oversized_file_read_is_413(async_client: AsyncClient, project, monkeypatch):
    (Path(project["root_path"]) / "big.txt").write_text("x" * 50, encoding="utf-8")
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_BYTES", 10)
    res = await async_client.get(files_url(project, "content"), params={"path": "big.txt"})
    assert res.status_code == 413


# --- write -------------------------------------------------------------------------------

async def test_save_file_content(save, project):
    """Updating an existing file: the response reports the bytes written and the hash of the new content."""
    content = "# Test file content\nprint('hello world')\n"
    res = await save(project, "app/main.py", content)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "saved"
    assert data["path"] == "app/main.py"
    assert data["bytes_written"] == len(content.encode("utf-8"))
    assert data["sha256"] == hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert (Path(project["root_path"]) / "app" / "main.py").read_bytes() == content.encode("utf-8")


async def test_save_overwrites_existing_file_without_leaving_temp_files(save, project):
    target = Path(project["root_path"]) / "app" / "main.py"
    res = await save(project, "app/main.py", "NEW")
    assert res.status_code == 200
    assert target.read_text(encoding="utf-8") == "NEW"
    assert list(target.parent.glob(".sp-*")) == []


async def test_content_round_trips_byte_for_byte_including_crlf_and_unicode(async_client: AsyncClient, save, project):
    content = "line1\r\nline2\r\nünïcode ✓\r\n"
    (Path(project["root_path"]) / "rt.txt").write_bytes(b"placeholder")  # saves update existing files only
    assert (await save(project, "rt.txt", content)).status_code == 200
    assert (Path(project["root_path"]) / "rt.txt").read_bytes() == content.encode("utf-8")
    back = await async_client.get(files_url(project, "content"), params={"path": "rt.txt"})
    assert back.json()["content"] == content


async def test_oversized_save_is_413_and_writes_nothing(async_client: AsyncClient, project, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_BYTES", 10)
    res = await async_client.put(files_url(project, "content"), json={"path": "toobig.txt", "content": "x" * 11})
    assert res.status_code == 413
    assert not (Path(project["root_path"]) / "toobig.txt").exists()


async def test_saving_over_a_directory_is_400(save, project):
    res = await save(project, "app", "x", base_sha256="0" * 64)
    assert res.status_code == 400


# --- containment -------------------------------------------------------------------------

async def test_path_traversal_prevention(async_client: AsyncClient, project):
    """Verify path traversal attempts are rejected with 400 Bad Request."""
    res = await async_client.get(files_url(project, "content"), params={"path": "../../etc/passwd"})
    assert res.status_code == 400
    assert "Path traversal is strictly prohibited" in res.json()["detail"]


@pytest.mark.parametrize(
    "bad_path",
    ["../../etc/passwd", "..\\..\\secret.txt", "app/../../secret.txt", "/etc/passwd", "C:\\Windows\\win.ini", "C:/Windows/win.ini", "x\x00y", "", "."],
)
async def test_read_and_write_reject_unsafe_paths(async_client: AsyncClient, project, sandbox, bad_path):
    got = await async_client.get(files_url(project, "content"), params={"path": bad_path})
    put = await async_client.put(files_url(project, "content"), json={"path": bad_path, "content": "pwned"})
    assert got.status_code == 400
    assert put.status_code == 400
    assert not (sandbox / "secret.txt").exists()


async def test_absolute_path_to_a_real_outside_file_is_rejected_for_read_and_write(async_client, project, sandbox):
    outside = sandbox / f"outside-{uuid.uuid4().hex[:6]}.txt"
    outside.write_text("TOP-SECRET", encoding="utf-8")

    got = await async_client.get(files_url(project, "content"), params={"path": str(outside)})
    assert got.status_code == 400 and "TOP-SECRET" not in got.text

    put = await async_client.put(files_url(project, "content"), json={"path": str(outside), "content": "pwned"})
    assert put.status_code == 400
    assert outside.read_text(encoding="utf-8") == "TOP-SECRET"


async def test_unknown_project_is_404_for_every_file_endpoint(async_client: AsyncClient):
    base = "/api/projects/does-not-exist/files"
    assert (await async_client.get(f"{base}/tree")).status_code == 404
    assert (await async_client.get(f"{base}/content", params={"path": "a.txt"})).status_code == 404
    assert (await async_client.put(f"{base}/content", json={"path": "a.txt", "content": "x"})).status_code == 404

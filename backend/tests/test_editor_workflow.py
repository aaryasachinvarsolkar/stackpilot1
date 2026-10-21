"""The editor's whole file workflow against the real API, using only the isolated test workspace.

The Monaco editor does exactly this: list the tree, open a file from it, edit, save, then read the
file back to check the save. These tests drive that sequence over HTTP and then look at the bytes on
disk, so a "saved" claim in the UI rests on something verified. Cases already covered by
test_files.py (traversal, binary, 413, unknown project) are not repeated here.
"""
import os
import sys
from pathlib import Path
from urllib.parse import quote

import pytest
from httpx import AsyncClient

from app.config import settings


def url(project: dict, suffix: str) -> str:
    return f"/api/projects/{project['id']}/files/{suffix}"


def flatten(nodes):
    for n in nodes:
        if n["type"] == "file":
            yield n
        else:
            yield from flatten(n.get("children") or [])


async def open_file(client: AsyncClient, project: dict, path: str) -> dict:
    res = await client.get(url(project, "content"), params={"path": path})
    assert res.status_code == 200, res.text
    return res.json()


# A well-formed hash that matches no real file, for requests that must be rejected before it is looked at.
ANY_SHA256 = "0" * 64


async def save_file(client: AsyncClient, project: dict, path: str, content: str, base_sha256: str = "current"):
    """Save the way the editor does: read the file's current sha256 and send it back as base_sha256."""
    if base_sha256 == "current":
        base_sha256 = (await open_file(client, project, path))["sha256"]
    return await client.put(url(project, "content"), json={"path": path, "content": content, "base_sha256": base_sha256})


# --- the happy path, end to end --------------------------------------------------------------

async def test_open_edit_save_read_back_matches_disk(async_client: AsyncClient, project):
    tree = (await async_client.get(url(project, "tree"))).json()
    target = next(f for f in flatten(tree) if f["path"] == "app/main.py")

    opened = await open_file(async_client, project, target["path"])
    edited = opened["content"] + "\n# edited in the editor\n"

    saved = await save_file(async_client, project, target["path"], edited)
    assert saved.status_code == 200
    assert saved.json()["bytes_written"] == len(edited.encode("utf-8"))

    back = await open_file(async_client, project, target["path"])
    assert back["content"] == edited
    assert (Path(project["root_path"]) / "app" / "main.py").read_bytes() == edited.encode("utf-8")


async def test_the_tree_size_matches_what_a_read_returns(async_client: AsyncClient, project):
    """Navigation consistency: every file the tree lists opens, and its size is the bytes the read returns."""
    tree = (await async_client.get(url(project, "tree"))).json()
    files = list(flatten(tree))
    assert files, "the starter project should contain files"
    for f in files:
        got = await open_file(async_client, project, f["path"])
        assert got["path"] == f["path"]
        assert len(got["content"].encode("utf-8")) == f["size"]


async def test_project_can_be_opened_by_id_or_by_name_for_file_access(async_client: AsyncClient, project):
    for key in (project["id"], project["name"]):
        res = await async_client.get(f"/api/projects/{key}/files/content", params={"path": "app/main.py"})
        assert res.status_code == 200


async def test_save_then_save_again_keeps_the_last_write_and_leaves_no_temp_files(async_client: AsyncClient, project):
    for text in ("first\n", "second\n", "third\n"):
        assert (await save_file(async_client, project, "app/main.py", text)).status_code == 200
    root = Path(project["root_path"])
    assert (root / "app" / "main.py").read_bytes() == b"third\n"
    assert [p.name for p in root.rglob(".sp-*")] == []


async def test_editing_one_file_does_not_touch_the_others(async_client: AsyncClient, project):
    root = Path(project["root_path"])
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    await save_file(async_client, project, "app/main.py", "changed\n")
    for p, data in before.items():
        if p != root / "app" / "main.py":
            assert p.read_bytes() == data, f"{p} changed although only app/main.py was saved"


async def test_saving_an_empty_buffer_is_allowed_and_reads_back_empty(async_client: AsyncClient, project):
    assert (await save_file(async_client, project, "app/main.py", "")).status_code == 200
    back = await open_file(async_client, project, "app/main.py")
    assert back["content"] == "" and back["line_count"] == 0


# --- file names the tree can hand to the editor ----------------------------------------------

@pytest.mark.parametrize("name", ["my notes.txt", "a&b=c.txt", "hash#1.txt", "per%cent.txt", "ünïcode-ファイル.txt", "plus+sign.txt"])
async def test_awkward_file_names_round_trip_through_the_url(async_client: AsyncClient, project, name):
    """The browser sends paths URL-encoded; names with spaces, '#', '&', '%', '+' or unicode must survive."""
    root = Path(project["root_path"])
    (root / name).write_bytes(b"original\n")

    names = [f["path"] for f in flatten((await async_client.get(url(project, "tree"))).json())]
    assert name in names

    # exactly what the frontend does: encodeURIComponent(path) in the query string
    res = await async_client.get(f"{url(project, 'content')}?path={quote(name, safe='')}")
    assert res.status_code == 200 and res.json()["content"] == "original\n"

    assert (await save_file(async_client, project, name, "edited\n")).status_code == 200
    assert (root / name).read_bytes() == b"edited\n"


async def test_files_in_nested_folders_open_and_save(async_client: AsyncClient, project):
    root = Path(project["root_path"])
    (root / "deep" / "er" / "still").mkdir(parents=True)
    (root / "deep" / "er" / "still" / "leaf.py").write_bytes(b"x = 1\n")
    assert (await open_file(async_client, project, "deep/er/still/leaf.py"))["content"] == "x = 1\n"
    assert (await save_file(async_client, project, "deep/er/still/leaf.py", "x = 2\n")).status_code == 200
    assert (root / "deep" / "er" / "still" / "leaf.py").read_bytes() == b"x = 2\n"


async def test_language_is_reported_for_the_editor(async_client: AsyncClient, project):
    root = Path(project["root_path"])
    (root / "a.ts").write_bytes(b"export {}\n")
    (root / "b.toml").write_bytes(b"k = 1\n")
    assert (await open_file(async_client, project, "a.ts"))["language"] == "typescript"
    assert (await open_file(async_client, project, "b.toml"))["language"] == "toml"


# --- failure handling the editor relies on to avoid false "saved" states ---------------------

async def test_failed_oversized_save_leaves_the_existing_file_unchanged(async_client: AsyncClient, project, monkeypatch):
    root = Path(project["root_path"])
    original = (root / "app" / "main.py").read_bytes()
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_BYTES", max(1, len(original)))
    res = await save_file(async_client, project, "app/main.py", "x" * (len(original) + 50))
    assert res.status_code == 413
    assert isinstance(res.json()["detail"], str) and "limit" in res.json()["detail"]
    assert (root / "app" / "main.py").read_bytes() == original
    assert list(root.rglob(".sp-*")) == []


async def test_rejected_path_gives_a_readable_message_and_writes_nothing(async_client: AsyncClient, project, sandbox):
    res = await save_file(async_client, project, "../escape.txt", "pwned", base_sha256=ANY_SHA256)
    assert res.status_code == 400
    assert isinstance(res.json()["detail"], str) and res.json()["detail"]
    assert not (sandbox / "workspaces" / "escape.txt").exists()
    assert not (Path(project["root_path"]).parent / "escape.txt").exists()


async def test_workspace_folder_deleted_while_editing_is_404_for_save_and_nothing_is_recreated(async_client: AsyncClient, project):
    import shutil

    root = Path(project["root_path"])
    shutil.rmtree(root)
    res = await save_file(async_client, project, "app/main.py", "x", base_sha256=ANY_SHA256)
    assert res.status_code == 404
    assert not root.exists()


async def test_missing_file_on_read_is_404_with_message(async_client: AsyncClient, project):
    res = await async_client.get(url(project, "content"), params={"path": "gone.py"})
    assert res.status_code == 404 and res.json()["detail"]


@pytest.mark.skipif(sys.platform != "win32", reason="replacing a read-only file only fails on Windows")
async def test_save_over_a_read_only_file_fails_cleanly_and_keeps_the_original(async_client: AsyncClient, project):
    import stat

    target = Path(project["root_path"]) / "locked.txt"
    target.write_bytes(b"keep me\n")
    os.chmod(target, stat.S_IREAD)
    try:
        res = await save_file(async_client, project, "locked.txt", "overwritten\n")
        assert res.status_code == 500 and res.json()["detail"] == "Failed to write file."
        assert target.read_bytes() == b"keep me\n"
        assert list(target.parent.glob(".sp-*")) == []
    finally:
        os.chmod(target, stat.S_IWRITE | stat.S_IREAD)


# --- containment through symlinks ------------------------------------------------------------

async def test_symlink_pointing_outside_the_project_can_be_neither_read_nor_written(async_client: AsyncClient, project, sandbox):
    outside = sandbox / "outside-secret.txt"
    outside.write_bytes(b"TOP-SECRET")
    link = Path(project["root_path"]) / "link.txt"
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("this account cannot create symlinks")

    names = [f["path"] for f in flatten((await async_client.get(url(project, "tree"))).json())]
    assert "link.txt" not in names, "the tree must not list symlinks"

    got = await async_client.get(url(project, "content"), params={"path": "link.txt"})
    assert got.status_code == 400 and "TOP-SECRET" not in got.text
    put = await save_file(async_client, project, "link.txt", "pwned", base_sha256=ANY_SHA256)
    assert put.status_code == 400
    assert outside.read_bytes() == b"TOP-SECRET"

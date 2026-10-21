"""PUT .../files/content is conflict-safe: it updates existing files only, and only if the file on disk is
still the one the caller loaded (proved by the SHA-256 the caller sends back as base_sha256).

Every rejection must leave the workspace exactly as it was: no bytes changed, nothing created (no file,
no parent folder), no temporary file left behind.
"""
import asyncio
import hashlib
import os
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.api import files as files_mod
from app.config import settings

ZERO = "0" * 64


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def files_url(project: dict, suffix: str = "content") -> str:
    return f"/api/projects/{project['id']}/files/{suffix}"


def snapshot(root: Path) -> dict:
    """Every path under root and the exact bytes of every file: the whole observable state of a workspace."""
    return {p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None) for p in sorted(root.rglob("*"))}


async def put(client: AsyncClient, project: dict, body: dict):
    return await client.put(files_url(project), json=body)


def root_of(project: dict) -> Path:
    return Path(project["root_path"])


# --- GET reports the hash the editor must send back ------------------------------------------

async def test_get_returns_the_sha256_of_the_exact_bytes_on_disk(async_client, project):
    raw = b"\xef\xbb\xbfline1\r\nline2\r\n\xc3\xbcn\xc3\xaf\r\n"  # BOM + CRLF + non-ASCII: nothing may be normalised
    (root_of(project) / "enc.txt").write_bytes(raw)
    got = await async_client.get(files_url(project), params={"path": "enc.txt"})
    assert got.status_code == 200
    assert got.json()["sha256"] == sha(raw)


async def test_the_hash_changes_when_the_file_changes_on_disk(async_client, project):
    first = (await async_client.get(files_url(project), params={"path": "app/main.py"})).json()["sha256"]
    (root_of(project) / "app" / "main.py").write_bytes(b"edited elsewhere")
    second = (await async_client.get(files_url(project), params={"path": "app/main.py"})).json()["sha256"]
    assert first != second and second == sha(b"edited elsewhere")


def test_hashing_reads_files_larger_than_one_chunk_correctly(tmp_path):
    data = (bytes(range(256)) * 10240) + b"tail"  # about 2.6 MB: more than two 1 MiB chunks
    target = tmp_path / "big.bin"
    target.write_bytes(data)
    assert files_mod.sha256_of_file(target) == sha(data)


# --- the happy path: the hash chains from one save to the next -------------------------------

async def test_save_with_the_current_hash_succeeds_and_returns_the_new_hash(async_client, save, project):
    res = await save(project, "app/main.py", "first\n")
    assert res.status_code == 200
    assert res.json()["sha256"] == sha(b"first\n")
    # the returned hash is exactly what a fresh read reports, so the editor can chain saves
    again = await async_client.get(files_url(project), params={"path": "app/main.py"})
    assert again.json()["sha256"] == res.json()["sha256"]

    chained = await put(async_client, project, {"path": "app/main.py", "content": "second\n", "base_sha256": res.json()["sha256"]})
    assert chained.status_code == 200
    assert (root_of(project) / "app" / "main.py").read_bytes() == b"second\n"


async def test_the_previous_hash_stops_working_after_a_successful_save(async_client, save, project):
    old = (await async_client.get(files_url(project), params={"path": "app/main.py"})).json()["sha256"]
    assert (await save(project, "app/main.py", "new\n")).status_code == 200
    stale = await put(async_client, project, {"path": "app/main.py", "content": "again\n", "base_sha256": old})
    assert stale.status_code == 409
    assert (root_of(project) / "app" / "main.py").read_bytes() == b"new\n"


async def test_a_no_op_save_of_the_loaded_content_is_accepted_and_changes_no_bytes(async_client, project):
    loaded = (await async_client.get(files_url(project), params={"path": "app/main.py"})).json()
    before = (root_of(project) / "app" / "main.py").read_bytes()
    res = await put(async_client, project, {"path": "app/main.py", "content": loaded["content"], "base_sha256": loaded["sha256"]})
    assert res.status_code == 200
    assert (root_of(project) / "app" / "main.py").read_bytes() == before


async def test_uppercase_hex_is_accepted(async_client, project):
    current = (await async_client.get(files_url(project), params={"path": "app/main.py"})).json()["sha256"]
    res = await put(async_client, project, {"path": "app/main.py", "content": "x", "base_sha256": current.upper()})
    assert res.status_code == 200


async def test_conflict_detection_is_by_content_not_by_timestamp(async_client, project):
    """Rewriting the same bytes (a touch, or a tool that saves unchanged content) is not a conflict."""
    target = root_of(project) / "app" / "main.py"
    base = (await async_client.get(files_url(project), params={"path": "app/main.py"})).json()["sha256"]
    target.write_bytes(target.read_bytes())
    os.utime(target, None)
    assert (await put(async_client, project, {"path": "app/main.py", "content": "ok", "base_sha256": base})).status_code == 200


# --- 409: the disk changed since the file was loaded -------------------------------------------

async def test_stale_hash_is_409_and_the_disk_keeps_the_other_writers_bytes(async_client, project):
    target = root_of(project) / "app" / "main.py"
    base = (await async_client.get(files_url(project), params={"path": "app/main.py"})).json()["sha256"]
    target.write_bytes(b"someone else changed this\n")  # e.g. another editor, git checkout, a formatter

    res = await put(async_client, project, {"path": "app/main.py", "content": "my edit\n", "base_sha256": base})

    assert res.status_code == 409
    assert "changed on disk" in res.json()["detail"] and "Nothing was written" in res.json()["detail"]
    assert target.read_bytes() == b"someone else changed this\n"
    assert list(root_of(project).rglob(".sp-*")) == []


async def test_a_conflict_response_never_leaks_file_content(async_client, project):
    (root_of(project) / "app" / "main.py").write_bytes(b"TOP-SECRET-CONTENT")
    res = await put(async_client, project, {"path": "app/main.py", "content": "x", "base_sha256": ZERO})
    assert res.status_code == 409
    assert "TOP-SECRET-CONTENT" not in res.text and sha(b"TOP-SECRET-CONTENT") not in res.text


async def test_a_hash_that_matches_no_state_of_the_file_is_409(async_client, project):
    before = snapshot(root_of(project))
    res = await put(async_client, project, {"path": "app/main.py", "content": "x", "base_sha256": ZERO})
    assert res.status_code == 409
    assert snapshot(root_of(project)) == before


# --- 428 / 400: the hash is required and must be well-formed -----------------------------------

async def test_missing_hash_is_428_and_nothing_is_written(async_client, project):
    before = snapshot(root_of(project))
    res = await put(async_client, project, {"path": "app/main.py", "content": "x"})
    assert res.status_code == 428
    assert "base_sha256" in res.json()["detail"] and "required" in res.json()["detail"]
    assert snapshot(root_of(project)) == before


async def test_an_explicit_null_hash_is_also_428(async_client, project):
    before = snapshot(root_of(project))
    res = await put(async_client, project, {"path": "app/main.py", "content": "x", "base_sha256": None})
    assert res.status_code == 428
    assert snapshot(root_of(project)) == before


@pytest.mark.parametrize(
    "bad",
    ["", "abc", "0" * 63, "0" * 65, "g" * 64, " " + "0" * 63, "0" * 63 + " ", "0" * 32 + "\n" + "0" * 31, "sha256:" + "0" * 57, "0x" + "0" * 62],
)
async def test_malformed_hash_is_400_and_nothing_is_written(async_client, project, bad):
    before = snapshot(root_of(project))
    res = await put(async_client, project, {"path": "app/main.py", "content": "x", "base_sha256": bad})
    assert res.status_code == 400
    assert "64 hexadecimal" in res.json()["detail"]
    assert snapshot(root_of(project)) == before


@pytest.mark.parametrize("wrong_type", [123, True, ["0" * 64], {"sha": "0" * 64}])
async def test_a_hash_of_the_wrong_json_type_is_rejected(async_client, project, wrong_type):
    before = snapshot(root_of(project))
    res = await put(async_client, project, {"path": "app/main.py", "content": "x", "base_sha256": wrong_type})
    # a non-string JSON value is rejected by request validation (422), unlike a malformed *string* (400);
    # API_DOCUMENTATION.md documents exactly this distinction
    assert res.status_code == 422
    assert isinstance(res.json()["detail"], list)
    assert snapshot(root_of(project)) == before


async def test_a_malformed_hash_string_is_400_not_422_as_documented(async_client, project):
    res = await put(async_client, project, {"path": "app/main.py", "content": "x", "base_sha256": "not-a-hash"})
    assert res.status_code == 400
    assert isinstance(res.json()["detail"], str)


# --- 404: PUT never creates ----------------------------------------------------------------------

async def test_a_file_that_never_existed_is_404_and_is_not_created(async_client, project):
    before = snapshot(root_of(project))
    res = await put(async_client, project, {"path": "brand-new.txt", "content": "x", "base_sha256": ZERO})
    assert res.status_code == 404
    detail = res.json()["detail"]
    assert "does not exist" in detail and "never creates" in detail and "Nothing was written" in detail
    assert snapshot(root_of(project)) == before


async def test_a_file_in_a_folder_that_does_not_exist_is_404_and_no_folder_is_created(async_client, project):
    before = snapshot(root_of(project))
    res = await put(async_client, project, {"path": "no/such/folder/new.txt", "content": "x", "base_sha256": ZERO})
    assert res.status_code == 404
    assert not (root_of(project) / "no").exists()
    assert snapshot(root_of(project)) == before


async def test_a_file_deleted_after_it_was_loaded_is_404_and_is_not_recreated(async_client, project):
    target = root_of(project) / "app" / "main.py"
    loaded = (await async_client.get(files_url(project), params={"path": "app/main.py"})).json()
    target.unlink()  # deleted on disk while the editor still holds the loaded content and hash

    res = await put(async_client, project, {"path": "app/main.py", "content": loaded["content"], "base_sha256": loaded["sha256"]})

    assert res.status_code == 404
    assert not target.exists()
    assert list(root_of(project).rglob(".sp-*")) == []


async def test_a_file_whose_parent_folder_was_deleted_is_404_and_the_folder_is_not_recreated(async_client, project):
    import shutil

    loaded = (await async_client.get(files_url(project), params={"path": "app/api/routes.py"})).json()
    shutil.rmtree(root_of(project) / "app" / "api")
    res = await put(async_client, project, {"path": "app/api/routes.py", "content": "x", "base_sha256": loaded["sha256"]})
    assert res.status_code == 404
    assert not (root_of(project) / "app" / "api").exists()


# --- 400: directories ----------------------------------------------------------------------------

async def test_a_directory_with_a_valid_hash_is_400(async_client, project):
    before = snapshot(root_of(project))
    res = await put(async_client, project, {"path": "app", "content": "x", "base_sha256": ZERO})
    assert res.status_code == 400 and "directory" in res.json()["detail"]
    assert snapshot(root_of(project)) == before


# --- 413: oversized content ----------------------------------------------------------------------

async def test_oversized_content_is_413_even_with_a_correct_hash_and_the_file_is_untouched(async_client, project, monkeypatch):
    target = root_of(project) / "app" / "main.py"
    original = target.read_bytes()
    base = sha(original)
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_BYTES", len(original))
    before = snapshot(root_of(project))
    res = await put(async_client, project, {"path": "app/main.py", "content": "x" * (len(original) + 1), "base_sha256": base})
    assert res.status_code == 413
    assert snapshot(root_of(project)) == before
    assert target.read_bytes() == original


async def test_content_exactly_at_the_limit_is_accepted(async_client, project, monkeypatch):
    base = sha((root_of(project) / "app" / "main.py").read_bytes())
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_BYTES", 10)
    res = await put(async_client, project, {"path": "app/main.py", "content": "x" * 10, "base_sha256": base})
    assert res.status_code == 200
    assert (root_of(project) / "app" / "main.py").read_bytes() == b"x" * 10


async def test_the_limit_counts_bytes_not_characters(async_client, project, monkeypatch):
    base = sha((root_of(project) / "app" / "main.py").read_bytes())
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_BYTES", 10)
    res = await put(async_client, project, {"path": "app/main.py", "content": "é" * 6, "base_sha256": base})  # 12 bytes
    assert res.status_code == 413


# --- the agreed validation order -----------------------------------------------------------------

async def test_unknown_project_is_404_before_anything_else(async_client):
    res = await async_client.put(
        "/api/projects/no-such-project/files/content", json={"path": "../x", "content": "x", "base_sha256": "bad"}
    )
    assert res.status_code == 404


async def test_missing_project_folder_is_404_before_the_path_or_hash_is_looked_at(async_client, project):
    import shutil

    shutil.rmtree(root_of(project))
    res = await put(async_client, project, {"path": "../x", "content": "x"})
    assert res.status_code == 404
    assert not root_of(project).exists()


async def test_unsafe_path_is_400_before_the_hash_is_looked_at(async_client, project):
    res = await put(async_client, project, {"path": "../escape.txt", "content": "x"})  # no hash at all
    assert res.status_code == 400 and "Path traversal" in res.json()["detail"]


async def test_oversized_content_is_413_before_the_hash_is_looked_at(async_client, project, monkeypatch):
    monkeypatch.setattr(settings, "MAX_FILE_SIZE_BYTES", 5)
    res = await put(async_client, project, {"path": "app/main.py", "content": "x" * 6})  # no hash at all
    assert res.status_code == 413


async def test_missing_hash_is_428_before_the_file_is_looked_up(async_client, project):
    assert (await put(async_client, project, {"path": "does-not-exist.txt", "content": "x"})).status_code == 428
    assert (await put(async_client, project, {"path": "app", "content": "x"})).status_code == 428  # a directory


async def test_malformed_hash_is_400_before_the_file_is_looked_up(async_client, project):
    res = await put(async_client, project, {"path": "does-not-exist.txt", "content": "x", "base_sha256": "nope"})
    assert res.status_code == 400 and "64 hexadecimal" in res.json()["detail"]


async def test_a_directory_is_400_before_the_hash_is_compared(async_client, project):
    res = await put(async_client, project, {"path": "app", "content": "x", "base_sha256": ZERO})
    assert res.status_code == 400 and "directory" in res.json()["detail"]


async def test_a_missing_file_is_404_before_the_hash_is_compared(async_client, project):
    res = await put(async_client, project, {"path": "missing.txt", "content": "x", "base_sha256": ZERO})
    assert res.status_code == 404


# --- no rejection may have any side effect -------------------------------------------------------

REJECTIONS = [
    pytest.param({"path": "app/main.py", "content": "x"}, id="missing-hash"),
    pytest.param({"path": "app/main.py", "content": "x", "base_sha256": "zzz"}, id="malformed-hash"),
    pytest.param({"path": "app/main.py", "content": "x", "base_sha256": ZERO}, id="stale-hash"),
    pytest.param({"path": "gone.txt", "content": "x", "base_sha256": ZERO}, id="missing-file"),
    pytest.param({"path": "a/b/c/new.txt", "content": "x", "base_sha256": ZERO}, id="missing-nested-file"),
    pytest.param({"path": "app", "content": "x", "base_sha256": ZERO}, id="directory"),
    pytest.param({"path": "../out.txt", "content": "x", "base_sha256": ZERO}, id="path-traversal"),
    pytest.param({"path": "/etc/passwd", "content": "x", "base_sha256": ZERO}, id="absolute-path"),
]


@pytest.mark.parametrize("body", REJECTIONS)
async def test_a_rejected_save_leaves_the_workspace_exactly_as_it_was(async_client, project, body, sandbox):
    before = snapshot(root_of(project))
    outside_before = sorted(p.name for p in root_of(project).parent.iterdir())
    res = await put(async_client, project, body)
    assert res.status_code in (400, 404, 409, 428), res.text
    assert snapshot(root_of(project)) == before
    assert sorted(p.name for p in root_of(project).parent.iterdir()) == outside_before


# --- temporary-file cleanup ----------------------------------------------------------------------

async def test_no_temp_files_remain_after_a_mix_of_successes_and_rejections(async_client, save, project):
    await save(project, "app/main.py", "one")
    await save(project, "app/main.py", "stale", base_sha256=ZERO)
    await put(async_client, project, {"path": "app/main.py", "content": "x"})
    await put(async_client, project, {"path": "nope.txt", "content": "x", "base_sha256": ZERO})
    await save(project, "app/main.py", "two")
    assert list(root_of(project).rglob(".sp-*")) == []


async def test_if_the_final_swap_fails_the_original_is_untouched_and_the_temp_file_is_removed(async_client, project, monkeypatch):
    target = root_of(project) / "app" / "main.py"
    original = target.read_bytes()
    base = sha(original)

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    # replace only the module's view of `os`, so nothing else in the test run is affected
    monkeypatch.setattr(files_mod, "os", SimpleNamespace(replace=boom, path=os.path, unlink=os.unlink))
    res = await put(async_client, project, {"path": "app/main.py", "content": "new", "base_sha256": base})

    assert res.status_code == 500 and res.json()["detail"] == "Failed to write file."
    assert target.read_bytes() == original
    assert list(root_of(project).rglob(".sp-*")) == []


async def test_a_change_made_between_the_first_check_and_the_swap_is_caught_by_the_second_check(async_client, project, monkeypatch):
    """Simulates another writer sneaking in after the first hash check: the re-check before the swap must catch it."""
    target = root_of(project) / "app" / "main.py"
    base = sha(target.read_bytes())
    real_check = files_mod._require_unchanged
    calls = {"n": 0}

    def racing_check(path, base_sha256):
        calls["n"] += 1
        if calls["n"] == 2:  # after the temp file was written, before the swap
            path.write_bytes(b"written by someone else in the gap")
        return real_check(path, base_sha256)

    monkeypatch.setattr(files_mod, "_require_unchanged", racing_check)
    res = await put(async_client, project, {"path": "app/main.py", "content": "mine", "base_sha256": base})

    assert calls["n"] == 2
    assert res.status_code == 409
    assert target.read_bytes() == b"written by someone else in the gap"
    assert list(root_of(project).rglob(".sp-*")) == []


async def test_a_file_deleted_between_the_first_check_and_the_swap_is_404_not_recreated(async_client, project, monkeypatch):
    target = root_of(project) / "app" / "main.py"
    base = sha(target.read_bytes())
    real_check = files_mod._require_unchanged
    calls = {"n": 0}

    def deleting_check(path, base_sha256):
        calls["n"] += 1
        if calls["n"] == 2:
            path.unlink()
        return real_check(path, base_sha256)

    monkeypatch.setattr(files_mod, "_require_unchanged", deleting_check)
    res = await put(async_client, project, {"path": "app/main.py", "content": "mine", "base_sha256": base})
    assert res.status_code == 404
    assert not target.exists()
    assert list(root_of(project).rglob(".sp-*")) == []


# --- concurrent saves ---------------------------------------------------------------------------

async def test_concurrent_saves_from_the_same_base_let_exactly_one_win(async_client, project):
    target = root_of(project) / "app" / "main.py"
    base = sha(target.read_bytes())
    contents = [f"writer {i}\n" for i in range(10)]

    responses = await asyncio.gather(
        *[put(async_client, project, {"path": "app/main.py", "content": c, "base_sha256": base}) for c in contents]
    )

    codes = sorted(r.status_code for r in responses)
    assert codes == [200] + [409] * 9, codes
    winner = next(c for c, r in zip(contents, responses) if r.status_code == 200)
    assert target.read_bytes() == winner.encode("utf-8")
    assert list(root_of(project).rglob(".sp-*")) == []


def test_concurrent_threads_cannot_both_pass_the_check(tmp_path):
    """The same guarantee at the function level, with real OS threads released at the same instant."""
    target = tmp_path / "shared.txt"
    target.write_bytes(b"original")
    base = sha(b"original")
    workers = 12
    barrier = threading.Barrier(workers)
    outcomes = [None] * workers

    def run(i: int):
        barrier.wait()
        try:
            outcomes[i] = ("ok", files_mod.replace_existing_file(target, f"writer {i}".encode(), base))
        except files_mod.FileChangedError:
            outcomes[i] = ("conflict", None)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(workers)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    winners = [i for i, o in enumerate(outcomes) if o[0] == "ok"]
    assert len(winners) == 1, outcomes
    assert target.read_bytes() == f"writer {winners[0]}".encode()
    assert [o[0] for o in outcomes].count("conflict") == workers - 1
    assert list(tmp_path.glob(".sp-*")) == []


def test_replace_existing_file_never_creates_a_file_or_folder(tmp_path):
    with pytest.raises(files_mod.FileMissingError):
        files_mod.replace_existing_file(tmp_path / "new.txt", b"x", ZERO)
    with pytest.raises(files_mod.FileMissingError):
        files_mod.replace_existing_file(tmp_path / "no" / "such" / "new.txt", b"x", ZERO)
    assert list(tmp_path.iterdir()) == []

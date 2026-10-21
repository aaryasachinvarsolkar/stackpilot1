"""ZIP import hardening: path traversal / zip-slip, unsafe entry types, size limits, cleanup and error hygiene.

Every archive here is built in memory, every project lives in the per-session sandbox, and nothing touches the network.
"""
import io
import stat
import uuid
import warnings
import zipfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.services import workspace
from app.api import projects as projects_api
from app.services.workspace import ArchiveError, ArchiveTooLargeError, extract_zip_archive

GENERIC_500 = "The project could not be imported."


def make_zip(entries, compress=zipfile.ZIP_DEFLATED) -> bytes:
    """entries: (name, bytes|str) pairs, or ("symlink:name", target). Names are written exactly as given."""
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # duplicate names are deliberate in some tests
        with zipfile.ZipFile(buf, "w", compress) as zf:
            for name, data in entries:
                info = zipfile.ZipInfo("placeholder")
                info.compress_type = compress
                if name.startswith("symlink:"):
                    info.filename = name[len("symlink:"):]
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                else:
                    info.filename = name  # assigned after construction: ZipInfo() would rewrite some names
                    info.create_system = 3
                    info.external_attr = ((stat.S_IFDIR | 0o755) if name.endswith("/") else (stat.S_IFREG | 0o644)) << 16
                zf.writestr(info, data if isinstance(data, bytes) else data.encode())
    return buf.getvalue()


def mark_encrypted(data: bytes) -> bytes:
    """Set the 'encrypted' flag in every local and central header (the content is not really encrypted)."""
    out = bytearray(data)
    for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        start = 0
        while (at := data.find(signature, start)) != -1:
            out[at + offset] |= 0x01
            start = at + 4
    return bytes(out)


async def upload(client: AsyncClient, name: str, data: bytes):
    return await client.post("/api/projects/upload", data={"name": name}, files={"file": ("x.zip", data, "application/zip")})


def new_name() -> str:
    return f"z-{uuid.uuid4().hex[:10]}"


def workspace_of(sandbox: Path, name: str) -> Path:
    return sandbox / "workspaces" / name


async def assert_nothing_imported(client: AsyncClient, sandbox: Path, name: str):
    assert not workspace_of(sandbox, name).exists(), "a rejected import left a folder behind"
    assert (await client.get(f"/api/projects/{name}")).status_code == 404, "a rejected import left a project record"


# ---------------------------------------------------------------------------------------------------------------
# valid imports keep working
# ---------------------------------------------------------------------------------------------------------------

async def test_valid_archive_with_a_top_level_folder_imports_and_the_folder_is_stripped(async_client, sandbox):
    name = new_name()
    data = make_zip([
        ("repo-main/", ""), ("repo-main/README.md", "# hi\n"), ("repo-main/src/", ""), ("repo-main/src/app.py", "print(1)\n"),
        ("repo-main/src/pkg/util.py", "x = 1\n"),
    ])
    res = await upload(async_client, name, data)
    assert res.status_code == 201, res.text
    root = workspace_of(sandbox, name)
    assert (root / "README.md").read_text() == "# hi\n"
    assert (root / "src" / "app.py").read_text() == "print(1)\n"
    assert (root / "src" / "pkg" / "util.py").read_text() == "x = 1\n"
    assert not (root / "repo-main").exists()
    assert res.json()["file_count"] == 3
    assert (await async_client.get(f"/api/projects/{name}")).status_code == 200


async def test_flat_archive_without_a_shared_folder_keeps_its_layout(async_client, sandbox):
    name = new_name()
    res = await upload(async_client, name, make_zip([("a.py", "a"), ("lib/b.py", "b")]))
    assert res.status_code == 201, res.text
    assert (workspace_of(sandbox, name) / "a.py").read_text() == "a"
    assert (workspace_of(sandbox, name) / "lib" / "b.py").read_text() == "b"


async def test_archive_with_two_top_level_folders_is_not_stripped(async_client, sandbox):
    name = new_name()
    res = await upload(async_client, name, make_zip([("one/a.py", "a"), ("two/b.py", "b")]))
    assert res.status_code == 201, res.text
    assert (workspace_of(sandbox, name) / "one" / "a.py").exists() and (workspace_of(sandbox, name) / "two" / "b.py").exists()


async def test_ignored_folders_are_skipped_silently_and_the_rest_imports(async_client, sandbox):
    name = new_name()
    data = make_zip([
        ("repo/src/main.py", "m"), ("repo/.git/config", "c"), ("repo/node_modules/x/index.js", "j"), ("repo/__pycache__/m.pyc", "p"),
    ])
    res = await upload(async_client, name, data)
    assert res.status_code == 201, res.text
    root = workspace_of(sandbox, name)
    assert (root / "src" / "main.py").exists()
    assert not (root / ".git").exists() and not (root / "node_modules").exists() and not (root / "__pycache__").exists()


async def test_unicode_and_spaced_file_names_import(async_client, sandbox):
    name = new_name()
    res = await upload(async_client, name, make_zip([("README.md", "r"), ("docs/Résumé draft.md", "x"), ("docs/日本語.txt", "y")]))
    assert res.status_code == 201, res.text
    assert (workspace_of(sandbox, name) / "docs" / "Résumé draft.md").read_text(encoding="utf-8") == "x"
    assert (workspace_of(sandbox, name) / "docs" / "日本語.txt").read_text(encoding="utf-8") == "y"


async def test_empty_archive_behaves_as_before(async_client, sandbox):
    name = new_name()
    res = await upload(async_client, name, make_zip([]))
    assert res.status_code == 201, res.text
    assert workspace_of(sandbox, name).is_dir()


# ---------------------------------------------------------------------------------------------------------------
# zip-slip and unsafe entries: the WHOLE archive is rejected, and nothing is written
# ---------------------------------------------------------------------------------------------------------------

def attacks(marker: str):
    return {
        "dotdot": [(f"../{marker}", "x")],
        "dotdot-deep": [(f"a/b/../../../{marker}", "x")],
        "dotdot-in-middle": [(f"a/../../{marker}", "x")],
        "dotdot-backslash": [(f"..\\{marker}", "x")],
        "dotdot-mixed": [(f"a\\..\\..\\{marker}", "x")],
        "absolute-unix": [(f"/{marker}", "x")],
        "absolute-backslash": [(f"\\{marker}", "x")],
        "windows-drive": [(f"C:/{marker}", "x")],
        "windows-drive-backslash": [(f"C:\\{marker}", "x")],
        "drive-relative": [(f"C:{marker}", "x")],
        "ntfs-stream": [(f"a.txt:{marker}", "x")],
        "unc-path": [(f"//server/share/{marker}", "x")],
        "dot-part": [(f"a/./{marker}", "x")],
        "empty-part": [(f"a//{marker}", "x")],
        "reserved-name": [("con.txt", "x")],
        "reserved-name-nested": [(f"dir/NUL/{marker}", "x")],
        "reserved-com": [("COM1", "x")],
        "trailing-dot": [(f"{marker}.", "x")],
        "trailing-space": [(f"{marker} ", "x")],
        "forbidden-char": [(f"{marker}?.py", "x")],
        "control-char": [(f"{marker}\n.py", "x")],
        "overlong-part": [("a" * 300, "x")],
        "overlong-path": [("/".join(["abcdefghij"] * 120) + "/f.py", "x")],
        "symlink": [("symlink:link", "/etc/passwd")],
        "symlink-relative": [("symlink:link", "../../..")],
        "duplicate": [("a.py", "one"), ("a.py", "two")],
        "duplicate-case": [("a.py", "one"), ("A.py", "two")],
        "file-and-folder": [("a", "file"), ("a/b.py", "x")],
        "unsafe-dir-entry": [(f"../{marker}/", "")],
        "unsafe-entry-inside-ignored-folder": [("repo/.git/../../" + marker, "x")],
    }


ATTACK_IDS = list(attacks("m").keys())


@pytest.mark.parametrize("attack", ATTACK_IDS)
async def test_unsafe_archive_is_rejected_whole_and_nothing_is_written(async_client, sandbox, attack):
    marker = f"escaped-{uuid.uuid4().hex[:8]}.txt"
    name = new_name()
    # a harmless entry FIRST, so "validate everything before writing" is observable: it must not have been written either
    entries = [("good/before.py", "ok")] + attacks(marker)[attack] + [("good/after.py", "ok")]
    res = await upload(async_client, name, make_zip(entries))
    assert res.status_code == 400, res.text
    assert marker not in res.text, "the response must not echo the offending name"
    await assert_nothing_imported(async_client, sandbox, name)
    for base in (sandbox, sandbox / "workspaces", sandbox.parent, Path.cwd()):
        assert not (base / marker).exists(), f"{marker} escaped to {base}"


async def test_rejection_message_is_generic(async_client):
    res = await upload(async_client, new_name(), make_zip([("../evil.py", "x")]))
    assert res.json()["detail"] == "The archive contains an unsafe or unsupported entry, so nothing was imported."


async def test_encrypted_archive_is_rejected(async_client, sandbox):
    name = new_name()
    res = await upload(async_client, name, mark_encrypted(make_zip([("a.py", "x")])))
    assert res.status_code == 400
    assert res.json()["detail"] == "Encrypted archives are not supported."
    await assert_nothing_imported(async_client, sandbox, name)


@pytest.mark.parametrize("name,expected", [
    ("a.py", ["a.py"]), ("a/b.py", ["a", "b.py"]), ("a\\b.py", ["a", "b.py"]), ("a/", ["a"]), ("dir/sub/", ["dir", "sub"]),
    ("日本語/ü.py", ["日本語", "ü.py"]), ("a b/c d.txt", ["a b", "c d.txt"]), (".gitignore", [".gitignore"]),
    ("..hidden", ["..hidden"]), ("con-sole.txt", ["con-sole.txt"]), ("aux1.txt", ["aux1.txt"]),
])
def test_safe_names_are_accepted(name, expected):
    assert workspace._safe_archive_parts(name, name.endswith("/")) == expected


@pytest.mark.parametrize("name", [
    "", "/", "a\x00b", "../a", "a/../b", "a/..", "..", ".", "a/.", "/a", "\\a", "C:a", "a:b", "a//b", "a/ /b", "a./b", "a /b",
    "CON", "con.txt", "a/nul.py", "Lpt3.x", "a<b", "a>b", 'a"b', "a|b", "a*b", "a?b", "a\tb", "x" * 256, "a/" * 600 + "b",
])
def test_unsafe_names_are_refused(name):
    assert workspace._safe_archive_parts(name, name.endswith("/")) is None


# ---------------------------------------------------------------------------------------------------------------
# validation happens before writing (unit level)
# ---------------------------------------------------------------------------------------------------------------

def test_a_bad_entry_at_the_end_of_a_big_archive_means_nothing_was_written(tmp_path):
    target = tmp_path / "proj"
    data = make_zip([(f"ok/f{i}.py", "x") for i in range(50)] + [("../../evil.py", "x")])
    with pytest.raises(ArchiveError):
        extract_zip_archive(data, target)
    assert not target.exists()
    assert not (tmp_path / "evil.py").exists() and not (tmp_path.parent / "evil.py").exists()


def test_an_existing_target_folder_is_left_empty_when_the_archive_is_rejected(tmp_path):
    target = tmp_path / "proj"
    target.mkdir()
    with pytest.raises(ArchiveError):
        extract_zip_archive(make_zip([("ok.py", "x"), ("../evil.py", "x")]), target)
    assert list(target.iterdir()) == []


def test_extraction_never_overwrites_an_existing_file(tmp_path):
    target = tmp_path / "proj"
    target.mkdir()
    (target / "a.py").write_text("precious")
    with pytest.raises(FileExistsError):
        extract_zip_archive(make_zip([("a.py", "new")]), target)
    assert (target / "a.py").read_text() == "precious"


def test_resolved_destination_is_checked_again_even_if_name_validation_were_wrong(tmp_path, monkeypatch):
    """Second layer: if the name validator ever let a traversal through, the resolved path must still stay inside."""
    monkeypatch.setattr(workspace, "_safe_archive_parts", lambda name, is_dir: ["top", "..", "escaped.py"])
    target = tmp_path / "proj"
    with pytest.raises(ArchiveError):
        extract_zip_archive(make_zip([("anything.py", "x")]), target)
    assert not (tmp_path / "escaped.py").exists()
    assert not target.exists()


def test_resolved_destination_equal_to_the_workspace_itself_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, "_safe_archive_parts", lambda name, is_dir: ["top", "x", ".."])
    with pytest.raises(ArchiveError):
        extract_zip_archive(make_zip([("anything.py", "x")]), tmp_path / "proj")


def test_the_returned_count_is_the_number_of_files_written(tmp_path):
    assert extract_zip_archive(make_zip([("r/a.py", "1"), ("r/d/", ""), ("r/d/b.py", "2"), ("r/.git/x", "3")]), tmp_path / "p") == 2


# ---------------------------------------------------------------------------------------------------------------
# size limits
# ---------------------------------------------------------------------------------------------------------------

async def test_upload_over_the_limit_is_413_even_for_a_perfectly_valid_zip(async_client, sandbox, monkeypatch):
    data = make_zip([("big.bin", "x" * 5000)], compress=zipfile.ZIP_STORED)
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", len(data) - 1)
    name = new_name()
    res = await upload(async_client, name, data)
    assert res.status_code == 413
    assert "byte limit" in res.json()["detail"]
    await assert_nothing_imported(async_client, sandbox, name)


async def test_upload_exactly_at_the_limit_is_accepted(async_client, sandbox, monkeypatch):
    data = make_zip([("a.py", "x" * 200)], compress=zipfile.ZIP_STORED)
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", len(data))
    name = new_name()
    assert (await upload(async_client, name, data)).status_code == 201


async def test_upload_limit_is_enforced_on_bytes_actually_read(async_client, monkeypatch):
    """The endpoint reads in chunks and stops at the limit; it does not trust a size reported by the client."""
    chunks_read = []

    class Spy:
        filename = "x.zip"

        def __init__(self):
            self.left = 10 * 1024 * 1024

        async def read(self, size=-1):
            chunk = min(size, self.left) if size > 0 else self.left
            self.left -= chunk
            chunks_read.append(chunk)
            return b"\0" * chunk

    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 3 * 1024 * 1024)
    with pytest.raises(Exception) as caught:
        await projects_api._read_upload_limited(Spy())
    assert getattr(caught.value, "status_code", None) == 413
    assert sum(chunks_read) <= 3 * 1024 * 1024 + 1024 * 1024, "kept reading long after the limit"


async def test_oversized_declared_body_is_refused_before_it_is_parsed(async_client, sandbox, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1000)
    name = new_name()
    res = await upload(async_client, name, b"\0" * (1000 + 1024 * 1024 + 4096))  # past limit + multipart allowance
    assert res.status_code == 413
    assert res.json()["detail"] == "The upload is larger than the 1000 byte limit."
    await assert_nothing_imported(async_client, sandbox, name)


async def test_oversized_streamed_body_without_a_content_length_is_cut_off(sandbox, monkeypatch):
    """A client can omit Content-Length (chunked). The bytes that really arrive are counted."""
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1000)
    limit = 1000 + 1024 * 1024
    delivered = []
    sent = {}
    opening = (
        b'--xyz\r\nContent-Disposition: form-data; name="name"\r\n\r\nstreamed\r\n'
        b'--xyz\r\nContent-Disposition: form-data; name="file"; filename="x.zip"\r\nContent-Type: application/zip\r\n\r\n'
    )
    chunks = iter([opening] + [b"x" * 600_000] * 4)  # a well-formed multipart start, then file bytes that never end

    async def receive():
        try:
            chunk = next(chunks)
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}
        delivered.append(len(chunk))
        return {"type": "http.request", "body": chunk, "more_body": True}

    async def send(message):
        if message["type"] == "http.response.start":
            sent["status"] = message["status"]

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/api/projects/upload", "raw_path": b"/api/projects/upload", "query_string": b"",
        "headers": [(b"host", b"127.0.0.1"), (b"content-type", b"multipart/form-data; boundary=xyz")],
        "server": ("127.0.0.1", 8000), "client": ("127.0.0.1", 50000),
    }
    await app(scope, receive, send)
    assert sent["status"] == 413
    assert sum(delivered) <= limit + 600_000, "kept consuming the body long after the limit"


async def test_other_endpoints_are_not_subject_to_the_upload_limit(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 10)
    res = await async_client.post(
        "/api/projects", json={"name": new_name(), "description": "d" * (2 * 1024 * 1024), "source_type": "blank"}
    )
    assert res.status_code != 413, "the upload size guard must only apply to POST /api/projects/upload"
    res = await async_client.get("/api/projects")
    assert res.status_code == 200


async def test_declared_oversize_is_refused_without_reading_any_of_the_body(sandbox, monkeypatch):
    """With a Content-Length far over the limit the body is never even read."""
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1000)
    sent = {}

    async def receive():
        raise AssertionError("the request body was read although its declared length is over the limit")

    async def send(message):
        if message["type"] == "http.response.start":
            sent["status"] = message["status"]

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/api/projects/upload", "raw_path": b"/api/projects/upload", "query_string": b"",
        "headers": [(b"host", b"127.0.0.1"), (b"content-type", b"multipart/form-data; boundary=xyz"),
                    (b"content-length", str(10 * 1024 * 1024 * 1024).encode())],
        "server": ("127.0.0.1", 8000), "client": ("127.0.0.1", 50000),
    }
    await app(scope, receive, send)
    assert sent["status"] == 413


async def test_zip_bomb_with_an_honest_header_is_413_and_leaves_nothing(async_client, sandbox, monkeypatch):
    data = make_zip([("zeros.bin", b"\0" * 5_000_000)])  # tiny when compressed, 5 MB when extracted
    assert len(data) < 50_000
    monkeypatch.setattr(settings, "MAX_ZIP_UNCOMPRESSED_BYTES", 1_000_000)
    name = new_name()
    res = await upload(async_client, name, data)
    assert res.status_code == 413
    assert "extract to more than 1000000 bytes" in res.json()["detail"]
    await assert_nothing_imported(async_client, sandbox, name)


async def test_total_of_many_small_files_counts_towards_the_uncompressed_limit(async_client, sandbox, monkeypatch):
    monkeypatch.setattr(settings, "MAX_ZIP_UNCOMPRESSED_BYTES", 5000)
    name = new_name()
    res = await upload(async_client, name, make_zip([(f"d/f{i}.txt", "x" * 1000) for i in range(6)]))
    assert res.status_code == 413
    await assert_nothing_imported(async_client, sandbox, name)


async def test_uncompressed_total_exactly_at_the_limit_is_accepted(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_ZIP_UNCOMPRESSED_BYTES", 3000)
    assert (await upload(async_client, new_name(), make_zip([(f"f{i}.txt", "x" * 1000) for i in range(3)]))).status_code == 201


def test_a_lying_archive_header_cannot_get_past_the_limit(tmp_path, monkeypatch):
    """The central directory says 10 bytes; the stream delivers megabytes. The bytes actually extracted are counted."""
    data = make_zip([("small.txt", "0123456789")])
    monkeypatch.setattr(settings, "MAX_ZIP_UNCOMPRESSED_BYTES", 100_000)
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda self, member, mode="r", pwd=None, **kw: io.BytesIO(b"x" * 5_000_000))
    target = tmp_path / "proj"
    with pytest.raises(ArchiveTooLargeError):
        extract_zip_archive(data, target)
    assert not target.exists(), "the partly written folder was not removed"


def test_a_lying_header_on_a_preexisting_folder_removes_the_files_this_call_wrote(tmp_path, monkeypatch):
    target = tmp_path / "proj"
    target.mkdir()
    (target / "keep.txt").write_text("mine")
    data = make_zip([("a.txt", "01"), ("b.txt", "23")])
    monkeypatch.setattr(settings, "MAX_ZIP_UNCOMPRESSED_BYTES", 1000)
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda self, member, mode="r", pwd=None, **kw: io.BytesIO(b"x" * 5000))
    with pytest.raises(ArchiveTooLargeError):
        extract_zip_archive(data, target)
    assert sorted(p.name for p in target.iterdir()) == ["keep.txt"]
    assert (target / "keep.txt").read_text() == "mine"


async def test_too_many_entries_is_413(async_client, sandbox, monkeypatch):
    monkeypatch.setattr(settings, "MAX_ZIP_ENTRIES", 3)
    name = new_name()
    res = await upload(async_client, name, make_zip([(f"f{i}.txt", "x") for i in range(4)]))
    assert res.status_code == 413
    assert "more than 3 entries" in res.json()["detail"]
    await assert_nothing_imported(async_client, sandbox, name)


async def test_entry_count_includes_folders_and_exactly_at_the_limit_is_accepted(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_ZIP_ENTRIES", 3)
    assert (await upload(async_client, new_name(), make_zip([("d/", ""), ("d/a.txt", "x"), ("d/b.txt", "y")]))).status_code == 201
    assert (await upload(async_client, new_name(), make_zip([("d/", ""), ("d/a.txt", "x"), ("d/b.txt", "y"), ("d/c.txt", "z")]))).status_code == 413


def test_default_limits_are_the_approved_ones():
    from app.config import Settings

    s = Settings(_env_file=None)
    assert (s.MAX_UPLOAD_BYTES, s.MAX_ZIP_UNCOMPRESSED_BYTES, s.MAX_ZIP_ENTRIES) == (50 * 1024 * 1024, 200 * 1024 * 1024, 5000)


@pytest.mark.parametrize("field", ["MAX_UPLOAD_BYTES", "MAX_ZIP_UNCOMPRESSED_BYTES", "MAX_ZIP_ENTRIES"])
@pytest.mark.parametrize("value", [0, -1])
def test_non_positive_limits_are_refused_at_startup(field, value):
    from app.config import Settings

    with pytest.raises(ValueError):
        Settings(_env_file=None, **{field: value})


# ---------------------------------------------------------------------------------------------------------------
# corrupt input, cleanup and error hygiene
# ---------------------------------------------------------------------------------------------------------------

NOT_ZIP = "The file is not a valid ZIP archive, or it is corrupt or uses an unsupported format."


@pytest.mark.parametrize("label,data", [
    ("random-bytes", b"this is not a zip file at all" * 10),
    ("truncated", make_zip([("a.py", "x" * 2000), ("b.py", "y" * 2000)])[:60]),
    ("header-only", b"PK\x03\x04" + b"\0" * 20),
    ("end-of-directory-only-garbage", b"PK\x05\x06" + b"\xff" * 18),
])
async def test_corrupt_archives_are_400_with_a_generic_message(async_client, sandbox, label, data):
    name = new_name()
    res = await upload(async_client, name, data)
    assert res.status_code == 400, res.text
    assert res.json()["detail"] == NOT_ZIP
    await assert_nothing_imported(async_client, sandbox, name)


async def test_corrupt_content_found_while_extracting_removes_what_was_written(async_client, sandbox):
    stored = bytearray(make_zip([("first.txt", "first-ok"), ("second.txt", "SECOND-CONTENT-HERE")], compress=zipfile.ZIP_STORED))
    at = stored.find(b"SECOND-CONTENT-HERE")
    stored[at] ^= 0xFF  # content no longer matches its CRC
    name = new_name()
    res = await upload(async_client, name, bytes(stored))
    assert res.status_code == 400
    assert res.json()["detail"] == NOT_ZIP
    await assert_nothing_imported(async_client, sandbox, name)


async def test_empty_upload_is_still_400(async_client, sandbox):
    name = new_name()
    res = await upload(async_client, name, b"")
    assert res.status_code == 400
    await assert_nothing_imported(async_client, sandbox, name)


async def test_unexpected_failure_while_extracting_is_a_generic_500_that_leaks_nothing(async_client, sandbox, monkeypatch):
    def boom(zip_bytes, target):
        target.mkdir(parents=True)
        (target / "half.txt").write_text("partial")
        raise RuntimeError("secret-internal-detail C:\\Users\\someone\\private")

    monkeypatch.setattr(projects_api, "extract_zip_archive", boom)
    name = new_name()
    res = await upload(async_client, name, make_zip([("a.py", "x")]))
    assert res.status_code == 500
    assert res.json()["detail"] == GENERIC_500
    assert "secret" not in res.text and "someone" not in res.text
    await assert_nothing_imported(async_client, sandbox, name)


async def test_unexpected_failure_after_extracting_is_a_generic_500_and_cleans_up(async_client, sandbox, monkeypatch):
    def boom(path):
        raise ValueError("secret-after-extract /etc/shadow")

    monkeypatch.setattr(projects_api, "detect_project_languages", boom)
    name = new_name()
    res = await upload(async_client, name, make_zip([("a.py", "x")]))
    assert res.status_code == 500
    assert res.json()["detail"] == GENERIC_500
    assert "secret" not in res.text and "shadow" not in res.text
    await assert_nothing_imported(async_client, sandbox, name)


async def test_existing_project_name_is_still_409_and_the_archive_is_not_touched(async_client, project, sandbox):
    before = sorted(p.name for p in workspace_of(sandbox, project["name"]).iterdir())
    res = await upload(async_client, project["name"], make_zip([("injected.py", "x")]))
    assert res.status_code == 409
    assert sorted(p.name for p in workspace_of(sandbox, project["name"]).iterdir()) == before


async def test_unsafe_project_name_is_still_rejected(async_client):
    res = await upload(async_client, "../escape", make_zip([("a.py", "x")]))
    assert res.status_code == 422

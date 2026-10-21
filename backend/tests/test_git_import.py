"""GitHub import: strict URL parsing, size-capped download, and the same archive protections as uploads.

httpx is replaced by a fake, and any socket connection to a non-loopback address fails the test, so no real GitHub
request can ever be made from here.
"""
import io
import socket
import uuid
import zipfile
from types import SimpleNamespace

import pytest

from app.api import projects as projects_api
from app.config import settings
from app.services.workspace import GitUrlError, parse_github_url

OK_URL = "https://github.com/acme/widget"


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    real_connect = socket.socket.connect

    def guarded(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise AssertionError(f"test tried to open a real network connection to {address!r}")
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded)


def zip_bytes(entries) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            info = zipfile.ZipInfo("x")
            info.filename = name
            zf.writestr(info, data)
    return buf.getvalue()


def good_archive() -> bytes:
    return zip_bytes([("widget-main/README.md", "# widget\n" * 20), ("widget-main/src/app.py", "print('hi')\n" * 20)])


class FakeResponse:
    def __init__(self, status=200, chunks=(), headers=None):
        self.status_code = status
        self.headers = headers or {}
        self._chunks = list(chunks)
        self.consumed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def aiter_bytes(self):
        for chunk in self._chunks:
            self.consumed += len(chunk)
            yield chunk


def install_fake(monkeypatch, routes, raises=None):
    """routes: {url: FakeResponse}; any other URL answers 404. Returns the list of requested URLs."""
    requested: list[str] = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, method, url):
            requested.append(url)
            if raises is not None:
                raise raises
            assert method == "GET"
            return routes.get(url) or FakeResponse(404)

    monkeypatch.setattr(projects_api, "httpx", SimpleNamespace(AsyncClient=FakeClient))
    return requested


def archive_url(owner="acme", repo="widget", branch="main") -> str:
    return f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"


def new_name() -> str:
    return f"g-{uuid.uuid4().hex[:10]}"


async def import_git(client, git_url=OK_URL, **extra):
    return await client.post("/api/projects/git", json={"name": new_name(), "git_url": git_url, **extra})


# ---------------------------------------------------------------------------------------------------------------
# URL parsing
# ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("url,expected", [
    ("https://github.com/owner/repo", ("owner", "repo")),
    ("https://github.com/owner/repo.git", ("owner", "repo")),
    ("https://github.com/owner/repo/", ("owner", "repo")),
    ("https://github.com/owner/repo.git/", ("owner", "repo")),
    ("http://github.com/owner/repo", ("owner", "repo")),
    ("github.com/owner/repo", ("owner", "repo")),
    ("www.github.com/owner/repo", ("owner", "repo")),
    ("https://www.github.com/owner/repo.git", ("owner", "repo")),
    ("git@github.com:owner/repo.git", ("owner", "repo")),
    ("git@github.com:owner/repo", ("owner", "repo")),
    ("  https://github.com/owner/repo  ", ("owner", "repo")),
    ("https://github.com/owner/repo\r\n", ("owner", "repo")),
    ("https://GitHub.com/Owner/Repo", ("Owner", "Repo")),
    ("https://github.com/my-org/my_repo.v2", ("my-org", "my_repo.v2")),
    ("https://github.com/owner/.github", ("owner", ".github")),
    ("https://github.com/owner/repo.git.git", ("owner", "repo.git")),
    ("https://github.com/owner/my.git.repo", ("owner", "my.git.repo")),
    ("https://github.com/owner/repo.GIT", ("owner", "repo")),
])
def test_supported_urls(url, expected):
    assert parse_github_url(url) == expected


@pytest.mark.parametrize("repo", ["widget", "git", "it", "gist", "tig", "digit", "legit", "gt", "t", "g", "i", "tool.", "x.gi", "x.it"])
def test_repository_names_are_not_mangled_by_the_old_rstrip_bug(repo):
    """The old code used rstrip('.git'), which strips any trailing run of '.', 'g', 'i', 't' characters."""
    for url in (f"https://github.com/owner/{repo}", f"https://github.com/owner/{repo}/", f"https://github.com/owner/{repo}.git"):
        assert parse_github_url(url) == ("owner", repo), url


@pytest.mark.parametrize("url", [
    "https://github.com/owner/repo/tree/main",
    "https://github.com/owner/repo/issues",
    "https://github.com/owner/repo/blob/main/README.md",
    "https://github.com/owner/repo.git/tree/main",
    "https://github.com/owner/repo?tab=readme",
    "https://github.com/owner/repo#readme",
    "https://github.com/owner",
    "https://github.com/",
    "https://github.com",
    "https://github.com//repo",
    "https://github.com/owner//",
    "https://gitlab.com/owner/repo",
    "https://evil.com/github.com/owner/repo",
    "https://evil.com/?u=github.com/owner/repo",
    "https://github.com.evil.com/owner/repo",
    "https://notgithub.com/owner/repo",
    "https://user:pw@github.com/owner/repo",
    "https://github.com:443/owner/repo",
    "ssh://git@github.com/owner/repo.git",
    "git@gitlab.com:owner/repo.git",
    "ftp://github.com/owner/repo",
    "https://github.com/./repo",
    "https://github.com/../repo",
    "https://github.com/owner/.",
    "https://github.com/owner/..",
    "https://github.com/owner/.git",
    "https://github.com/owner/.git/",
    "https://github.com/owner/re po",
    "https://github.com/owner/repo\nHost: evil.com",
    "https://github.com/own%2Fer/repo",
    "https://github.com/owner/ré",
    "https://github.com/ö/repo",
    "https://github.com/" + "o" * 101 + "/repo",
    "https://github.com/owner/" + "r" * 101,
    "",
    "   ",
    "owner/repo",
    "not a url",
])
def test_everything_else_is_refused(url):
    with pytest.raises(GitUrlError):
        parse_github_url(url)


@pytest.mark.parametrize("value", [None, 5, [], {}, b"https://github.com/o/r"])
def test_non_strings_are_refused(value):
    with pytest.raises(GitUrlError):
        parse_github_url(value)


# ---------------------------------------------------------------------------------------------------------------
# endpoint behaviour with a mocked GitHub
# ---------------------------------------------------------------------------------------------------------------

async def test_supported_url_imports_and_requests_the_exact_archive_of_the_right_repository(async_client, sandbox, monkeypatch):
    requested = install_fake(monkeypatch, {archive_url(): FakeResponse(200, [good_archive()])})
    res = await import_git(async_client)
    assert res.status_code == 201, res.text
    assert requested == [archive_url()], "the repository name 'widget' must not be altered"
    body = res.json()
    root = sandbox / "workspaces" / body["name"]
    assert (root / "README.md").exists() and (root / "src" / "app.py").exists()
    assert not (root / "widget-main").exists()
    assert body["description"] == "Imported from GitHub: acme/widget"
    assert body["file_count"] == 2


@pytest.mark.parametrize("git_url,repo", [
    ("https://github.com/acme/tool.git", "tool"),
    ("https://github.com/acme/tool/", "tool"),
    ("https://github.com/acme/tool.git/", "tool"),
    ("github.com/acme/tool", "tool"),
    ("git@github.com:acme/tool.git", "tool"),
    ("https://github.com/acme/git", "git"),
])
async def test_url_forms_all_request_the_same_correct_archive(async_client, monkeypatch, git_url, repo):
    requested = install_fake(monkeypatch, {archive_url(repo=repo): FakeResponse(200, [good_archive()])})
    res = await import_git(async_client, git_url)
    assert res.status_code == 201, res.text
    assert requested == [archive_url(repo=repo)]


async def test_falls_back_to_master_then_main_in_the_existing_order(async_client, monkeypatch):
    requested = install_fake(monkeypatch, {archive_url(branch="master"): FakeResponse(200, [good_archive()])})
    assert (await import_git(async_client, branch="dev")).status_code == 201
    assert requested == [archive_url(branch="dev"), archive_url(branch="master")]


async def test_default_branch_is_main_and_the_download_stops_at_the_first_success(async_client, monkeypatch):
    requested = install_fake(monkeypatch, {archive_url(): FakeResponse(200, [good_archive()])})
    assert (await import_git(async_client)).status_code == 201
    assert requested == [archive_url()]


@pytest.mark.parametrize("git_url", [
    "https://github.com/acme/widget/tree/main", "https://evil.com/github.com/acme/widget", "https://github.com/acme",
    "https://github.com/../widget", "not a url", "https://github.com/acme/widget?x=1",
])
async def test_invalid_urls_are_400_before_any_network_call_and_create_nothing(async_client, sandbox, monkeypatch, git_url):
    requested = install_fake(monkeypatch, {})
    name = new_name()
    res = await async_client.post("/api/projects/git", json={"name": name, "git_url": git_url})
    assert res.status_code == 400
    assert res.json()["detail"] == "Invalid GitHub URL. Format must be: https://github.com/owner/repository"
    assert requested == []
    assert not (sandbox / "workspaces" / name).exists()
    assert (await async_client.get(f"/api/projects/{name}")).status_code == 404


async def test_existing_project_name_is_409_before_any_network_call(async_client, project, monkeypatch):
    requested = install_fake(monkeypatch, {})
    res = await async_client.post("/api/projects/git", json={"name": project["name"], "git_url": OK_URL})
    assert res.status_code == 409
    assert requested == []


async def test_repository_that_cannot_be_downloaded_is_a_generic_400(async_client, sandbox, monkeypatch):
    requested = install_fake(monkeypatch, {})
    name = new_name()
    res = await async_client.post("/api/projects/git", json={"name": name, "git_url": OK_URL})
    assert res.status_code == 400
    assert "Could not download repository archive from GitHub (acme/widget)" in res.json()["detail"]
    assert len(requested) == 3  # branch (main), master, main
    assert not (sandbox / "workspaces" / name).exists()


async def test_a_tiny_response_is_not_accepted_as_an_archive(async_client, monkeypatch):
    requested = install_fake(monkeypatch, {archive_url(): FakeResponse(200, [b"PK" * 10])})
    res = await import_git(async_client)
    assert res.status_code == 400
    assert "Could not download repository archive" in res.json()["detail"]  # treated as "no archive", not as a corrupt ZIP
    assert len(requested) == 3  # and the other branches were still tried


async def test_network_failures_do_not_leak_their_message(async_client, sandbox, monkeypatch):
    install_fake(monkeypatch, {}, raises=RuntimeError("secret-proxy-credentials user:hunter2@10.0.0.5"))
    name = new_name()
    res = await async_client.post("/api/projects/git", json={"name": name, "git_url": OK_URL})
    assert res.status_code == 400
    assert "hunter2" not in res.text and "secret" not in res.text
    assert not (sandbox / "workspaces" / name).exists()


# ---------------------------------------------------------------------------------------------------------------
# download size limit (counted on the bytes actually received)
# ---------------------------------------------------------------------------------------------------------------

async def test_download_over_the_limit_is_413_and_reading_stops_early(async_client, sandbox, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1000)
    response = FakeResponse(200, [b"x" * 400] * 1000)  # no Content-Length: only the bytes received can tell
    requested = install_fake(monkeypatch, {archive_url(): response})
    name = new_name()
    res = await async_client.post("/api/projects/git", json={"name": name, "git_url": OK_URL})
    assert res.status_code == 413
    assert "1000 byte limit" in res.json()["detail"]
    assert response.consumed <= 1000 + 400, f"kept downloading: {response.consumed} bytes read"
    assert requested == [archive_url()], "an oversized archive must not trigger the fallback branches"
    assert not (sandbox / "workspaces" / name).exists()


async def test_a_lying_content_length_cannot_get_past_the_limit(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1000)
    response = FakeResponse(200, [b"x" * 600] * 50, headers={"content-length": "10"})
    install_fake(monkeypatch, {archive_url(): response})
    assert (await import_git(async_client)).status_code == 413
    assert response.consumed <= 1000 + 600


async def test_declared_oversize_is_refused_without_reading_the_body(async_client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", 1000)
    response = FakeResponse(200, [b"x" * 600] * 50, headers={"content-length": "999999999"})
    install_fake(monkeypatch, {archive_url(): response})
    assert (await import_git(async_client)).status_code == 413
    assert response.consumed == 0


async def test_download_exactly_at_the_limit_is_accepted(async_client, monkeypatch):
    data = good_archive()
    monkeypatch.setattr(settings, "MAX_UPLOAD_BYTES", len(data))
    install_fake(monkeypatch, {archive_url(): FakeResponse(200, [data[:50], data[50:]])})
    assert (await import_git(async_client)).status_code == 201


async def test_a_streamed_download_in_many_chunks_is_reassembled(async_client, sandbox, monkeypatch):
    data = good_archive()
    install_fake(monkeypatch, {archive_url(): FakeResponse(200, [data[i:i + 7] for i in range(0, len(data), 7)])})
    res = await import_git(async_client)
    assert res.status_code == 201
    assert (sandbox / "workspaces" / res.json()["name"] / "src" / "app.py").read_text() == "print('hi')\n" * 20


# ---------------------------------------------------------------------------------------------------------------
# a downloaded archive gets exactly the same protections as an uploaded one
# ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad_name", ["../../evil.py", "/etc/evil.py", "C:/evil.py", "a.txt:stream", "dir/con.txt"])
async def test_unsafe_entries_in_a_downloaded_archive_reject_it_whole(async_client, sandbox, monkeypatch, bad_name):
    data = zip_bytes([("repo-main/ok.py", "ok" * 100), (bad_name, "x" * 200)])
    install_fake(monkeypatch, {archive_url(): FakeResponse(200, [data])})
    name = new_name()
    res = await async_client.post("/api/projects/git", json={"name": name, "git_url": OK_URL})
    assert res.status_code == 400
    assert res.json()["detail"] == "The archive contains an unsafe or unsupported entry, so nothing was imported."
    assert not (sandbox / "workspaces" / name).exists()
    assert not (sandbox / "evil.py").exists()


async def test_a_downloaded_zip_bomb_is_413(async_client, sandbox, monkeypatch):
    monkeypatch.setattr(settings, "MAX_ZIP_UNCOMPRESSED_BYTES", 100_000)
    data = zip_bytes([("repo/zeros.bin", b"\0" * 2_000_000)])
    install_fake(monkeypatch, {archive_url(): FakeResponse(200, [data])})
    name = new_name()
    res = await async_client.post("/api/projects/git", json={"name": name, "git_url": OK_URL})
    assert res.status_code == 413
    assert not (sandbox / "workspaces" / name).exists()


async def test_a_corrupt_download_is_a_generic_400(async_client, sandbox, monkeypatch):
    install_fake(monkeypatch, {archive_url(): FakeResponse(200, [b"<html>rate limited</html>" * 20])})
    name = new_name()
    res = await async_client.post("/api/projects/git", json={"name": name, "git_url": OK_URL})
    assert res.status_code == 400
    assert res.json()["detail"] == "The file is not a valid ZIP archive, or it is corrupt or uses an unsupported format."
    assert not (sandbox / "workspaces" / name).exists()


async def test_unexpected_failure_after_download_is_a_generic_500(async_client, sandbox, monkeypatch):
    install_fake(monkeypatch, {archive_url(): FakeResponse(200, [good_archive()])})

    def boom(path):
        raise ValueError("secret-after-extract C:\\private")

    monkeypatch.setattr(projects_api, "detect_project_languages", boom)
    name = new_name()
    res = await async_client.post("/api/projects/git", json={"name": name, "git_url": OK_URL})
    assert res.status_code == 500
    assert res.json()["detail"] == "The project could not be imported."
    assert "secret" not in res.text
    assert not (sandbox / "workspaces" / name).exists()

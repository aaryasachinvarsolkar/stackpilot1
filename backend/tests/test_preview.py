"""Live preview: how a project is detected, what is served, and what is never served."""
import os
from pathlib import Path

import pytest

from app.services import preview

HTML = '<!doctype html><html><head><link rel="stylesheet" href="style.css"></head><body><h1>Hello</h1><script src="app.js"></script></body></html>'


@pytest.fixture
def root(project) -> Path:
    path = Path(project["root_path"])
    # the starter template may add files of its own; the tests need a known, empty project
    for child in list(path.iterdir()):
        if child.is_dir():
            import shutil
            shutil.rmtree(child)
        else:
            child.unlink()
    return path


def info_url(project):
    return f"/api/projects/{project['id']}/preview-info"


def file_url(project, rel):
    return f"/api/projects/{project['id']}/preview/{rel}"


# --- detection -------------------------------------------------------------------------------------------------------
async def test_a_root_index_html_is_a_static_page(async_client, project, root):
    (root / "index.html").write_text(HTML)
    body = (await async_client.get(info_url(project))).json()
    assert body["kind"] == "static" and body["entry"] == "index.html" and body["needs_backend"] is False


async def test_the_shallowest_and_most_usual_folder_wins(async_client, project, root):
    (root / "frontend").mkdir()
    (root / "frontend" / "index.html").write_text(HTML)
    (root / "docs").mkdir()
    (root / "docs" / "index.html").write_text(HTML)
    (root / "deep" / "er" / "x").mkdir(parents=True)
    (root / "deep" / "er" / "x" / "index.html").write_text(HTML)
    body = (await async_client.get(info_url(project))).json()
    assert body["entry"] == "frontend/index.html"
    assert [c["path"] for c in body["candidates"]][:2] == ["frontend/index.html", "docs/index.html"]


async def test_a_page_with_a_backend_is_still_shown_but_flagged(async_client, project, root):
    (root / "frontend").mkdir()
    (root / "frontend" / "index.html").write_text(HTML)
    (root / "requirements.txt").write_text("fastapi==0.110\nuvicorn\n")
    body = (await async_client.get(info_url(project))).json()
    assert body["kind"] == "static" and body["needs_backend"] is True
    assert any("FastAPI" in h for h in body["hints"]) and "start the backend" in body["message"]


async def test_a_framework_project_without_a_page_is_reported_as_needing_a_server_and_is_not_run(async_client, project, root):
    (root / "package.json").write_text('{"scripts": {"dev": "next dev"}, "dependencies": {"next": "14.0.0", "react": "18"}}')
    body = (await async_client.get(info_url(project))).json()
    assert body["kind"] == "server" and body["entry"] is None
    assert any("Next.js" in h for h in body["hints"]) and "needs a running server" in body["message"]


async def test_a_project_with_nothing_to_show_says_so(async_client, project, root):
    (root / "notes.txt").write_text("hi")
    body = (await async_client.get(info_url(project))).json()
    assert body["kind"] == "none" and "index.html" in body["message"]


async def test_pages_inside_dependency_and_hidden_folders_are_not_candidates(async_client, project, root):
    for folder in ("node_modules/pkg", ".git/x", ".hidden"):
        (root / folder).mkdir(parents=True)
        (root / folder / "index.html").write_text(HTML)
    assert (await async_client.get(info_url(project))).json()["kind"] == "none"


# --- serving ---------------------------------------------------------------------------------------------------------
async def test_files_are_served_with_the_right_type_and_isolation_headers(async_client, project, root):
    (root / "index.html").write_text(HTML)
    (root / "style.css").write_text("h1{color:red}")
    (root / "app.js").write_text("console.log(1)")
    page = await async_client.get(file_url(project, "index.html"))
    assert page.status_code == 200 and page.text == HTML
    assert page.headers["content-type"].startswith("text/html")
    csp = page.headers["content-security-policy"]
    assert csp.startswith("sandbox ") and "allow-scripts" in csp and "allow-same-origin" not in csp
    assert page.headers["cache-control"] == "no-store" and page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["access-control-allow-origin"] == "*"
    assert (await async_client.get(file_url(project, "style.css"))).headers["content-type"].startswith("text/css")
    assert (await async_client.get(file_url(project, "app.js"))).headers["content-type"].startswith("text/javascript")


async def test_a_folder_address_serves_its_index_page(async_client, project, root):
    (root / "site").mkdir()
    (root / "site" / "index.html").write_text(HTML)
    assert (await async_client.get(file_url(project, "site/"))).text == HTML
    assert (await async_client.get(file_url(project, "site"))).text == HTML


async def test_a_change_on_disk_shows_on_the_next_request(async_client, project, root):
    (root / "index.html").write_text("<h1>one</h1>")
    assert "one" in (await async_client.get(file_url(project, "index.html"))).text
    (root / "index.html").write_text("<h1>two</h1>")
    assert "two" in (await async_client.get(file_url(project, "index.html"))).text


@pytest.mark.parametrize("rel", [".env", ".env.local", "secrets.json", "credentials.yml", "server.pem", "id_rsa", ".git/config", "node_modules/x/index.js", ".hidden/a.txt", "sub/.env"])
async def test_secrets_dotfiles_and_dependency_folders_are_never_served(async_client, project, root, rel):
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("SECRET=1")
    res = await async_client.get(file_url(project, rel))
    assert res.status_code == 404 and "SECRET" not in res.text


@pytest.mark.parametrize("rel", ["../outside.txt", "..%2foutside.txt", "%2e%2e/outside.txt", "a/../../outside.txt", "..\\outside.txt", "C:/Windows/win.ini", "/etc/passwd"])
async def test_paths_cannot_escape_the_project(async_client, project, root, rel):
    (root.parent / "outside.txt").write_text("OUTSIDE")
    try:
        res = await async_client.get(file_url(project, rel))
        assert res.status_code in (400, 404) and "OUTSIDE" not in res.text
    finally:
        (root.parent / "outside.txt").unlink(missing_ok=True)


async def test_a_link_pointing_outside_the_project_is_not_served(async_client, project, root):
    outside = root.parent / "target-outside.txt"
    outside.write_text("OUTSIDE")
    try:
        os.symlink(outside, root / "link.txt")
    except (OSError, NotImplementedError):
        outside.unlink()
        pytest.skip("this system cannot create symbolic links")
    try:
        res = await async_client.get(file_url(project, "link.txt"))
        assert res.status_code == 404 and "OUTSIDE" not in res.text
    finally:
        outside.unlink(missing_ok=True)


async def test_a_missing_file_is_a_404_that_is_still_sandboxed(async_client, project, root):
    res = await async_client.get(file_url(project, "nope.html"))
    assert res.status_code == 404 and "sandbox" in res.headers["content-security-policy"]


async def test_a_huge_file_is_refused(async_client, project, root, monkeypatch):
    (root / "big.bin").write_bytes(b"x" * 2048)
    monkeypatch.setattr(preview, "MAX_SERVED_BYTES", 1024)
    assert (await async_client.get(file_url(project, "big.bin"))).status_code == 404


# --- addressing ------------------------------------------------------------------------------------------------------
async def test_a_project_is_addressed_by_id_never_by_name(async_client, project, root):
    (root / "index.html").write_text(HTML)
    by_name = f"/api/projects/{project['name']}/preview/index.html"
    assert (await async_client.get(by_name)).status_code == 404
    assert (await async_client.get(f"/api/projects/{project['name']}/preview-info")).status_code == 404
    assert (await async_client.get("/api/projects/does-not-exist/preview/index.html")).status_code == 404


async def test_a_wrong_host_header_is_refused_for_previews_too(async_client, project, root):
    (root / "index.html").write_text(HTML)
    res = await async_client.get(file_url(project, "index.html"), headers={"Host": "evil.example"})
    assert res.status_code == 400


def test_the_preview_never_starts_a_process():
    import ast

    for module in ("services/preview.py", "api/preview.py"):
        source = (Path(preview.__file__).parent.parent / module).read_text(encoding="utf-8")
        names = {n.module for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Import) for a in n.names}
        assert not names & {"subprocess", "os.system", "multiprocessing", "pty"}, f"{module} must not start processes"
        assert "os.system(" not in source and "Popen(" not in source and "exec(" not in source and "eval(" not in source

"""Host-header allowlist: with no authentication, the API must only answer requests addressed to a loopback name.

A page on another site can make a browser send requests to 127.0.0.1 under its own host name (DNS rebinding), which CORS does
not stop. The check runs before routing, so a rejected request never reaches an endpoint.
"""
import re
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import app

REPO = Path(__file__).resolve().parents[2]
BAD_HOSTS = [
    "evil.com",
    "evil.com:8000",
    "localhost.evil.com",
    "127.0.0.1.evil.com",
    "evil.com/127.0.0.1",
    "localhost@evil.com",
    "0.0.0.0",
    "0.0.0.0:8000",
    "127.0.0.2",
    "192.168.1.10:8000",
    "[::1]:8000",
    "testserver",
]


async def get(host: str, path: str = "/health", method: str = "GET", **kwargs):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        return await client.request(method, path, headers={"Host": host}, **kwargs)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "127.0.0.1:8000", "localhost:8000", "localhost:3000"])
async def test_loopback_hosts_are_answered(host):
    res = await get(host)
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


@pytest.mark.parametrize("host", BAD_HOSTS)
async def test_other_hosts_are_refused_with_400(host):
    res = await get(host)
    assert res.status_code == 400
    assert res.text == "Invalid host header"


@pytest.mark.parametrize("path", ["/health", "/api/projects", "/docs", "/openapi.json", "/redoc", "/no-such-route"])
async def test_every_path_is_guarded_including_docs_and_unknown_routes(path):
    assert (await get("evil.com", path)).status_code == 400
    assert (await get("localhost", path)).status_code != 400


async def test_request_without_a_host_header_is_refused():
    sent: dict = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            sent["status"] = message["status"]

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.0", "method": "GET", "scheme": "http",
        "path": "/health", "raw_path": b"/health", "query_string": b"", "headers": [], "server": ("127.0.0.1", 8000),
        "client": ("127.0.0.1", 50000),
    }
    await app(scope, receive, send)
    assert sent["status"] == 400


async def test_rejected_request_never_reaches_the_endpoint(sandbox):
    """A state-changing request with a bad Host is refused before the handler runs: nothing is created."""
    name = f"h-{uuid.uuid4().hex[:10]}"
    res = await get("evil.com", "/api/projects", "POST", json={"name": name, "source_type": "blank"})
    assert res.status_code == 400
    assert not (sandbox / "workspaces" / name).exists()
    assert (await get("localhost", f"/api/projects/{name}")).status_code == 404


async def test_rejected_upload_is_not_even_parsed(sandbox):
    name = f"h-{uuid.uuid4().hex[:10]}"
    res = await get(
        "evil.com", "/api/projects/upload", "POST", data={"name": name}, files={"file": ("a.zip", b"PK\x03\x04junk")}
    )
    assert res.status_code == 400
    assert not (sandbox / "workspaces" / name).exists()


async def test_cors_preflight_with_a_bad_host_gets_400_and_no_cors_headers():
    headers = {"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        bad = await client.options("/api/projects", headers={**headers, "Host": "evil.com"})
        good = await client.options("/api/projects", headers={**headers, "Host": "localhost:8000"})
    assert bad.status_code == 400
    assert "access-control-allow-origin" not in bad.headers
    assert good.status_code == 200
    assert good.headers["access-control-allow-origin"] == "http://localhost:3000"


async def test_a_trusted_host_with_an_untrusted_origin_is_still_not_given_cors_access():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://127.0.0.1") as client:
        res = await client.options(
            "/api/projects",
            headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "POST", "Host": "localhost"},
        )
    assert res.headers.get("access-control-allow-origin") != "http://evil.com"


def test_host_check_is_the_outermost_layer_and_cors_wraps_the_size_guard():
    order = [m.cls.__name__ for m in app.user_middleware]  # first = outermost
    assert order[0] == "TrustedHostMiddleware"
    assert order.index("CORSMiddleware") < order.index("UploadSizeLimitMiddleware")


# ---- configuration ----------------------------------------------------------------------------------------------

def test_default_allowlist_is_exactly_the_loopback_names(monkeypatch):
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)
    assert Settings(_env_file=None).ALLOWED_HOSTS == ["127.0.0.1", "localhost"]


def test_allowlist_comes_from_a_comma_separated_variable_and_is_normalized():
    assert Settings(_env_file=None, ALLOWED_HOSTS=" LocalHost , 127.0.0.1 ,, ").ALLOWED_HOSTS == ["localhost", "127.0.0.1"]


@pytest.mark.parametrize(
    "value",
    ["*", "localhost,*", "*.example.com", "", " , ", "http://localhost", "localhost:8000", "localhost/", "user@localhost", "a b"],
)
def test_unsafe_allowlist_values_are_refused_at_startup(value):
    with pytest.raises(ValueError):
        Settings(_env_file=None, ALLOWED_HOSTS=value)


def test_env_example_documents_the_loopback_allowlist():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    match = re.search(r"^ALLOWED_HOSTS=(.*)$", text, re.M)
    assert match, ".env.example must document ALLOWED_HOSTS"
    assert [h.strip() for h in match.group(1).split(",")] == ["127.0.0.1", "localhost"]

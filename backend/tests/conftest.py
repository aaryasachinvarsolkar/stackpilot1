"""Test harness: every test session runs against a throwaway database and a throwaway
working directory. The developer database (backend/stackpilot.db) and the real
backend/workspaces folder are never opened for writing.
"""
import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Callable

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

BACKEND_DIR = Path(__file__).resolve().parent.parent
REAL_DB = BACKEND_DIR / "stackpilot.db"
REAL_WORKSPACES = BACKEND_DIR / "workspaces"

# Must happen before `app` is imported: pydantic-settings gives real environment
# variables priority over .env, so this overrides whatever DATABASE_URL is configured.
SANDBOX = Path(tempfile.mkdtemp(prefix="stackpilot-tests-")).resolve()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(SANDBOX / 'test.db').as_posix()}"
os.environ["WORKSPACES_ROOT"] = str(SANDBOX / "workspaces")
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "False"

from app.main import app  # noqa: E402
from app.database import engine, Base  # noqa: E402

# Hard guard: refuse to run if the engine could possibly point at real data.
_db_file = Path(engine.url.database or "").resolve()
if _db_file == REAL_DB.resolve() or SANDBOX not in _db_file.parents:
    raise RuntimeError(f"Refusing to run tests: engine points at {_db_file}, not the sandbox {SANDBOX}")


def _snapshot_real_data() -> dict:
    """Fingerprint of the real DB file and every real workspace file (read-only)."""
    def digest(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    files = {}
    if REAL_WORKSPACES.exists():
        for p in sorted(REAL_WORKSPACES.rglob("*")):
            files[p.relative_to(REAL_WORKSPACES).as_posix()] = digest(p) if p.is_file() else "<dir>"
    return {"db": digest(REAL_DB) if REAL_DB.exists() else None, "workspaces": files}


_REAL_DATA_AT_START = _snapshot_real_data()


@pytest.fixture(scope="session")
def sandbox() -> Path:
    """The per-session temp directory that holds the test DB and workspaces/."""
    return SANDBOX


@pytest.fixture(scope="session")
def real_data_changed() -> Callable[[], bool]:
    """Returns a callable that is True if real dev data differs from session start."""
    return lambda: _snapshot_real_data() != _REAL_DATA_AT_START


@pytest.fixture(scope="session", autouse=True)
def sandbox_cwd():
    """Run from the sandbox so cwd-relative paths (workspaces/) never touch the repo."""
    previous = os.getcwd()
    os.chdir(SANDBOX)
    try:
        yield
    finally:
        os.chdir(previous)
        shutil.rmtree(SANDBOX, ignore_errors=True)
        assert _snapshot_real_data() == _REAL_DATA_AT_START, (
            "REAL development data changed during the test session!"
        )


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db(sandbox_cwd):
    """Create the schema in the sandbox database, and remove everything afterwards."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def project(async_client) -> dict:
    """A real project created through the API with a unique name (starter files on disk)."""
    name = f"t-{uuid.uuid4().hex[:10]}"
    res = await async_client.post("/api/projects", json={"name": name, "source_type": "blank"})
    assert res.status_code == 201, res.text
    return res.json()


@pytest_asyncio.fixture
async def async_client():
    """Yield an HTTPX AsyncClient bound to the FastAPI ASGI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

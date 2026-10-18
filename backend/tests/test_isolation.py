"""Guards that prove the test session cannot touch real development data."""
from pathlib import Path

from app.config import settings
from app.database import engine

from tests.conftest import REAL_DB, REAL_WORKSPACES


def test_database_is_the_sandbox_copy(sandbox: Path):
    db_file = Path(engine.url.database).resolve()
    assert db_file != REAL_DB.resolve()
    assert sandbox in db_file.parents
    assert str(sandbox.as_posix()) in settings.DATABASE_URL


def test_cwd_is_the_sandbox_not_the_repo(sandbox: Path):
    cwd = Path.cwd().resolve()
    assert cwd == sandbox
    assert REAL_WORKSPACES.resolve() not in cwd.parents


async def test_workspaces_are_created_in_the_sandbox(async_client, sandbox: Path):
    res = await async_client.post("/api/projects", json={"name": "isolation-probe", "source_type": "blank"})
    assert res.status_code == 201
    root = Path(res.json()["root_path"]).resolve()
    assert sandbox in root.parents
    assert REAL_WORKSPACES.resolve() not in root.parents


def test_real_dev_data_untouched_so_far(real_data_changed):
    assert real_data_changed() is False

import asyncio
import hashlib
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models.code_chunk import CodeChunk
from app.models.project import Project, ProjectFile
from app.services.indexer import (
    get_project_lock,
    index_project_workspace,
    scan_workspace_files,
    is_link_or_reparse_point,
)


@pytest.fixture
async def multi_lang_project(async_client: AsyncClient, sandbox: Path):
    """Create a project with Python, TypeScript, TSX, JavaScript, and Go source files."""
    import uuid
    proj_name = f"test-ml-{uuid.uuid4().hex[:8]}"
    create_res = await async_client.post(
        "/api/projects",
        json={"name": proj_name, "template": "FastAPI + Python"},
    )
    assert create_res.status_code == 201
    proj_data = create_res.json()

    root = Path(proj_data["root_path"])

    # Python file with class and functions
    (root / "calculator.py").write_text(
        '"""Calculator module."""\n\n'
        "class Calculator:\n"
        '    """Calculator service."""\n'
        "    def add(self, a: int, b: int) -> int:\n"
        "        return a + b\n\n"
        "def helper():\n"
        "    return 1\n",
        encoding="utf-8",
    )

    # TypeScript file with interface and class
    (root / "types.ts").write_text(
        "export interface User {\n"
        "    id: string;\n"
        "    name: string;\n"
        "}\n\n"
        "export class UserManager {\n"
        "    getUser(id: string): User {\n"
        '        return { id, name: "Alice" };\n'
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    # TSX component file
    (root / "Button.tsx").write_text(
        "import React from 'react';\n\n"
        "export function Button({ label }: { label: string }) {\n"
        "    return <button>{label}</button>;\n"
        "}\n",
        encoding="utf-8",
    )

    # JavaScript file
    (root / "utils.js").write_text(
        "function formatOutput(data) {\n"
        "    return JSON.stringify(data);\n"
        "}\n\n"
        "const logger = (msg) => console.log(msg);\n",
        encoding="utf-8",
    )

    # Go file with struct and method
    (root / "service.go").write_text(
        "package service\n\n"
        "type Config struct {\n"
        "    Port int\n"
        "}\n\n"
        "func (c *Config) GetPort() int {\n"
        "    return c.Port\n"
        "}\n\n"
        "func Start() error {\n"
        "    return nil\n"
        "}\n",
        encoding="utf-8",
    )

    return proj_data


async def test_successful_multi_language_indexing(async_client: AsyncClient, multi_lang_project: dict):
    proj_id = multi_lang_project["id"]
    res = await async_client.post(f"/api/projects/{proj_id}/index")
    assert res.status_code == 200
    data = res.json()

    assert data["project_id"] == proj_id
    assert data["status"] == "completed"
    assert data["files_indexed"] >= 5
    assert data["chunks_created"] >= 8
    assert data["errors"] == []
    assert data["duration_seconds"] is not None

    # Check database persistence
    async with AsyncSessionLocal() as session:
        proj = await session.get(Project, proj_id)
        assert proj.is_indexed is True
        assert proj.last_indexed_at is not None

        chunks_res = await session.execute(
            select(CodeChunk).where(CodeChunk.project_id == proj_id)
        )
        chunks = chunks_res.scalars().all()
        assert len(chunks) == data["chunks_created"]

        # Check symbol names and types
        sym_names = {c.symbol_name for c in chunks if c.symbol_name}
        assert "Calculator" in sym_names
        assert "add" in sym_names
        assert "User" in sym_names
        assert "UserManager" in sym_names
        assert "Button" in sym_names
        assert "formatOutput" in sym_names
        assert "Config" in sym_names

        # Check 1-based line ranges
        for c in chunks:
            assert c.start_line >= 1
            assert c.end_line >= c.start_line
            assert len(c.content) > 0


async def test_module_chunk_for_script_without_functions(async_client: AsyncClient, multi_lang_project: dict):
    root = Path(multi_lang_project["root_path"])
    (root / "constants.ts").write_text(
        "export const API_URL = 'http://localhost';\n"
        "export const TIMEOUT = 5000;\n",
        encoding="utf-8",
    )

    res = await async_client.post(f"/api/projects/{multi_lang_project['id']}/index")
    assert res.status_code == 200

    async with AsyncSessionLocal() as session:
        pf_res = await session.execute(
            select(ProjectFile).where(
                ProjectFile.project_id == multi_lang_project["id"],
                ProjectFile.file_path == "constants.ts",
            )
        )
        pf = pf_res.scalar_one()
        chunk_res = await session.execute(
            select(CodeChunk).where(CodeChunk.file_id == pf.id)
        )
        chunks = chunk_res.scalars().all()
        assert len(chunks) == 1
        assert chunks[0].chunk_type == "module"
        assert chunks[0].symbol_name is None
        assert "API_URL" in chunks[0].content


async def test_repeatable_idempotent_indexing(async_client: AsyncClient, multi_lang_project: dict):
    proj_id = multi_lang_project["id"]

    # First index
    res1 = await async_client.post(f"/api/projects/{proj_id}/index")
    assert res1.status_code == 200
    first_count = res1.json()["chunks_created"]

    # Re-index without changing files
    res2 = await async_client.post(f"/api/projects/{proj_id}/index")
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["files_unchanged"] >= 5
    assert d2["files_indexed"] == 0
    assert d2["chunks_created"] == 0

    # Total chunks in DB must remain exactly the same
    async with AsyncSessionLocal() as session:
        total_chunks = (
            await session.execute(
                select(func.count()).select_from(CodeChunk).where(CodeChunk.project_id == proj_id)
            )
        ).scalar()
        assert total_chunks == first_count


async def test_modified_file_updates_chunks(async_client: AsyncClient, multi_lang_project: dict):
    proj_id = multi_lang_project["id"]
    await async_client.post(f"/api/projects/{proj_id}/index")

    # Modify calculator.py
    root = Path(multi_lang_project["root_path"])
    (root / "calculator.py").write_text(
        "class Calculator:\n"
        "    def multiply(self, a: int, b: int) -> int:\n"
        "        return a * b\n",
        encoding="utf-8",
    )

    res = await async_client.post(f"/api/projects/{proj_id}/index")
    assert res.status_code == 200
    d = res.json()
    assert d["files_indexed"] == 1
    assert d["files_unchanged"] >= 4

    # Verify updated chunks
    async with AsyncSessionLocal() as session:
        pf_res = await session.execute(
            select(ProjectFile).where(
                ProjectFile.project_id == proj_id,
                ProjectFile.file_path == "calculator.py",
            )
        )
        pf = pf_res.scalar_one()
        c_res = await session.execute(select(CodeChunk).where(CodeChunk.file_id == pf.id))
        chunks = c_res.scalars().all()
        syms = {c.symbol_name for c in chunks}
        assert "multiply" in syms
        assert "add" not in syms  # old symbol was removed


async def test_deleted_file_removes_stale_records(async_client: AsyncClient, multi_lang_project: dict):
    proj_id = multi_lang_project["id"]
    await async_client.post(f"/api/projects/{proj_id}/index")

    # Delete utils.js
    root = Path(multi_lang_project["root_path"])
    (root / "utils.js").unlink()

    res = await async_client.post(f"/api/projects/{proj_id}/index")
    assert res.status_code == 200
    d = res.json()
    assert d["files_removed"] == 1

    # Verify records are gone
    async with AsyncSessionLocal() as session:
        pf_res = await session.execute(
            select(ProjectFile).where(
                ProjectFile.project_id == proj_id,
                ProjectFile.file_path == "utils.js",
            )
        )
        assert pf_res.scalar_one_or_none() is None


async def test_secret_and_prohibited_files_are_never_indexed(async_client: AsyncClient, multi_lang_project: dict):
    root = Path(multi_lang_project["root_path"])
    (root / ".env").write_text("SECRET_KEY=12345", encoding="utf-8")
    (root / "secret.key").write_text("private-key-data", encoding="utf-8")
    (root / "credentials.json").write_text('{"user": "admin"}', encoding="utf-8")
    (root / "cert.pem").write_text("---PEM---", encoding="utf-8")

    (root / "node_modules").mkdir(exist_ok=True)
    (root / "node_modules" / "sub.js").write_text("function bad() {}", encoding="utf-8")

    (root / ".git").mkdir(exist_ok=True)
    (root / ".git" / "hook.py").write_text("def hook(): pass", encoding="utf-8")

    res = await async_client.post(f"/api/projects/{multi_lang_project['id']}/index")
    assert res.status_code == 200

    async with AsyncSessionLocal() as session:
        pf_res = await session.execute(
            select(ProjectFile.file_path).where(ProjectFile.project_id == multi_lang_project["id"])
        )
        paths = set(pf_res.scalars().all())
        assert ".env" not in paths
        assert "secret.key" not in paths
        assert "credentials.json" not in paths
        assert "cert.pem" not in paths
        assert not any("node_modules" in p for p in paths)
        assert not any(".git" in p for p in paths)


async def test_indexing_status_endpoint(async_client: AsyncClient, multi_lang_project: dict):
    proj_id = multi_lang_project["id"]

    # Before index
    s0 = await async_client.get(f"/api/projects/{proj_id}/index/status")
    assert s0.status_code == 200
    assert s0.json()["status"] in ("idle", "completed")

    # Run index
    await async_client.post(f"/api/projects/{proj_id}/index")

    # After index
    s1 = await async_client.get(f"/api/projects/{proj_id}/index/status")
    assert s1.status_code == 200
    d = s1.json()
    assert d["status"] == "completed"
    assert d["files_indexed"] >= 5
    assert d["duration_seconds"] is not None


async def test_unknown_project_returns_404(async_client: AsyncClient):
    res = await async_client.post("/api/projects/non-existent-proj-id/index")
    assert res.status_code == 404

    res_status = await async_client.get("/api/projects/non-existent-proj-id/index/status")
    assert res_status.status_code == 404


async def test_concurrent_indexing_returns_409(async_client: AsyncClient, multi_lang_project: dict):
    proj_id = multi_lang_project["id"]
    lock = await get_project_lock(proj_id)

    # Acquire lock externally to simulate long-running job in progress
    await lock.acquire()
    try:
        res = await async_client.post(f"/api/projects/{proj_id}/index")
        assert res.status_code == 409
        assert "already in progress" in res.json()["detail"]
    finally:
        lock.release()


async def test_oversized_files_are_skipped(async_client: AsyncClient, multi_lang_project: dict):
    root = Path(multi_lang_project["root_path"])
    # Create an oversized file (600 KB > 512 KB limit)
    (root / "oversized.py").write_text("# " + "x" * (600 * 1024), encoding="utf-8")

    res = await async_client.post(f"/api/projects/{multi_lang_project['id']}/index")
    assert res.status_code == 200

    async with AsyncSessionLocal() as session:
        pf = (
            await session.execute(
                select(ProjectFile).where(
                    ProjectFile.project_id == multi_lang_project["id"],
                    ProjectFile.file_path == "oversized.py",
                )
            )
        ).scalar_one_or_none()
        assert pf is None  # Oversized file was skipped


async def test_unreadable_file_fault_isolation(async_client: AsyncClient, multi_lang_project: dict, monkeypatch):
    proj_id = multi_lang_project["id"]
    root = Path(multi_lang_project["root_path"])
    (root / "bad_read.py").write_text("def will_fail(): pass\n", encoding="utf-8")

    orig_read_bytes = Path.read_bytes

    def mock_read_bytes(self):
        if self.name == "bad_read.py":
            raise PermissionError("Simulated I/O permission denied")
        return orig_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", mock_read_bytes)

    res = await async_client.post(f"/api/projects/{proj_id}/index")
    assert res.status_code == 200
    d = res.json()
    assert d["status"] == "completed_with_errors"
    assert any("bad_read.py" in err for err in d["errors"])

    # Other valid files must still be indexed
    assert d["files_indexed"] >= 5

    # Project is_indexed must NOT be marked True when errors occurred
    async with AsyncSessionLocal() as session:
        proj = await session.get(Project, proj_id)
        assert proj.is_indexed is False


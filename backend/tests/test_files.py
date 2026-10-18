import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_file_tree(async_client: AsyncClient):
    """Verify retrieving project file tree returns valid nested hierarchy."""
    # List projects to get an existing project
    list_res = await async_client.get("/api/projects")
    projects = list_res.json()
    proj_id = projects[0]["id"]

    tree_res = await async_client.get(f"/api/projects/{proj_id}/files/tree")
    assert tree_res.status_code == 200
    tree_data = tree_res.json()
    assert isinstance(tree_data, list)
    assert len(tree_data) > 0
    # First item should have name and path
    assert "name" in tree_data[0]
    assert "path" in tree_data[0]


@pytest.mark.asyncio
async def test_get_file_content(async_client: AsyncClient):
    """Verify reading file content."""
    list_res = await async_client.get("/api/projects")
    proj_id = list_res.json()[0]["id"]

    res = await async_client.get(f"/api/projects/{proj_id}/files/content?path=app/api/routes.py")
    assert res.status_code == 200
    data = res.json()
    assert data["path"] == "app/api/routes.py"
    assert data["file_name"] == "routes.py"
    assert "content" in data
    assert data["line_count"] > 0
    assert data["language"] == "python"


@pytest.mark.asyncio
async def test_save_file_content(async_client: AsyncClient):
    """Verify saving file content."""
    list_res = await async_client.get("/api/projects")
    proj_id = list_res.json()[0]["id"]

    save_payload = {
        "path": "app/test_file.py",
        "content": "# Test file content\nprint('hello world')\n",
    }
    res = await async_client.put(f"/api/projects/{proj_id}/files/content", json=save_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "saved"
    assert data["path"] == "app/test_file.py"
    assert data["bytes_written"] > 0


@pytest.mark.asyncio
async def test_path_traversal_prevention(async_client: AsyncClient):
    """Verify path traversal attempts are rejected with 400 Bad Request."""
    list_res = await async_client.get("/api/projects")
    proj_id = list_res.json()[0]["id"]

    res = await async_client.get(f"/api/projects/{proj_id}/files/content?path=../../etc/passwd")
    assert res.status_code == 400
    assert "Path traversal is strictly prohibited" in res.json()["detail"]

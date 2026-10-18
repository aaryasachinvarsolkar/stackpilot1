import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_projects(async_client: AsyncClient):
    """Verify that listing projects returns HTTP 200 and a non-empty list (auto-seeded)."""
    response = await async_client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    first_proj = data[0]
    assert "id" in first_proj
    assert "name" in first_proj
    assert "languages" in first_proj


@pytest.mark.asyncio
async def test_create_and_get_project(async_client: AsyncClient):
    """Verify creating a project and retrieving it by ID."""
    payload = {
        "name": "test-analytics-engine",
        "description": "Real-time analytics engine with FastAPI",
        "source_type": "blank",
        "template": "FastAPI + Python",
    }
    create_res = await async_client.post("/api/projects", json=payload)
    assert create_res.status_code == 201
    created_data = create_res.json()
    project_id = created_data["id"]
    assert created_data["name"] == "test-analytics-engine"
    assert created_data["file_count"] > 0
    assert "Python" in created_data["languages"]

    # Retrieve by ID
    get_res = await async_client.get(f"/api/projects/{project_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == project_id
    assert get_res.json()["name"] == "test-analytics-engine"


@pytest.mark.asyncio
async def test_create_duplicate_project_error(async_client: AsyncClient):
    """Verify that creating a duplicate project returns HTTP 409."""
    payload = {
        "name": "duplicate-test-service",
        "source_type": "blank",
    }
    res1 = await async_client.post("/api/projects", json=payload)
    assert res1.status_code == 201

    res2 = await async_client.post("/api/projects", json=payload)
    assert res2.status_code == 409


@pytest.mark.asyncio
async def test_delete_project(async_client: AsyncClient):
    """Verify project deletion."""
    payload = {"name": "delete-me-service", "source_type": "blank"}
    create_res = await async_client.post("/api/projects", json=payload)
    proj_id = create_res.json()["id"]

    del_res = await async_client.delete(f"/api/projects/{proj_id}")
    assert del_res.status_code == 204

    # Verify 404 after deletion
    get_res = await async_client.get(f"/api/projects/{proj_id}")
    assert get_res.status_code == 404

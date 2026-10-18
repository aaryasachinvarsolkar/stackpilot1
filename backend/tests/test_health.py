import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client: AsyncClient):
    """Test that /health returns status 200 and healthy status."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_detailed_health_check_endpoint(async_client: AsyncClient):
    """Test that /api/health returns database connectivity and environment details."""
    response = await async_client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "database" in data
    assert "version" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_info_endpoint(async_client: AsyncClient):
    """Test that /api/info returns platform metadata."""
    response = await async_client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "STACKPILOT"
    assert "capabilities" in data
    assert len(data["capabilities"]) > 0
    assert "active_providers" in data

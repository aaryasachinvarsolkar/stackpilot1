import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_chat_history(async_client: AsyncClient):
    """Verify retrieving chat history."""
    list_res = await async_client.get("/api/projects")
    proj_id = list_res.json()[0]["id"]

    res = await async_client.get(f"/api/projects/{proj_id}/chat/history")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "sender" in data[0]
    assert "content" in data[0]


@pytest.mark.asyncio
async def test_send_chat_message_with_plan(async_client: AsyncClient):
    """Verify sending an engineering prompt generates citations and implementation plan."""
    list_res = await async_client.get("/api/projects")
    proj_id = list_res.json()[0]["id"]

    chat_payload = {
        "message": "Add rate limiting middleware to protected routes and write verification tests",
        "mode": "agent",
    }
    res = await async_client.post(f"/api/projects/{proj_id}/chat", json=chat_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["sender"] == "assistant"
    assert len(data["plan_steps"]) > 0
    assert len(data["citations"]) > 0
    first_citation = data["citations"][0]
    assert "file_path" in first_citation
    assert "line_start" in first_citation

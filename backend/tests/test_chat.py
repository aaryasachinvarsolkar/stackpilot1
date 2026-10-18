import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.api.chat import CHAT_UNAVAILABLE_DETAIL
from app.database import AsyncSessionLocal
from app.models.conversation import Conversation, Message


async def test_history_of_a_new_project_is_empty_not_an_invented_greeting(async_client: AsyncClient, project):
    res = await async_client.get(f"/api/projects/{project['id']}/chat/history")
    assert res.status_code == 200
    assert res.json() == []


async def test_history_returns_stored_messages_in_order(async_client: AsyncClient, project):
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with AsyncSessionLocal() as session:
        conv = Conversation(id=str(uuid.uuid4()), project_id=project["id"], title="t")
        session.add(conv)
        await session.flush()
        session.add_all(
            [
                Message(conversation_id=conv.id, sender="user", content="first", citations=[], plan_steps=[], created_at=t0),
                Message(
                    conversation_id=conv.id,
                    sender="assistant",
                    content="second",
                    citations=[],
                    plan_steps=[],
                    created_at=t0 + timedelta(seconds=1),
                ),
            ]
        )
        await session.commit()

    data = (await async_client.get(f"/api/projects/{project['id']}/chat/history")).json()
    assert [m["content"] for m in data] == ["first", "second"]
    assert {"id", "sender", "content", "citations", "plan_steps", "timestamp"} <= data[0].keys()


async def test_chat_is_honestly_unavailable_and_stores_nothing(async_client: AsyncClient, project):
    payload = {"message": "Add rate limiting middleware to protected routes", "mode": "agent"}
    res = await async_client.post(f"/api/projects/{project['id']}/chat", json=payload)
    assert res.status_code == 503
    assert res.json()["detail"] == CHAT_UNAVAILABLE_DETAIL
    assert "plan_steps" not in res.json()  # no invented plan or citations

    async with AsyncSessionLocal() as session:
        count = (
            await session.execute(select(func.count()).select_from(Conversation).where(Conversation.project_id == project["id"]))
        ).scalar_one()
    assert count == 0


async def test_chat_and_history_on_unknown_project_are_404(async_client: AsyncClient):
    assert (await async_client.post("/api/projects/does-not-exist/chat", json={"message": "hello"})).status_code == 404
    assert (await async_client.get("/api/projects/does-not-exist/chat/history")).status_code == 404


@pytest.mark.parametrize("body", [{"message": ""}, {"message": "hi", "mode": "bogus"}, {}])
async def test_invalid_chat_requests_are_422(async_client: AsyncClient, project, body):
    res = await async_client.post(f"/api/projects/{project['id']}/chat", json=body)
    assert res.status_code == 422

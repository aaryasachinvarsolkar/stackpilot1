import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

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
    assert {"id", "sender", "content", "citations", "plan_steps", "timestamp", "status", "grounding"} <= data[0].keys()
    # messages stored without a status are legacy: the assistant's is labelled as such, never as verified
    assert [(m["sender"], m["status"], m["grounding"]) for m in data] == [("user", None, None), ("assistant", "legacy", None)]


async def test_chat_sends_message_and_stores_conversation(async_client: AsyncClient, project):
    payload = {"message": "Add rate limiting middleware to protected routes", "mode": "agent"}
    res = await async_client.post(f"/api/projects/{project['id']}/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["sender"] == "assistant"
    assert "content" in data and len(data["content"]) > 0
    assert "plan_steps" in data
    assert "citations" in data
    # with no provider configured (the test default) nothing is answered: the reply says so and is stored as such
    assert data["status"] == "unavailable" and data["plan_steps"] == [] and data["citations"] == []
    assert data["grounding"]["reason"] == "not_sendable"

    async with AsyncSessionLocal() as session:
        count = (
            await session.execute(select(func.count()).select_from(Conversation).where(Conversation.project_id == project["id"]))
        ).scalar_one()
    assert count >= 1

    async with AsyncSessionLocal() as session:
        stored = (await session.execute(select(Message).where(Message.id == data["message_id"]))).scalars().one()
    assert (stored.status, stored.plan_steps, stored.citations) == ("unavailable", [], [])
    assert stored.grounding == data["grounding"]


async def test_history_of_a_conversation_whose_messages_have_no_status_or_grounding_loads(async_client: AsyncClient, project):
    async with AsyncSessionLocal() as session:
        conv = Conversation(id=str(uuid.uuid4()), project_id=project["id"], title="t")
        session.add(conv)
        await session.flush()
        for i, sender in enumerate(["user", "assistant", "user", "assistant"]):
            session.add(
                Message(
                    conversation_id=conv.id, sender=sender, content=f"m{i}", citations=[], plan_steps=[],
                    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i),
                )
            )
        await session.commit()
    res = await async_client.get(f"/api/projects/{project['id']}/chat/history")
    assert res.status_code == 200
    assert [(m["content"], m["status"]) for m in res.json()] == [("m0", None), ("m1", "legacy"), ("m2", None), ("m3", "legacy")]


async def test_a_stored_status_is_returned_as_it_is(async_client: AsyncClient, project):
    async with AsyncSessionLocal() as session:
        conv = Conversation(id=str(uuid.uuid4()), project_id=project["id"], title="t")
        session.add(conv)
        await session.flush()
        session.add(
            Message(
                conversation_id=conv.id, sender="assistant", content="grounded", citations=[], plan_steps=[],
                status="answered_unverified", grounding={"version": 1, "reason": "no_citations"},
            )
        )
        await session.commit()
    (m,) = (await async_client.get(f"/api/projects/{project['id']}/chat/history")).json()
    assert (m["status"], m["grounding"]) == ("answered_unverified", {"version": 1, "reason": "no_citations"})


async def test_chat_and_history_on_unknown_project_are_404(async_client: AsyncClient):
    assert (await async_client.post("/api/projects/does-not-exist/chat", json={"message": "hello"})).status_code == 404
    assert (await async_client.get("/api/projects/does-not-exist/chat/history")).status_code == 404


@pytest.mark.parametrize("body", [{"message": ""}, {"message": "hi", "mode": "bogus"}, {}])
async def test_invalid_chat_requests_are_422(async_client: AsyncClient, project, body):
    res = await async_client.post(f"/api/projects/{project['id']}/chat", json=body)
    assert res.status_code == 422

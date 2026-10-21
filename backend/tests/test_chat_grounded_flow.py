"""The grounded chat end to end through the HTTP API: persistence, history, legacy messages, ownership, ordering.

Providers are fakes (`llm.httpx` is replaced), projects live in the test sandbox, and nothing here can reach a network.
"""
import asyncio
import inspect
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.conversation import Conversation, Message
from app.services import grounding, llm, retrieval

KEY = "sk-proj-AbCdEf0123456789AbCdEf0123456789AbCdEf0123456789"
MARKER = "ZEBRAMARKER"
SOURCE = "".join(f"line {i}\n" for i in range(1, 6)) + f"the {MARKER} is defined here\n" + "".join(f"after {i}\n" for i in range(1, 4))
STATUSES = {"answered_verified", "answered_unverified", "not_in_context", "unavailable"}


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code, self._body = status_code, body if body is not None else {}

    def json(self):
        return self._body


def reply(payload) -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": {"content": json.dumps(payload)}}]})


def structured(answer="an answer", citations=None, answerable=True) -> dict:
    return {"answerable": answerable, "answer": answer, "citations": citations or []}


@pytest.fixture
def provider(monkeypatch):
    state = SimpleNamespace(sent=[], clients=0, events=[], respond=lambda url, body: reply(structured()))

    class FakeClient:
        def __init__(self, **_kwargs):
            state.clients += 1

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def post(self, url, headers=None, json=None):
            state.events.append("provider")
            state.sent.append({"url": url, "headers": headers or {}, "json": json})
            result = state.respond(url, json)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(llm, "httpx", SimpleNamespace(AsyncClient=FakeClient))
    return state


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    for name in ("OPENAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "LLM_API_KEY", KEY)
    monkeypatch.setattr(settings, "LLM_MODEL", "test-model")
    monkeypatch.setattr(settings, "ALLOW_SENDING_CODE_TO_PROVIDER", True)


@pytest.fixture
def planted(project) -> Path:
    root = Path(project["root_path"])
    (root / "lib").mkdir(exist_ok=True)
    (root / "lib" / "zebra_service.py").write_text(SOURCE, encoding="utf-8")
    return root


async def ask(client: AsyncClient, project: dict, message: str = f"where is {MARKER} defined?", **extra):
    return await client.post(f"/api/projects/{project['id']}/chat", json={"message": message, **extra})


def excerpt_id(provider, n=0, path="lib/zebra_service.py") -> str:
    return re.search(rf"id=(E\d+) path={re.escape(path)}", provider.sent[n]["json"]["messages"][1]["content"]).group(1)


def valid_citation(provider, start=6, end=6, n=0) -> dict:
    return {"excerpt_id": excerpt_id(provider, n), "line_start": start, "line_end": end}


async def rows(conversation_id: str):
    async with AsyncSessionLocal() as session:
        return (await session.execute(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc()))).scalars().all()


# ---------------------------------------------------------------------------------------------------------------
# a verified answer, end to end
# ---------------------------------------------------------------------------------------------------------------

async def test_a_verified_answer_is_returned_and_stored_with_its_checked_citations(async_client, project, planted, provider):
    provider.respond = lambda url, body: reply(structured("It is defined on line 6.", [valid_citation(provider)]))
    res = await ask(async_client, project)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "answered_verified" and body["content"] == "It is defined on line 6."
    assert body["plan_steps"] == []
    [citation] = body["citations"]
    assert (citation["file_path"], citation["line_start"], citation["line_end"], citation["status"]) == ("lib/zebra_service.py", 6, 6, "verified")
    assert re.fullmatch(r"E\d+", citation["excerpt_id"]) and len(citation["file_sha256"]) == 64 and len(citation["range_sha256"]) == 64

    assistant = (await rows(body["conversation_id"]))[-1]
    assert assistant.id == body["message_id"] and assistant.sender == "assistant"
    assert assistant.status == "answered_verified" and assistant.plan_steps == []
    assert assistant.grounding == body["grounding"] and assistant.grounding["reason"] == "all_citations_verified"
    assert assistant.citations[0]["status"] == "verified" and assistant.citations[0]["file_path"] == "lib/zebra_service.py"


async def test_nothing_that_is_source_code_is_stored_in_the_grounding_or_citation_columns(async_client, project, planted, provider):
    (planted / "lib" / "zebra_service.py").write_text(SOURCE + 'DB_PASSWORD = "Sup3rS3cretPassw0rd"\n', encoding="utf-8")
    provider.respond = lambda url, body: reply(structured("see the cited line", [valid_citation(provider)]))
    body = (await ask(async_client, project, f"where is {MARKER} defined, and the password?")).json()
    assistant = (await rows(body["conversation_id"]))[-1]
    stored = json.dumps({"grounding": assistant.grounding, "citations": assistant.citations, "plan_steps": assistant.plan_steps})
    for text in (f"the {MARKER} is defined here", "after 1", "line 1", "Sup3rS3cretPassw0rd", "DB_PASSWORD", "[REDACTED]", KEY):
        assert text not in stored, f"{text!r} was stored with the message"
    assert set(assistant.grounding["retrieval"]) == {"excerpts", "chars", "files", "redactions", "scan_truncated"}


async def test_the_user_message_is_stored_without_status_or_grounding(async_client, project, planted, provider):
    body = (await ask(async_client, project)).json()
    user, assistant = (await rows(body["conversation_id"]))[-2:]
    assert (user.sender, user.status, user.grounding, user.citations, user.plan_steps) == ("user", None, None, [], [])
    assert assistant.sender == "assistant"


# ---------------------------------------------------------------------------------------------------------------
# every status, and what is listed
# ---------------------------------------------------------------------------------------------------------------

async def test_an_answer_without_citations_is_unverified(async_client, project, planted, provider):
    body = (await ask(async_client, project)).json()
    assert body["status"] == "answered_unverified" and body["citations"] == []
    assert body["grounding"]["reason"] == "no_citations"


async def test_invalid_citations_are_not_listed_but_are_counted_in_the_metadata(async_client, project, planted, provider):
    provider.respond = lambda url, body: reply(structured("x", [valid_citation(provider), {"excerpt_id": "E77", "file_path": "../../etc/passwd", "line_start": 1, "line_end": 2}]))
    body = (await ask(async_client, project)).json()
    assert body["status"] == "answered_unverified"
    assert [c["status"] for c in body["citations"]] == ["verified"]
    assert [c["status"] for c in body["grounding"]["citations"]] == ["verified", "invalid"]
    assert "etc/passwd" not in json.dumps(body), "model-supplied path text is never echoed"


async def test_a_stale_citation_is_listed_as_stale(async_client, project, planted, provider):
    def edit_then_reply(url, body):
        (planted / "lib" / "zebra_service.py").write_text(SOURCE.replace(f"the {MARKER} is defined here", "rewritten"), encoding="utf-8")
        return reply(structured("x", [valid_citation(provider)]))

    provider.respond = edit_then_reply
    body = (await ask(async_client, project)).json()
    assert body["status"] == "answered_unverified" and [c["status"] for c in body["citations"]] == ["stale"]


async def test_a_question_with_nothing_relevant_is_not_in_context_and_stored_as_such(async_client, project, planted, provider):
    res = await ask(async_client, project, "kubernetes helm chart rollout strategy")
    body = res.json()
    assert body["status"] == "not_in_context" and body["content"] == grounding.NOT_IN_CONTEXT_TEXT and body["citations"] == []
    assert provider.sent == [] and provider.clients == 0, "the provider is not called when nothing was found"
    assert (await rows(body["conversation_id"]))[-1].status == "not_in_context"


async def test_consent_off_is_unavailable_and_stored_as_such(async_client, project, planted, provider, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_SENDING_CODE_TO_PROVIDER", False)
    body = (await ask(async_client, project)).json()
    assert body["status"] == "unavailable" and "turned off" in body["content"]
    assert provider.sent == [] and provider.clients == 0
    assistant = (await rows(body["conversation_id"]))[-1]
    assert assistant.status == "unavailable" and assistant.grounding["reason"] == "not_sendable"


@pytest.mark.parametrize("respond", [
    lambda u, b: FakeResponse(500),
    lambda u, b: ConnectionError("sk-LEAK https://api.openai.com"),
    lambda u, b: reply({"content": "old format"}),
    lambda u, b: reply(structured("")),
])
async def test_provider_failures_are_unavailable_and_nothing_raw_is_returned_or_stored(async_client, project, planted, provider, respond):
    provider.respond = respond
    body = (await ask(async_client, project)).json()
    assert body["status"] == "unavailable" and body["citations"] == [] and body["plan_steps"] == []
    blob = json.dumps(body) + json.dumps((await rows(body["conversation_id"]))[-1].grounding)
    for raw in ("sk-LEAK", "api.openai.com", "old format", KEY):
        assert raw not in blob


async def test_every_response_has_a_known_status_and_the_agreed_shape(async_client, project, planted, provider):
    for message in (f"where is {MARKER}", "kubernetes helm", "?!"):
        body = (await ask(async_client, project, message)).json()
        assert body["status"] in STATUSES
        assert set(body) == {"conversation_id", "message_id", "sender", "content", "citations", "plan_steps", "timestamp", "status", "grounding"}
        assert body["sender"] == "assistant"


# ---------------------------------------------------------------------------------------------------------------
# ordering and statelessness through the API
# ---------------------------------------------------------------------------------------------------------------

async def test_retrieval_runs_before_the_provider_through_the_api(async_client, project, planted, provider, monkeypatch):
    real = retrieval.retrieve

    def logged(*args, **kwargs):
        provider.events.append("retrieve")
        return real(*args, **kwargs)

    monkeypatch.setattr(grounding.retrieval, "retrieve", logged)
    await ask(async_client, project)
    assert provider.events == ["retrieve", "provider"]


async def test_without_consent_retrieval_is_never_reached(async_client, project, planted, provider, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("retrieval must not run without consent")

    monkeypatch.setattr(grounding.retrieval, "retrieve", explode)
    monkeypatch.setattr(settings, "ALLOW_SENDING_CODE_TO_PROVIDER", False)
    res = await ask(async_client, project)
    assert res.status_code == 200 and res.json()["status"] == "unavailable"
    monkeypatch.setattr(settings, "ALLOW_SENDING_CODE_TO_PROVIDER", True)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "mock")
    res = await ask(async_client, project)
    assert res.status_code == 200 and res.json()["status"] == "unavailable" and provider.sent == []


async def test_earlier_messages_are_stored_but_never_sent(async_client, project, planted, provider):
    provider.respond = lambda url, body: reply(structured("FIRST-ANSWER-1111"))
    first = (await ask(async_client, project, f"FIRST-QUESTION-2222 {MARKER}")).json()
    await ask(async_client, project, f"SECOND-QUESTION-3333 {MARKER}", conversation_id=first["conversation_id"])
    assert len(await rows(first["conversation_id"])) == 4, "both exchanges are persisted"
    second = json.dumps(provider.sent[1]["json"])
    assert "SECOND-QUESTION-3333" in second and "FIRST-QUESTION-2222" not in second and "FIRST-ANSWER-1111" not in second


async def test_no_database_write_is_held_open_while_the_provider_is_awaited(async_client, project, planted, provider):
    """A brand new conversation used to be written (flushed) BEFORE the provider call, holding SQLite's write lock for up to a
    minute. Another writer must now be able to commit while the provider is still thinking."""
    other = (await async_client.post("/api/projects", json={"name": f"w-{uuid.uuid4().hex[:10]}", "source_type": "blank"})).json()
    outcome = {}

    async def concurrent_write_then_reply():
        async with AsyncSessionLocal() as session:
            session.add(Conversation(id=str(uuid.uuid4()), project_id=other["id"], title="written while waiting"))
            try:
                await asyncio.wait_for(session.commit(), timeout=2.0)
                outcome["committed"] = True
            except asyncio.TimeoutError:
                outcome["committed"] = False
        return reply(structured())

    provider.respond = lambda url, body: concurrent_write_then_reply()
    res = await ask(async_client, project)
    assert res.status_code == 200
    assert outcome == {"committed": True}, "the database was locked by the request while it waited for the provider"


# ---------------------------------------------------------------------------------------------------------------
# history and legacy messages
# ---------------------------------------------------------------------------------------------------------------

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


async def insert_legacy_conversation(project_id: str) -> str:
    """Messages exactly as written before grounding existed: NULL status and NULL grounding."""
    async with AsyncSessionLocal() as session:
        conv = Conversation(id=str(uuid.uuid4()), project_id=project_id, title="old", created_at=T0)
        session.add(conv)
        await session.flush()
        session.add_all([
            Message(conversation_id=conv.id, sender="user", content="old question", citations=[], plan_steps=[], created_at=T0),
            Message(
                conversation_id=conv.id, sender="assistant", content="old canned answer",
                citations=[{"file_path": "app/main.py", "line_start": 1, "line_end": 4, "symbol": None}],
                plan_steps=[{"id": 1, "text": "Add rate limiting", "tool": "modify_file", "status": "pending"}],
                created_at=T0 + timedelta(seconds=1),
            ),
        ])
        await session.commit()
        return conv.id


async def test_old_messages_are_reported_as_legacy_and_never_as_verified(async_client, project):
    await insert_legacy_conversation(project["id"])
    data = (await async_client.get(f"/api/projects/{project['id']}/chat/history")).json()
    assert [(m["sender"], m["status"], m["grounding"]) for m in data] == [("user", None, None), ("assistant", "legacy", None)]
    legacy = data[1]
    assert legacy["content"] == "old canned answer"
    assert legacy["citations"] == [{"file_path": "app/main.py", "line_start": 1, "line_end": 4, "symbol": None}], "stored citations are returned as they were"
    assert "status" not in legacy["citations"][0], "no verification is invented for a legacy citation"
    assert legacy["plan_steps"][0]["text"] == "Add rate limiting", "stored plan steps stay readable"
    assert {"id", "sender", "content", "citations", "plan_steps", "timestamp", "status", "grounding"} <= set(legacy)


async def test_new_and_legacy_messages_mix_in_one_history_in_order(async_client, project, planted, provider):
    conv_id = await insert_legacy_conversation(project["id"])
    provider.respond = lambda url, body: reply(structured("new answer", [valid_citation(provider)]))
    new = (await ask(async_client, project, conversation_id=conv_id)).json()
    data = (await async_client.get(f"/api/projects/{project['id']}/chat/history")).json()
    assert [m["content"] for m in data][:2] == ["old question", "old canned answer"]
    assert [m["status"] for m in data] == [None, "legacy", None, "answered_verified"]
    assert data[-1]["id"] == new["message_id"] and data[-1]["grounding"]["reason"] == "all_citations_verified"
    assert data[-1]["citations"][0]["status"] == "verified"


async def test_history_returns_the_stored_grounding_metadata(async_client, project, planted, provider):
    provider.respond = lambda url, body: reply(structured("x", [valid_citation(provider)]))
    body = (await ask(async_client, project)).json()
    data = (await async_client.get(f"/api/projects/{project['id']}/chat/history")).json()
    assert data[-1]["status"] == "answered_verified" and data[-1]["grounding"] == body["grounding"]


async def test_clearing_the_history_removes_grounded_and_legacy_messages(async_client, project, planted, provider):
    await insert_legacy_conversation(project["id"])
    await ask(async_client, project)
    assert (await async_client.delete(f"/api/projects/{project['id']}/chat/history")).status_code == 204
    assert (await async_client.get(f"/api/projects/{project['id']}/chat/history")).json() == []


# ---------------------------------------------------------------------------------------------------------------
# conversation ownership
# ---------------------------------------------------------------------------------------------------------------

async def other_project(client: AsyncClient) -> dict:
    res = await client.post("/api/projects", json={"name": f"o-{uuid.uuid4().hex[:10]}", "source_type": "blank"})
    assert res.status_code == 201, res.text
    return res.json()


async def test_a_conversation_of_another_project_is_a_404_that_reads_nothing_sends_nothing_and_leaks_nothing(async_client, project, planted, provider, monkeypatch):
    other = await other_project(async_client)
    foreign = await insert_legacy_conversation(other["id"])
    before = [m.id for m in await rows(foreign)]

    def explode(*args, **kwargs):
        raise AssertionError("no work may be done for a conversation that is not this project's")

    monkeypatch.setattr(grounding.retrieval, "retrieve", explode)
    res = await ask(async_client, project, conversation_id=foreign)

    assert res.status_code == 404 and res.json() == {"detail": "Conversation not found in this project."}
    assert "old canned answer" not in res.text and "old question" not in res.text
    assert provider.sent == [] and provider.clients == 0
    assert [m.id for m in await rows(foreign)] == before, "nothing may be written into the other project's conversation"


async def test_an_unknown_conversation_id_is_a_404_and_does_not_fall_back_to_another_conversation(async_client, project, planted, provider):
    mine = await insert_legacy_conversation(project["id"])
    res = await ask(async_client, project, conversation_id=str(uuid.uuid4()))
    assert res.status_code == 404 and provider.sent == []
    assert len(await rows(mine)) == 2


async def test_without_an_id_the_projects_own_latest_conversation_is_used_never_another_projects(async_client, project, planted, provider):
    other = await other_project(async_client)
    foreign = await insert_legacy_conversation(other["id"])
    body = (await ask(async_client, project)).json()
    assert body["conversation_id"] != foreign
    assert len(await rows(foreign)) == 2


async def test_the_projects_own_conversation_id_works(async_client, project, planted, provider):
    first = (await ask(async_client, project)).json()
    second = await ask(async_client, project, conversation_id=first["conversation_id"])
    assert second.status_code == 200 and second.json()["conversation_id"] == first["conversation_id"]


# ---------------------------------------------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------------------------------------------

async def test_unknown_projects_and_invalid_bodies_are_still_rejected(async_client, project):
    assert (await async_client.post("/api/projects/does-not-exist/chat", json={"message": "hi"})).status_code == 404
    for body in ({"message": ""}, {"message": "hi", "mode": "bogus"}, {}):
        assert (await async_client.post(f"/api/projects/{project['id']}/chat", json=body)).status_code == 422


async def test_nothing_sensitive_is_logged_by_the_api_path(async_client, project, planted, provider, caplog):
    provider.respond = lambda url, body: reply(structured("ANSWER-TEXT-9921", [valid_citation(provider)]))
    with caplog.at_level("DEBUG"):
        await ask(async_client, project, f"QUESTION-TEXT-7731 {MARKER}")
    for private in (KEY, "QUESTION-TEXT-7731", "ANSWER-TEXT-9921", f"the {MARKER} is defined here"):
        assert private not in caplog.text, f"{private!r} was logged"

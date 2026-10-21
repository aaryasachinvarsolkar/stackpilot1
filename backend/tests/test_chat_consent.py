"""Consent (ALLOW_SENDING_CODE_TO_PROVIDER) and what the chat may send, read or log.

The provider's HTTP client is replaced by a recorder and every filesystem entry point that could read a project is
watched, so each test can state exactly what left the machine (nothing, unless consent is on) and what was read (nothing).
No test here can reach the network: there is no real HTTP client in the chat path while these fakes are installed.
"""
import builtins
import json
import os
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.config import Settings, settings
from app.services import llm

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "backend" / "app"
CODE_QUESTION = "Why does def secret_algorithm(): return 42 in app/main.py print TOP-SECRET-MARKER-7781?"
PROVIDER_KEYS = [
    ("openai", "sk-proj-AbCdEf0123456789AbCdEf0123456789AbCdEf0123456789"),
    ("groq", "gsk_AbCdEf0123456789AbCdEf0123456789AbCdEf012345"),
    ("gemini", "AIzaSyAbCdEf0123456789-AbCdEf0123456789"),
]


# ---------------------------------------------------------------------------------------------------------------
# fakes and spies
# ---------------------------------------------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


def structured(answer="a general answer", citations=None, answerable=True) -> dict:
    return {"answerable": answerable, "answer": answer, "citations": citations or []}


def openai_reply(content="a general answer") -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": {"content": json.dumps(structured(content))}}]})


def gemini_reply(content="a general answer") -> FakeResponse:
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(structured(content))}]}}]})


@pytest.fixture
def outbound(monkeypatch):
    """Replaces httpx inside the chat path. Counts requests AND the creation of any client."""
    state = SimpleNamespace(sent=[], clients=0, respond=lambda url: openai_reply())

    class FakeClient:
        def __init__(self, **_kwargs):
            state.clients += 1

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def post(self, url, headers=None, json=None):
            state.sent.append({"url": url, "headers": headers or {}, "json": json})
            return state.respond(url)

    monkeypatch.setattr(llm, "httpx", SimpleNamespace(AsyncClient=FakeClient))
    return state


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ["OPENAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "ALLOW_SENDING_CODE_TO_PROVIDER"]:
        monkeypatch.delenv(name, raising=False)


def configure(monkeypatch, provider: str, key: str, consent, model: str = "test-model"):
    monkeypatch.setattr(settings, "LLM_PROVIDER", provider)
    monkeypatch.setattr(settings, "LLM_API_KEY", key)
    monkeypatch.setattr(settings, "LLM_MODEL", model)
    monkeypatch.setattr(settings, "ALLOW_SENDING_CODE_TO_PROVIDER", consent)


@pytest.fixture
def file_access(monkeypatch, project):
    """Fails the test the moment anything opens, lists or walks the project's folder. `touched` lists any attempts."""
    root = os.path.normcase(os.path.abspath(project["root_path"]))
    touched: list[str] = []

    def inside(path) -> bool:
        try:
            candidate = os.path.normcase(os.path.abspath(os.fspath(path)))
        except TypeError:  # a file descriptor
            return False
        return candidate == root or candidate.startswith(root + os.sep)

    def guard_function(real, name):
        def wrapper(path=".", *args, **kwargs):
            if inside(path):
                touched.append(name)
                raise AssertionError(f"{name}() touched the project folder: {path}")
            return real(path, *args, **kwargs)

        return wrapper

    def guard_method(real, name):
        def wrapper(self, *args, **kwargs):
            if inside(self):
                touched.append(name)
                raise AssertionError(f"Path.{name}() touched the project folder: {self}")
            return real(self, *args, **kwargs)

        return wrapper

    for owner, attr in [(os, "walk"), (os, "scandir"), (os, "listdir"), (builtins, "open")]:
        monkeypatch.setattr(owner, attr, guard_function(getattr(owner, attr), f"{owner.__name__}.{attr}"))
    for attr in ["open", "read_text", "read_bytes", "iterdir", "glob", "rglob"]:
        monkeypatch.setattr(Path, attr, guard_method(getattr(Path, attr), attr))
    return SimpleNamespace(root=project["root_path"], touched=touched)


async def ask(client: AsyncClient, project: dict, message: str = CODE_QUESTION, mode: str = "agent", **extra):
    return await client.post(f"/api/projects/{project['id']}/chat", json={"message": message, "mode": mode, **extra})


# ---------------------------------------------------------------------------------------------------------------
# the setting itself
# ---------------------------------------------------------------------------------------------------------------

def test_consent_is_off_by_default():
    assert Settings(_env_file=None).ALLOW_SENDING_CODE_TO_PROVIDER is False


@pytest.mark.parametrize("value,expected", [("true", True), ("True", True), ("1", True), ("false", False), ("0", False), ("no", False)])
def test_consent_can_be_set_from_the_environment_only(monkeypatch, value, expected):
    monkeypatch.setenv("ALLOW_SENDING_CODE_TO_PROVIDER", value)
    assert Settings(_env_file=None).ALLOW_SENDING_CODE_TO_PROVIDER is expected


def test_a_garbage_value_does_not_silently_turn_consent_on(monkeypatch):
    monkeypatch.setenv("ALLOW_SENDING_CODE_TO_PROVIDER", "maybe")
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_env_example_documents_the_switch_as_off():
    text = (REPO / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^ALLOW_SENDING_CODE_TO_PROVIDER=false$", text, re.M)


def test_no_api_route_can_change_the_setting():
    """There is no endpoint, request field or database column through which a client could turn consent on."""
    for path in (APP / "api").glob("*.py"):
        assert "ALLOW_SENDING_CODE_TO_PROVIDER" not in path.read_text(encoding="utf-8"), path.name
    assert "ALLOW_SENDING_CODE_TO_PROVIDER" not in (APP / "models" / "conversation.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------------------------------------------
# consent OFF: zero outbound requests, whatever else is configured
# ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("provider,key", PROVIDER_KEYS)
@pytest.mark.parametrize("mode", ["agent", "chat", "review"])
async def test_consent_off_sends_nothing_even_with_a_realistic_key(async_client, project, monkeypatch, outbound, file_access, provider, key, mode):
    configure(monkeypatch, provider, key, consent=False)

    res = await ask(async_client, project, mode=mode)

    assert res.status_code == 200, res.text
    reply = res.json()
    assert outbound.sent == [], "a request was sent to a provider while consent was off"
    assert outbound.clients == 0, "an HTTP client was even created while consent was off"
    assert file_access.touched == []
    assert reply["content"] == llm.consent_problem()
    assert reply["plan_steps"] == [] and reply["citations"] == []


@pytest.mark.parametrize("provider,key", PROVIDER_KEYS)
async def test_consent_off_message_is_clear_and_does_not_mislead(async_client, project, monkeypatch, outbound, provider, key):
    configure(monkeypatch, provider, key, consent=False)
    content = (await ask(async_client, project)).json()["content"]
    assert "turned off" in content
    assert "ALLOW_SENDING_CODE_TO_PROVIDER" in content
    assert "nothing was sent anywhere" in content and "files were not read" in content
    assert f"'{provider}'" in content
    for misleading in ("analysed your", "I scanned", "I analyzed", "Based on your code", "indexed"):
        assert misleading not in content
    assert key not in content and "TOP-SECRET-MARKER" not in content, "the key or the question must not be echoed back"


@pytest.mark.parametrize("not_true", ["true", "yes", "1", 1, "True", None, 0, ""])
async def test_only_the_boolean_true_turns_consent_on(async_client, project, monkeypatch, outbound, not_true):
    configure(monkeypatch, "openai", PROVIDER_KEYS[0][1], consent=not_true)
    reply = (await ask(async_client, project)).json()
    assert outbound.sent == [] and outbound.clients == 0
    assert "turned off" in reply["content"]


async def test_consent_off_blocks_the_lowest_layer_too(monkeypatch, outbound):
    """A future caller that skips answer_query still cannot reach the network."""
    configure(monkeypatch, "openai", PROVIDER_KEYS[0][1], consent=False)
    with pytest.raises(llm.ConsentError):
        await llm.call_external_llm(system="rules", user=CODE_QUESTION)
    assert outbound.sent == [] and outbound.clients == 0


async def test_unconfigured_provider_cannot_be_reached_at_the_lowest_layer_either(monkeypatch, outbound):
    configure(monkeypatch, "mock", "mock-key", consent=True)
    with pytest.raises(llm.LLMCallError):
        await llm.call_external_llm(system="rules", user=CODE_QUESTION)
    assert outbound.sent == [] and outbound.clients == 0


async def test_consent_off_leaves_no_trace_of_the_question_in_the_logs(async_client, project, monkeypatch, outbound, caplog):
    key = PROVIDER_KEYS[0][1]
    configure(monkeypatch, "openai", key, consent=False)
    with caplog.at_level("DEBUG"):
        await ask(async_client, project)
    assert "TOP-SECRET-MARKER" not in caplog.text and "secret_algorithm" not in caplog.text
    assert key not in caplog.text
    assert "turned off" not in caplog.text, "the stored reply was printed to the log"


async def test_questions_and_answers_are_not_logged_even_when_a_question_is_sent_and_logging_is_at_debug(
    async_client, project, monkeypatch, outbound, caplog
):
    """DEBUG is the development default. Database drivers log statements with their parameters at that level."""
    key = PROVIDER_KEYS[0][1]
    configure(monkeypatch, "openai", key, consent=True)
    outbound.respond = lambda url: openai_reply("ANSWER-MARKER-9921 about secret_algorithm")
    with caplog.at_level("DEBUG"):
        reply = (await ask(async_client, project)).json()
    assert "ANSWER-MARKER-9921" in reply["content"]
    for private in ("TOP-SECRET-MARKER", "secret_algorithm", "ANSWER-MARKER-9921", key):
        assert private not in caplog.text, f"{private!r} was written to the log"


# ---------------------------------------------------------------------------------------------------------------
# consent ON but the provider is not usable: still nothing is sent, and the reason says so
# ---------------------------------------------------------------------------------------------------------------

async def test_consent_on_without_a_provider_is_unavailable_and_sends_nothing(async_client, project, monkeypatch, outbound, file_access):
    configure(monkeypatch, "mock", "mock-key", consent=True)
    reply = (await ask(async_client, project)).json()
    assert outbound.sent == [] and outbound.clients == 0 and file_access.touched == []
    assert reply["content"] == llm.llm_config_problem()
    assert "no model is connected" in reply["content"]


@pytest.mark.parametrize("provider", ["anthropic", "acme-ai"])
async def test_consent_on_with_an_unsupported_provider_is_unavailable(async_client, project, monkeypatch, outbound, provider):
    configure(monkeypatch, provider, "sk-realistic-looking-key", consent=True)
    reply = (await ask(async_client, project)).json()
    assert outbound.sent == [] and outbound.clients == 0
    assert "not supported" in reply["content"] and provider in reply["content"]


@pytest.mark.parametrize("placeholder", ["", "   ", "mock-key", "your-llm-api-key-here"])
async def test_consent_on_with_a_placeholder_key_is_unavailable(async_client, project, monkeypatch, outbound, placeholder):
    configure(monkeypatch, "openai", placeholder, consent=True)
    reply = (await ask(async_client, project)).json()
    assert outbound.sent == [] and outbound.clients == 0
    assert "LLM_API_KEY" in reply["content"]


# ---------------------------------------------------------------------------------------------------------------
# consent ON and a provider configured: what is sent is exactly the question (no files, no history, no paths)
# ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("provider,key", PROVIDER_KEYS)
async def test_consent_on_sends_exactly_one_request_to_the_providers_own_host(async_client, project, monkeypatch, outbound, provider, key):
    configure(monkeypatch, provider, key, consent=True)
    outbound.respond = (lambda url: gemini_reply()) if provider == "gemini" else (lambda url: openai_reply())
    res = await ask(async_client, project)
    assert res.status_code == 200
    assert len(outbound.sent) == 1 and outbound.clients == 1
    body = res.json()
    assert body["content"] == "a general answer" and body["status"] == "answered_unverified"


def plant(project: dict) -> Path:
    """Files inside the (sandbox) project: two ordinary ones, and files that must never be sent."""
    root = Path(project["root_path"])
    (root / "lib").mkdir(exist_ok=True)
    (root / "lib" / "zebra_service.py").write_text("def zebra_total():\n    return 'ZEBRA-BODY-1111'\n", encoding="utf-8")
    (root / "lib" / "other_service.py").write_text("def gizmo():\n    return 'OTHER-BODY-2222'\n", encoding="utf-8")
    (root / ".env").write_text("API_SECRET_VALUE=ENV-SECRET-3333\nzebra_total=1\n", encoding="utf-8")
    (root / "secrets.json").write_text('{"zebra_total": "SECRETS-FILE-4444"}', encoding="utf-8")
    (root / "lib" / "settings.py").write_text('# zebra_total settings\nDB_PASSWORD = "Sup3rS3cretPassw0rd"\n', encoding="utf-8")
    return root


@pytest.mark.parametrize("provider,key", PROVIDER_KEYS)
async def test_what_is_sent_is_the_question_and_only_the_retrieved_excerpts(async_client, project, sandbox, monkeypatch, outbound, provider, key):
    plant(project)
    configure(monkeypatch, provider, key, consent=True)
    outbound.respond = (lambda url: gemini_reply()) if provider == "gemini" else (lambda url: openai_reply())
    await ask(async_client, project, "FIRST-QUESTION-1111 where is zebra_total")
    await ask(async_client, project, "SECOND-QUESTION-2222 where is zebra_total")
    assert len(outbound.sent) == 2

    second = json.dumps(outbound.sent[1]["json"])
    assert "SECOND-QUESTION-2222" in second and "ZEBRA-BODY-1111" in second, "the question and the matching excerpt are sent"
    assert "FIRST-QUESTION-1111" not in second, "an earlier question was replayed to the provider (history must not be sent)"
    assert "a general answer" not in second, "an earlier answer was replayed to the provider"
    for never in ("OTHER-BODY-2222", "ENV-SECRET-3333", "API_SECRET_VALUE", "SECRETS-FILE-4444", "Sup3rS3cretPassw0rd", "requirements.txt"):
        assert never not in second, f"{never!r} must never reach the provider"
    assert project["root_path"].replace("\\", "\\\\") not in second and str(sandbox).replace("\\", "\\\\") not in second, "a local path was sent"
    if provider != "gemini":
        messages = outbound.sent[1]["json"]["messages"]
        assert [m["role"] for m in messages] == ["system", "user"]
        assert "1| def zebra_total():" in messages[1]["content"], "excerpt lines are numbered so citations can name them"
        assert "SECOND-QUESTION-2222" in messages[1]["content"] and "SECOND-QUESTION-2222" not in messages[0]["content"]


async def test_the_project_is_never_uploaded_as_a_whole(async_client, project, monkeypatch, outbound):
    root = plant(project)
    for i in range(60):
        (root / "lib" / f"bulk_{i:02d}.py").write_text(f"def bulk_{i}():\n    return 'BULK-{i:02d}-BODY' + 'x' * 200\n", encoding="utf-8")
    for i in range(150):  # a word found in over half of all files is ignored as non-discriminating, so give it company
        (root / "lib" / f"plain_{i:03d}.txt").write_text(f"plain filler number {i}\n", encoding="utf-8")
    configure(monkeypatch, "openai", PROVIDER_KEYS[0][1], consent=True)
    await ask(async_client, project, "explain bulk functions")
    sent = json.dumps(outbound.sent[0]["json"])
    assert outbound.sent[0]["json"]["messages"][1]["content"].count("<<<EXCERPT") <= 8, "at most 8 excerpts"
    assert len(outbound.sent[0]["json"]["messages"][1]["content"]) < 24_000 + 4_000, "the excerpt text is bounded"
    assert sum(f"BULK-{i:02d}-BODY" in sent for i in range(60)) <= 8


async def test_the_instructions_sent_to_the_model_forbid_following_file_text_and_offer_no_edit_tools(async_client, project, monkeypatch, outbound):
    plant(project)
    configure(monkeypatch, "openai", PROVIDER_KEYS[0][1], consent=True)
    await ask(async_client, project, "where is zebra_total")
    system = outbound.sent[0]["json"]["messages"][0]["content"]
    for tool in ("modify_file", "create_file", "run_tests", "run_linter", "plan_steps"):
        assert tool not in system
    assert "ONLY the excerpts" in system and "untrusted" in system and "answerable" in system
    nonce = re.search(r"<<<EXCERPT ([0-9a-f]{16}) ", outbound.sent[0]["json"]["messages"][1]["content"]).group(1)
    assert f"contain the code {nonce}" in system, "only delimiters carrying this request's random code are real"
    everything = json.dumps(outbound.sent[0]["json"])
    assert not re.search(r"(?<![A-Za-z])[A-Za-z]:[\\/]|\\\\\\\\|/Users/|/home/|/tmp/|stackpilot-tests", everything), "a local path was sent"


async def test_the_api_key_only_ever_appears_in_the_auth_header(async_client, project, monkeypatch, outbound, caplog):
    key = PROVIDER_KEYS[0][1]
    configure(monkeypatch, "openai", key, consent=True)
    reply = (await ask(async_client, project)).json()
    request = outbound.sent[0]
    assert request["headers"]["Authorization"] == f"Bearer {key}"
    assert key not in request["url"] and key not in json.dumps(request["json"])
    assert key not in reply["content"] and key not in caplog.text


# ---------------------------------------------------------------------------------------------------------------
# socket level: with the REAL http client in place, consent off causes no DNS lookup and no connection at all
# ---------------------------------------------------------------------------------------------------------------

@pytest.fixture
def socket_spy(monkeypatch):
    """Records, and refuses, every DNS lookup and every non-loopback connection. Nothing can leave the machine."""
    import socket

    attempts: list[tuple[str, str]] = []
    real_connect = socket.socket.connect

    def refuse_lookup(host, *args, **kwargs):
        attempts.append(("dns", host.decode() if isinstance(host, bytes) else str(host)))
        raise OSError("blocked by the test")

    def refuse_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        if host not in ("127.0.0.1", "::1", "localhost"):
            attempts.append(("connect", str(host)))
            raise OSError("blocked by the test")
        return real_connect(self, address, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", refuse_lookup)
    monkeypatch.setattr(socket.socket, "connect", refuse_connect)
    return SimpleNamespace(attempts=attempts)


@pytest.mark.parametrize("provider,key", PROVIDER_KEYS)
async def test_consent_off_causes_no_dns_lookup_and_no_connection_with_the_real_http_client(async_client, project, monkeypatch, socket_spy, provider, key):
    assert llm.httpx.__name__ == "httpx", "this test must run against the real http client"
    configure(monkeypatch, provider, key, consent=False)
    reply = (await ask(async_client, project)).json()
    assert socket_spy.attempts == [], f"network activity with consent off: {socket_spy.attempts}"
    assert "turned off" in reply["content"]


async def test_the_socket_spy_does_see_an_attempt_when_consent_is_on(async_client, project, monkeypatch, socket_spy):
    """Control: proves the instrument above is not blind. The attempt is refused by the spy, so nothing is sent."""
    configure(monkeypatch, "openai", PROVIDER_KEYS[0][1], consent=True)
    reply = (await ask(async_client, project)).json()
    assert ("dns", "api.openai.com") in socket_spy.attempts
    assert "openai request failed" in reply["content"]
    assert PROVIDER_KEYS[0][1] not in reply["content"]


# ---------------------------------------------------------------------------------------------------------------
# the file-access spy is not vacuous
# ---------------------------------------------------------------------------------------------------------------

def test_the_file_access_spy_really_catches_reads_of_the_project(file_access):
    with pytest.raises(AssertionError):
        list(os.walk(file_access.root))
    with pytest.raises(AssertionError):
        os.listdir(file_access.root)
    with pytest.raises(AssertionError):
        open(os.path.join(file_access.root, "app", "main.py"))
    with pytest.raises(AssertionError):
        (Path(file_access.root) / "app" / "main.py").read_text()
    assert len(file_access.touched) == 4


# ---------------------------------------------------------------------------------------------------------------
# status endpoint
# ---------------------------------------------------------------------------------------------------------------

async def status_of(client: AsyncClient, project: dict):
    res = await client.get(f"/api/projects/{project['id']}/chat/status")
    assert res.status_code == 200, res.text
    return res.json()


async def test_status_without_a_provider(async_client, project, monkeypatch, outbound, file_access):
    configure(monkeypatch, "mock", "mock-key", consent=False)
    data = await status_of(async_client, project)
    assert data == {"provider": "mock", "model": None, "configured": False, "consent": False, "can_send": False, "reason": llm.llm_config_problem()}
    assert outbound.sent == [] and outbound.clients == 0 and file_access.touched == []


async def test_status_with_a_provider_but_no_consent(async_client, project, monkeypatch, outbound):
    key = PROVIDER_KEYS[0][1]
    configure(monkeypatch, "openai", key, consent=False, model="gpt-test")
    data = await status_of(async_client, project)
    assert data["provider"] == "openai" and data["model"] == "gpt-test"
    assert data["configured"] is True and data["consent"] is False and data["can_send"] is False
    assert "turned off" in data["reason"]
    assert key not in json.dumps(data)
    assert outbound.sent == [] and outbound.clients == 0


async def test_status_ready_to_send(async_client, project, monkeypatch, outbound):
    configure(monkeypatch, "groq", PROVIDER_KEYS[1][1], consent=True)
    data = await status_of(async_client, project)
    assert data["can_send"] is True and data["reason"] is None and data["consent"] is True
    assert outbound.sent == [], "asking for the status must never send anything"


@pytest.mark.parametrize("provider,key", PROVIDER_KEYS)
async def test_status_never_contains_a_key(async_client, project, monkeypatch, provider, key):
    for consent in (False, True):
        configure(monkeypatch, provider, key, consent=consent)
        assert key not in json.dumps(await status_of(async_client, project))


async def test_status_of_an_unknown_project_is_404(async_client):
    assert (await async_client.get("/api/projects/does-not-exist/chat/status")).status_code == 404


# ---------------------------------------------------------------------------------------------------------------
# a conversation id must belong to the project
# ---------------------------------------------------------------------------------------------------------------

async def _other_project(client: AsyncClient) -> dict:
    res = await client.post("/api/projects", json={"name": f"c-{uuid.uuid4().hex[:10]}", "source_type": "blank"})
    assert res.status_code == 201, res.text
    return res.json()


async def _message_count(conversation_id: str) -> int:
    from sqlalchemy import func, select

    from app.database import AsyncSessionLocal
    from app.models.conversation import Message

    async with AsyncSessionLocal() as session:
        return (await session.execute(select(func.count()).select_from(Message).where(Message.conversation_id == conversation_id))).scalar_one()


async def test_a_conversation_of_another_project_cannot_be_used(async_client, project, monkeypatch, outbound):
    configure(monkeypatch, "mock", "mock-key", consent=False)
    other = await _other_project(async_client)
    foreign = (await ask(async_client, other, "hello")).json()["conversation_id"]
    before = await _message_count(foreign)

    res = await ask(async_client, project, "hello", conversation_id=foreign)

    assert res.status_code == 404
    assert res.json()["detail"] == "Conversation not found in this project."
    assert await _message_count(foreign) == before, "a message was written into another project's conversation"
    assert outbound.sent == []


async def test_an_unknown_conversation_id_is_404(async_client, project, monkeypatch):
    configure(monkeypatch, "mock", "mock-key", consent=False)
    assert (await ask(async_client, project, "hello", conversation_id=str(uuid.uuid4()))).status_code == 404


async def test_the_projects_own_conversation_id_still_works(async_client, project, monkeypatch):
    configure(monkeypatch, "mock", "mock-key", consent=False)
    first = (await ask(async_client, project, "one")).json()
    second = await ask(async_client, project, "two", conversation_id=first["conversation_id"])
    assert second.status_code == 200 and second.json()["conversation_id"] == first["conversation_id"]
    assert await _message_count(first["conversation_id"]) == 4


# ---------------------------------------------------------------------------------------------------------------
# source-level tripwires
# ---------------------------------------------------------------------------------------------------------------

def _code(path: Path) -> str:
    """Source with comments and docstrings removed, so explanations cannot trip the checks."""
    import ast
    import io
    import tokenize

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant) and isinstance(first.value.value, str):
                first.value.value = ""
    kept = [t for t in tokenize.generate_tokens(io.StringIO(ast.unparse(tree)).readline) if t.type != tokenize.COMMENT]
    return tokenize.untokenize(kept)


def test_only_llm_py_makes_chat_requests_and_the_only_other_httpx_user_is_the_github_import():
    users = sorted(
        str(p.relative_to(APP)).replace("\\", "/")
        for p in APP.rglob("*.py")
        if re.search(r"^\s*(import httpx|from httpx\b)", p.read_text(encoding="utf-8"), re.M)
    )
    # api/run.py is the project proxy: it only ever talks to 127.0.0.1 (pinned by test_run.py), never to a provider
    assert users == ["api/projects.py", "api/run.py", "services/llm.py"], f"unexpected module(s) import httpx: {users}"


def test_the_chat_api_module_has_no_network_or_file_access_of_its_own():
    code = _code(APP / "api" / "chat.py")
    assert not re.search(r"\bhttpx\b|\burllib\b|\brequests\b|\bsocket\b|\baiohttp\b", code)
    assert not re.search(r"\bopen\(|os\.walk|os\.scandir|os\.listdir|read_text|read_bytes|\bPath\(|workspace|retrieval", code)
    text = (APP / "api" / "chat.py").read_text(encoding="utf-8")
    assert "from app.services.grounding import" in text and "from app.services.llm import provider_status" in text
    assert "call_external_llm" not in code, "the sending function is reached only through grounding"


def test_llm_py_builds_exactly_one_http_client_and_talks_to_three_hosts_only():
    code = _code(APP / "services" / "llm.py")
    assert len(re.findall(r"httpx\.AsyncClient\(", code)) == 1
    assert len(re.findall(r"\.post\(", code)) == 2  # openai-compatible, gemini
    hosts = sorted(set(re.findall(r"https?://([a-z0-9.\-]+)", code)))
    assert hosts == ["api.groq.com", "api.openai.com", "generativelanguage.googleapis.com"]


def test_llm_py_does_not_read_project_files():
    code = _code(APP / "services" / "llm.py")
    assert not re.search(r"\bopen\(|os\.walk|os\.scandir|os\.listdir|read_text|read_bytes|\bPath\b|root_path|scan_workspace", code)


def test_the_consent_check_comes_before_any_request_in_the_only_sending_function():
    code = (APP / "services" / "llm.py").read_text(encoding="utf-8")
    body = code[code.index("async def call_external_llm") :]
    assert body.index("consent_problem()") < body.index("httpx.AsyncClient(")
    assert body.index("llm_config_problem()") < body.index("httpx.AsyncClient(")


def test_configuration_and_consent_are_checked_before_any_project_file_is_read_or_anything_is_sent():
    code = _code(APP / "services" / "grounding.py")
    flow = code[code.index("async def answer_grounded") :]
    assert flow.index("llm.send_blocker()") < flow.index("retrieval.retrieve") < flow.index("llm.call_external_llm(")
    assert "asyncio.to_thread(retrieval.retrieve" in flow, "retrieval runs in a worker thread"
    before = code[: code.index("async def answer_grounded")]
    # The only other reader is the gated helper guided changes use (app/services/changes.py calls send_blocker first; see
    # test_changes.py). Nothing else in grounding.py may search the project.
    assert before.count("retrieval.retrieve") == 1 and "retrieval.retrieve(project_root, request," in before[before.index("def retrieve_context") :], "no other function in grounding.py reads the project"

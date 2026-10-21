"""Guided changes (analyze -> plan -> propose -> approve/apply -> revert) through the HTTP API, with a fake provider."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services import changes, llm

KEY = "sk-proj-AbCdEf0123456789AbCdEf0123456789AbCdEf0123456789"
SERVICE = "def greet(name):\n    return 'hi ' + name\n\n\ndef bye(name):\n    return 'bye ' + name\n"
OTHER = "from service import greet\n\nprint(greet('x'))\n"


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None):
        self.status_code, self._body, self.headers = status_code, body or {}, headers or {}

    def json(self):
        return self._body


def reply(payload):
    return FakeResponse(200, {"choices": [{"message": {"content": json.dumps(payload)}}]})


@pytest.fixture
def provider(monkeypatch):
    state = SimpleNamespace(sent=[], respond=lambda body: reply({}), sleeps=[])

    class FakeClient:
        def __init__(self, **_kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def post(self, url, headers=None, json=None):
            state.sent.append(dict(json))
            return state.respond(json)

    async def fake_sleep(seconds):
        state.sleeps.append(seconds)

    monkeypatch.setattr(llm, "httpx", SimpleNamespace(AsyncClient=FakeClient))
    monkeypatch.setattr(llm.asyncio, "sleep", fake_sleep)
    return state


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "LLM_API_KEY", KEY)
    monkeypatch.setattr(settings, "LLM_MODEL", "test-model")
    monkeypatch.setattr(settings, "ALLOW_SENDING_CODE_TO_PROVIDER", True)


@pytest.fixture
def root(project) -> Path:
    path = Path(project["root_path"])
    (path / "service.py").write_bytes(SERVICE.encode())
    (path / "other.py").write_bytes(OTHER.encode())
    return path


def url(project, tail):
    return f"/api/projects/{project['id']}/changes/{tail}"


MODIFY = {"action": "modify", "path": "service.py", "what": "make greeting polite"}
CREATE = {"action": "create", "path": "util/helpers.py", "what": "add a helper"}
GOOD_EDIT = {"explanation": "change greeting", "edits": [{"old": "return 'hi ' + name", "new": "return 'hello ' + name"}]}
NEW_FILE = {"explanation": "adds helper", "content": "def helper():\n    return 1\n"}


def by_step(**replies):
    """A provider that answers each per-file request according to the path named in 'YOUR STEP: <action> <path>:'."""
    def respond(body):
        text = body["messages"][1]["content"]
        for path, payload in replies.items():
            if f"YOUR STEP: modify {path}:" in text or f"YOUR STEP: create {path}:" in text:
                return reply(payload)
        return reply({})
    return respond


async def propose(client, project, steps=(MODIFY,), **extra):
    return await client.post(url(project, "propose"), json={"request": "make greet polite", "steps": list(steps), **extra})


# --- analyze: detection, impact and plan -------------------------------------------------------------------------------
async def test_analyze_returns_impact_and_a_plan_with_only_real_or_allowed_paths(async_client, project, root, provider):
    provider.respond = lambda body: reply({
        "summary": "greet is used by other.py", "risk": "medium", "risk_reasons": ["used elsewhere"],
        "affected_files": [
            {"path": "service.py", "category": "direct", "why": "defines greet"},
            {"path": "other.py", "category": "indirect", "why": "calls greet"},
            {"path": "ghost.py", "category": "direct", "why": "does not exist"},
            {"path": "../outside.py", "category": "direct", "why": "escape"},
        ],
        "plan": [
            MODIFY, {"action": "modify", "path": "ghost.py", "what": "invented"},
            CREATE, {"action": "create", "path": "service.py", "what": "already there"},
            {"action": "create", "path": ".env", "what": "secrets"}, {"action": "create", "path": "../x.py", "what": "escape"},
            {"action": "create", "path": "node_modules/a.js", "what": "dependency folder"}, {"action": "delete", "path": "other.py"},
        ],
        "questions": ["Keep the old name as an alias?"],
    })
    res = await async_client.post(url(project, "analyze"), json={"request": "make the greeting polite"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert [f["path"] for f in body["affected_files"]] == ["service.py", "other.py"]
    assert [(s["id"], s["action"], s["path"]) for s in body["plan"]] == [(1, "modify", "service.py"), (2, "create", "util/helpers.py")]
    assert len(body["skipped_steps"]) == 6
    assert body["risk"] == "medium" and body["questions"] == ["Keep the old name as an alias?"]
    assert (root / "service.py").read_text() == SERVICE and not (root / "util").exists()


async def test_analyze_sends_the_file_list_so_the_model_can_see_the_project(async_client, project, root, provider):
    provider.respond = lambda body: reply({"summary": "x", "plan": []})
    await async_client.post(url(project, "analyze"), json={"request": "make the greeting polite"})
    user = provider.sent[0]["messages"][1]["content"]
    assert "service.py" in user and "other.py" in user and "make the greeting polite" in user


async def test_analyze_sends_nothing_without_consent(async_client, project, root, provider, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_SENDING_CODE_TO_PROVIDER", False)
    res = await async_client.post(url(project, "analyze"), json={"request": "rename greet"})
    assert res.status_code == 503 and res.json()["detail"]["code"] == "not_sendable"
    assert provider.sent == []


# --- propose: modify and create -----------------------------------------------------------------------------------------
async def test_propose_builds_diffs_for_edits_and_new_files_and_writes_nothing(async_client, project, root, provider):
    provider.respond = by_step(**{"service.py": GOOD_EDIT, "util/helpers.py": NEW_FILE})
    res = await propose(async_client, project, steps=[MODIFY, CREATE])
    assert res.status_code == 200, res.text
    files = {f["path"]: f for f in res.json()["files"]}
    assert files["service.py"]["is_new"] is False and "+    return 'hello ' + name" in files["service.py"]["diff"]
    assert files["util/helpers.py"]["is_new"] is True and "+def helper():" in files["util/helpers.py"]["diff"] and files["util/helpers.py"]["removed"] == 0
    assert (root / "service.py").read_text() == SERVICE and not (root / "util").exists()
    assert len(provider.sent) == 2, "one small request per file"


async def test_one_failing_file_does_not_stop_the_others(async_client, project, root, provider):
    bad = {"explanation": "x", "edits": [{"old": "text that is not there", "new": "z"}]}
    provider.respond = by_step(**{"service.py": bad, "util/helpers.py": NEW_FILE})
    body = (await propose(async_client, project, steps=[MODIFY, CREATE])).json()
    assert [f["path"] for f in body["files"]] == ["util/helpers.py"]
    assert body["rejected"][0]["path"] == "service.py" and "does not match" in body["rejected"][0]["reason"]


async def test_an_edit_that_matches_twice_or_not_at_all_is_rejected(async_client, project, root, provider):
    for old in ("return", "text that is not there"):
        provider.respond = lambda body, old=old: reply({"explanation": "x", "edits": [{"old": old, "new": "z"}]})
        res = await propose(async_client, project)
        assert res.status_code == 422 and res.json()["detail"]["code"] == "no_usable_edits"
    assert (root / "service.py").read_text() == SERVICE


async def test_steps_the_model_or_user_invents_are_never_carried_out(async_client, project, root, provider):
    provider.respond = lambda body: reply(GOOD_EDIT)
    steps = [MODIFY, {"action": "modify", "path": "../etc/passwd", "what": "x"}, {"action": "create", "path": ".env", "what": "x"}]
    body = (await propose(async_client, project, steps=steps)).json()
    assert [f["path"] for f in body["files"]] == ["service.py"] and len(body["rejected"]) == 2
    assert len(provider.sent) == 1


async def test_generated_files_that_look_like_secrets_are_discarded(async_client, project, root, provider):
    leak = {"explanation": "x", "content": f'API_KEY = "{KEY}"\n'}
    provider.respond = lambda body: reply(leak)
    res = await propose(async_client, project, steps=[CREATE])
    assert res.status_code == 422 and "secret" in res.json()["detail"]["message"]
    assert not (root / "util").exists()


async def test_a_file_with_a_secret_is_not_sent_for_editing(async_client, project, root, provider):
    (root / "settings.py").write_text(f'API_KEY = "{KEY}"\n')
    res = await propose(async_client, project, steps=[{"action": "modify", "path": "settings.py", "what": "x"}])
    assert res.status_code == 422 and res.json()["detail"]["code"] == "no_usable_steps"
    assert provider.sent == []


async def test_a_large_file_is_sent_as_matching_parts_not_whole(async_client, project, root, provider):
    filler = "".join(f"# filler line {i}\n" for i in range(3000))
    (root / "big.py").write_text(filler + "def polite_greeting(name):\n    return 'hi ' + name\n" + filler)
    provider.respond = lambda body: reply({"explanation": "x", "edits": [{"old": "return 'hi ' + name", "new": "return 'hello ' + name"}]})
    res = await propose(async_client, project, steps=[{"action": "modify", "path": "big.py", "what": "polite_greeting"}], request="make polite_greeting polite")
    assert res.status_code == 200, res.text
    assert len(provider.sent[0]["messages"][1]["content"]) < 30_000


async def test_crlf_files_keep_their_line_endings(async_client, project, root, provider):
    (root / "service.py").write_bytes(SERVICE.replace("\n", "\r\n").encode())
    provider.respond = lambda body: reply(GOOD_EDIT)
    pid = (await propose(async_client, project)).json()["proposal_id"]
    assert (await async_client.post(url(project, "apply"), json={"proposal_id": pid, "paths": ["service.py"]})).status_code == 200
    data = (root / "service.py").read_bytes()
    assert b"hello" in data and data.count(b"\n") == data.count(b"\r\n")


# --- apply / revert --------------------------------------------------------------------------------------------------
async def test_approved_edits_and_new_files_are_written_and_can_be_reverted(async_client, project, root, provider):
    provider.respond = by_step(**{"service.py": GOOD_EDIT, "util/helpers.py": NEW_FILE})
    pid = (await propose(async_client, project, steps=[MODIFY, CREATE])).json()["proposal_id"]
    res = await async_client.post(url(project, "apply"), json={"proposal_id": pid, "paths": ["service.py", "util/helpers.py"]})
    assert res.status_code == 200 and res.json()["applied"] == ["service.py", "util/helpers.py"]
    assert "hello " in (root / "service.py").read_text() and (root / "util" / "helpers.py").read_text() == NEW_FILE["content"]
    assert (await async_client.post(url(project, "apply"), json={"proposal_id": pid, "paths": ["service.py"]})).status_code == 409
    back = await async_client.post(url(project, "revert"), json={"proposal_id": pid})
    assert back.status_code == 200 and (root / "service.py").read_text() == SERVICE
    assert not (root / "util").exists(), "the created file and the folder made for it are removed"


async def test_apply_refuses_when_a_file_changed_since_the_proposal(async_client, project, root, provider):
    provider.respond = lambda body: reply(GOOD_EDIT)
    pid = (await propose(async_client, project)).json()["proposal_id"]
    (root / "service.py").write_text(SERVICE + "# edited by hand\n")
    res = await async_client.post(url(project, "apply"), json={"proposal_id": pid, "paths": ["service.py"]})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "file_changed"
    assert "hello" not in (root / "service.py").read_text() and (root / "service.py").read_text().endswith("# edited by hand\n")


async def test_a_new_file_is_never_created_over_something_that_appeared_meanwhile(async_client, project, root, provider):
    provider.respond = lambda body: reply(NEW_FILE)
    pid = (await propose(async_client, project, steps=[CREATE])).json()["proposal_id"]
    (root / "util").mkdir()
    (root / "util" / "helpers.py").write_text("mine\n")
    res = await async_client.post(url(project, "apply"), json={"proposal_id": pid, "paths": ["util/helpers.py"]})
    assert res.status_code == 409 and (root / "util" / "helpers.py").read_text() == "mine\n"


async def test_if_one_write_fails_the_ones_before_it_are_undone(async_client, project, root, provider, monkeypatch):
    provider.respond = by_step(**{"service.py": GOOD_EDIT, "util/helpers.py": NEW_FILE})
    pid = (await propose(async_client, project, steps=[MODIFY, CREATE])).json()["proposal_id"]

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(changes, "_create_file", boom)
    res = await async_client.post(url(project, "apply"), json={"proposal_id": pid, "paths": ["service.py", "util/helpers.py"]})
    assert res.status_code == 409 and res.json()["detail"]["code"] == "apply_failed"
    assert (root / "service.py").read_text() == SERVICE


async def test_only_approved_files_of_a_proposal_are_written(async_client, project, root, provider):
    other = {"explanation": "x", "edits": [{"old": "print(greet('x'))", "new": "print(greet('y'))"}]}
    provider.respond = by_step(**{"service.py": GOOD_EDIT, "other.py": other})
    pid = (await propose(async_client, project, steps=[MODIFY, {"action": "modify", "path": "other.py", "what": "x"}])).json()["proposal_id"]
    assert (await async_client.post(url(project, "apply"), json={"proposal_id": pid, "paths": ["service.py"]})).status_code == 200
    assert (root / "other.py").read_text() == OTHER


async def test_apply_rejects_paths_outside_the_proposal_and_unknown_proposals(async_client, project, root, provider):
    provider.respond = lambda body: reply(GOOD_EDIT)
    pid = (await propose(async_client, project)).json()["proposal_id"]
    res = await async_client.post(url(project, "apply"), json={"proposal_id": pid, "paths": ["other.py"]})
    assert res.status_code == 400 and res.json()["detail"]["code"] == "not_in_proposal"
    assert (await async_client.post(url(project, "apply"), json={"proposal_id": "nope", "paths": ["service.py"]})).status_code == 404


async def test_revert_refuses_to_overwrite_later_edits(async_client, project, root, provider):
    provider.respond = lambda body: reply(GOOD_EDIT)
    pid = (await propose(async_client, project)).json()["proposal_id"]
    await async_client.post(url(project, "apply"), json={"proposal_id": pid, "paths": ["service.py"]})
    (root / "service.py").write_text("my own later work\n")
    res = await async_client.post(url(project, "revert"), json={"proposal_id": pid})
    assert res.status_code == 409 and (root / "service.py").read_text() == "my own later work\n"


async def test_a_proposal_cannot_be_used_from_another_project(async_client, project, root, provider):
    provider.respond = lambda body: reply(GOOD_EDIT)
    pid = (await propose(async_client, project)).json()["proposal_id"]
    with pytest.raises(changes.ChangeError):
        changes.get_proposal(pid, "some-other-project")


# --- the provider call: rate limits, strict-JSON failures, readable errors -----------------------------------------------
async def test_a_rate_limit_is_waited_out_and_retried(async_client, project, root, provider):
    answers = [FakeResponse(429, {"error": {"message": "Rate limit reached. Please try again in 7.5s."}}), reply({"summary": "ok", "plan": []})]
    provider.respond = lambda body: answers.pop(0)
    res = await async_client.post(url(project, "analyze"), json={"request": "make the greeting polite"})
    assert res.status_code == 200 and res.json()["summary"] == "ok"
    assert provider.sleeps == [8.0]


async def test_a_long_rate_limit_is_reported_with_the_provider_message_not_waited_for(async_client, project, root, provider):
    provider.respond = lambda body: FakeResponse(429, {"error": {"message": "Rate limit reached. Please try again in 58s."}})
    res = await async_client.post(url(project, "analyze"), json={"request": "make the greeting polite"})
    assert res.status_code == 502 and "HTTP 429" in res.json()["detail"]["message"] and "try again in about 59s" in res.json()["detail"]["message"]
    assert provider.sleeps == []


async def test_invalid_json_from_the_strict_mode_is_retried_without_it(async_client, project, root, provider):
    answers = [FakeResponse(400, {"error": {"code": "json_validate_failed", "message": "Failed to generate JSON."}}),
               FakeResponse(200, {"choices": [{"message": {"content": 'Sure!\n```json\n{"summary": "fine", "plan": []}\n```'}}]})]
    provider.respond = lambda body: answers.pop(0)
    res = await async_client.post(url(project, "analyze"), json={"request": "make the greeting polite"})
    assert res.status_code == 200 and res.json()["summary"] == "fine"
    assert "response_format" in provider.sent[0] and "response_format" not in provider.sent[1]


async def test_provider_free_text_is_never_shown_only_its_short_code(async_client, project, root, provider):
    provider.respond = lambda body: FakeResponse(400, {"error": {"code": "context_length_exceeded", "message": f"echo of the prompt and {KEY}"}})
    res = await async_client.post(url(project, "analyze"), json={"request": "make the greeting polite"})
    assert res.status_code == 502 and "context_length_exceeded" in res.text
    assert KEY not in res.text and "echo of the prompt" not in res.text


def test_changes_check_configuration_and_consent_before_any_project_file_is_read():
    """Same rule as grounding: nothing is read or sent until send_blocker passes, and only grounding's helpers touch files."""
    import re

    source = Path(changes.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from app\.services import .*\bretrieval\b|from app\.services\.retrieval\b|import app\.services\.retrieval)", source, re.M)
    for name in ("analyze", "propose"):
        body = source[source.index(f"async def {name}(") :]
        end = body.find("\nasync def ", 10)
        body = body[:end] if end != -1 else body[: body.index("\ndef ", 10)]
        first_read = min(body.index(marker) for marker in ("grounding.", "_root_real(", "_prepare_step", "_check_step") if marker in body)
        assert body.index("_check_sendable()") < first_read, f"{name}: consent must be checked before project files are read"

"""What the chat endpoint may and may not do with a model, and what it says when there is none.

The HTTP client used by app.services.llm is replaced by a recorder, so every test can assert exactly
what (if anything) would have left the machine, to which host, and with which key. Nothing here
touches the network.
"""
import json
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.config import settings
from app.services import llm

PROVIDER_ENV_KEYS = ["OPENAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"]
CODE_PROMPT = "Explain def secret_algorithm(): return 42 in app/main.py"


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {}

    def json(self):
        return self._body


def openai_reply(payload: dict) -> FakeResponse:
    return FakeResponse(200, {"choices": [{"message": {"content": json.dumps(payload)}}]})


def answer(text: str, citations=None, answerable: bool = True) -> dict:
    """The structured reply the chat expects from a model: {"answerable", "answer", "citations"}."""
    return {"answerable": answerable, "answer": text, "citations": citations or []}


@pytest.fixture
def outbound(monkeypatch):
    """Replace the HTTP client. `outbound.sent` lists every request; set `outbound.respond` to script replies."""
    state = SimpleNamespace(sent=[], respond=lambda url: FakeResponse(500))

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def post(self, url, headers=None, json=None):
            state.sent.append({"url": url, "headers": headers or {}, "json": json})
            result = state.respond(url)
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(llm, "httpx", SimpleNamespace(AsyncClient=FakeClient))
    return state


@pytest.fixture
def no_provider_keys_in_env(monkeypatch):
    for name in PROVIDER_ENV_KEYS:
        monkeypatch.delenv(name, raising=False)


def configure(monkeypatch, provider: str, key: str = "mock-key", model: str = "test-model", consent: bool = False):
    """Choose a provider. `consent` is ALLOW_SENDING_CODE_TO_PROVIDER: tests that expect a request must pass True."""
    monkeypatch.setattr(settings, "LLM_PROVIDER", provider)
    monkeypatch.setattr(settings, "LLM_API_KEY", key)
    monkeypatch.setattr(settings, "LLM_MODEL", model)
    monkeypatch.setattr(settings, "ALLOW_SENDING_CODE_TO_PROVIDER", consent)


async def ask(client: AsyncClient, project: dict, message: str = CODE_PROMPT, mode: str = "agent") -> dict:
    res = await client.post(f"/api/projects/{project['id']}/chat", json={"message": message, "mode": mode})
    assert res.status_code == 200, res.text
    return res.json()


# --- LLM_PROVIDER=mock must never send anything ----------------------------------------------

@pytest.mark.parametrize("env_key", PROVIDER_ENV_KEYS)
async def test_mock_provider_sends_nothing_even_when_a_provider_key_is_in_the_environment(
    async_client, project, monkeypatch, outbound, env_key
):
    configure(monkeypatch, "mock")
    monkeypatch.setenv(env_key, "sk-real-looking-key-from-the-environment")

    reply = await ask(async_client, project)

    assert outbound.sent == [], "code or file excerpts were sent to an external provider while LLM_PROVIDER=mock"
    assert reply["content"].startswith("AI chat is not available yet")
    assert reply["plan_steps"] == [] and reply["citations"] == []


async def test_mock_provider_sends_nothing_with_every_provider_key_set_at_once(async_client, project, monkeypatch, outbound):
    configure(monkeypatch, "mock")
    for name in PROVIDER_ENV_KEYS:
        monkeypatch.setenv(name, "sk-real-looking-key-from-the-environment")
    await ask(async_client, project)
    assert outbound.sent == []


async def test_mock_provider_sends_nothing_even_if_a_real_looking_key_is_in_settings(async_client, project, monkeypatch, outbound):
    configure(monkeypatch, "mock", key="sk-this-looks-real")
    await ask(async_client, project)
    assert outbound.sent == []


@pytest.mark.parametrize("spelling", ["MOCK", " mock ", "Mock", ""])
async def test_mock_is_recognised_regardless_of_case_or_whitespace(async_client, project, monkeypatch, outbound, spelling):
    configure(monkeypatch, spelling, key="sk-this-looks-real")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-environment")
    reply = await ask(async_client, project)
    assert outbound.sent == []
    assert reply["content"].startswith("AI chat is not available yet")


async def test_environment_keys_are_never_used_for_a_chosen_provider_either(async_client, project, monkeypatch, outbound):
    """Choosing openai with a placeholder key must not quietly borrow OPENAI_API_KEY from the environment."""
    configure(monkeypatch, "openai", key="mock-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-environment")
    reply = await ask(async_client, project)
    assert outbound.sent == []
    assert "LLM_API_KEY" in reply["content"] and "openai" in reply["content"]


# --- Anthropic and other unsupported providers: an explicit error, never a silent fallback ---

@pytest.mark.parametrize("provider", ["anthropic", "Anthropic", "acme-ai"])
async def test_unsupported_provider_returns_a_clear_error_and_sends_nothing(
    async_client, project, monkeypatch, outbound, no_provider_keys_in_env, provider
):
    configure(monkeypatch, provider, key="sk-real-looking")
    reply = await ask(async_client, project)

    assert outbound.sent == []
    assert provider.strip().lower() in reply["content"]
    assert "not supported" in reply["content"]
    assert "openai" in reply["content"] and "gemini" in reply["content"], "should say what is supported"
    assert reply["plan_steps"] == [] and reply["citations"] == []


async def test_anthropic_key_in_the_environment_does_not_make_anthropic_work(async_client, project, monkeypatch, outbound):
    configure(monkeypatch, "mock")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-real-looking")
    reply = await ask(async_client, project)
    assert outbound.sent == []
    assert reply["content"].startswith("AI chat is not available yet")


# --- when a supported provider IS configured ------------------------------------------------

async def test_configured_openai_is_called_with_the_settings_key_and_only_that_host(
    async_client, project, monkeypatch, outbound, no_provider_keys_in_env
):
    configure(monkeypatch, "openai", key="sk-from-settings", model="gpt-test", consent=True)
    monkeypatch.setenv("GROQ_API_KEY", "sk-other-provider")
    outbound.respond = lambda url: openai_reply(answer("Real model answer"))

    reply = await ask(async_client, project)

    assert reply["content"] == "Real model answer"
    assert reply["status"] == "answered_unverified", "an answer without any citation is never reported as verified"
    assert len(outbound.sent) == 1
    sent = outbound.sent[0]
    assert sent["url"] == "https://api.openai.com/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer sk-from-settings"
    assert sent["json"]["model"] == "gpt-test"
    assert sent["json"]["temperature"] == 0 and sent["json"]["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in sent["json"]["messages"]] == ["system", "user"]


@pytest.mark.parametrize(
    "provider,host",
    [("groq", "https://api.groq.com/"), ("gemini", "https://generativelanguage.googleapis.com/")],
)
async def test_other_supported_providers_go_only_to_their_own_host(
    async_client, project, monkeypatch, outbound, no_provider_keys_in_env, provider, host
):
    configure(monkeypatch, provider, key="sk-from-settings", consent=True)
    if provider == "gemini":
        outbound.respond = lambda url: FakeResponse(
            200, {"candidates": [{"content": {"parts": [{"text": json.dumps(answer("ok"))}]}}]}
        )
    else:
        outbound.respond = lambda url: openai_reply(answer("ok"))
    reply = await ask(async_client, project)
    assert reply["content"] == "ok"
    assert [r["url"].startswith(host) for r in outbound.sent] == [True]


async def test_a_failing_provider_is_reported_as_an_error_not_covered_up_with_made_up_analysis(
    async_client, project, monkeypatch, outbound, no_provider_keys_in_env
):
    configure(monkeypatch, "openai", key="sk-from-settings", consent=True)
    outbound.respond = lambda url: FakeResponse(500)

    reply = await ask(async_client, project, "Explain what app/main.py does")

    assert len(outbound.sent) == 1, "the question must have found excerpts, otherwise the provider is never called"
    assert "openai" in reply["content"] and "HTTP 500" in reply["content"]
    assert "No answer was produced" in reply["content"]
    assert reply["status"] == "unavailable"
    assert reply["plan_steps"] == [] and reply["citations"] == []
    for invented in ("Approve Plan", "assert True", "sliding-window", "indexed", "I scanned"):
        assert invented not in reply["content"]


async def test_a_network_error_never_leaks_the_api_key_into_the_reply_or_the_logs(
    async_client, project, monkeypatch, outbound, no_provider_keys_in_env, caplog
):
    secret = "sk-SUPER-SECRET-123"
    configure(monkeypatch, "gemini", key=secret, consent=True)
    # httpx error messages can contain the full request URL
    outbound.respond = lambda url: ConnectionError(f"cannot reach {url}")

    reply = await ask(async_client, project)

    assert secret not in reply["content"]
    assert secret not in caplog.text
    assert "gemini" in reply["content"] and "ConnectionError" in reply["content"]
    assert secret not in outbound.sent[0]["url"], "the Gemini key must travel in a header, never in the URL"
    assert outbound.sent[0]["headers"]["x-goog-api-key"] == secret


async def test_gemini_key_is_sent_in_a_header_and_never_in_the_address(
    async_client, project, monkeypatch, outbound, no_provider_keys_in_env, caplog
):
    secret = "sk-GEMINI-SECRET-456"
    configure(monkeypatch, "gemini", key=secret, model="gemini-test", consent=True)
    outbound.respond = lambda url: FakeResponse(
        200, {"candidates": [{"content": {"parts": [{"text": json.dumps({"content": "ok"})}]}}]}
    )
    reply = await ask(async_client, project)
    request = outbound.sent[0]
    assert request["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent"
    assert "key=" not in request["url"] and secret not in request["url"]
    assert request["headers"]["x-goog-api-key"] == secret
    assert secret not in json.dumps(request["json"]), "the key must not be in the request body either"
    assert secret not in reply["content"] and secret not in caplog.text


async def test_a_reply_that_is_not_valid_json_is_an_error(async_client, project, monkeypatch, outbound, no_provider_keys_in_env):
    configure(monkeypatch, "openai", key="sk-from-settings", consent=True)
    outbound.respond = lambda url: FakeResponse(200, {"choices": [{"message": {"content": "not json at all"}}]})
    reply = await ask(async_client, project)
    assert "openai" in reply["content"] and "No answer was produced" in reply["content"]
    assert reply["status"] == "unavailable" and reply["citations"] == []
    assert "not json at all" not in reply["content"], "the raw reply must never be shown"


# --- no invented analysis when there is no model ---------------------------------------------

@pytest.mark.parametrize(
    "message,mode",
    [
        ("add rate limiting middleware", "agent"),
        ("how does auth and jwt token security work?", "agent"),
        ("write pytest tests for the router", "chat"),
        ("where is the main entrypoint?", "chat"),
        ("review this project", "review"),
        ("something unrelated", "agent"),
    ],
)
async def test_without_a_model_every_prompt_gets_the_same_plain_notice(async_client, project, monkeypatch, outbound, message, mode):
    configure(monkeypatch, "mock")
    reply = await ask(async_client, project, message, mode)
    assert reply["content"] == llm.llm_config_problem()
    assert reply["plan_steps"] == []
    assert reply["citations"] == []
    for invented in ("Approve Plan", "assert True", "sliding-window", "indexed", "I analyzed", "I scanned", "app/main.py"):
        assert invented not in reply["content"]


# --- chat.py no longer invents citations or steps for incomplete model output ----------------

async def test_model_supplied_plan_steps_and_unchecked_citations_are_never_passed_on(
    async_client, project, monkeypatch, outbound, no_provider_keys_in_env
):
    """Citations must name an excerpt this request supplied; anything else is rejected, and plan steps are never stored."""
    configure(monkeypatch, "openai", key="sk-from-settings", consent=True)
    outbound.respond = lambda url: openai_reply(
        {
            "answerable": True,
            "answer": "answer",
            "citations": [{"line_start": 3}, {"file_path": "app/main.py", "line_start": 1, "line_end": 4}, {"excerpt_id": "E999", "line_start": 1, "line_end": 2}],
            "plan_steps": [{"id": 1}, {"id": 2, "text": "Do the thing", "tool": "modify_file", "status": "pending"}],
        }
    )
    reply = await ask(async_client, project, "Explain what app/main.py does")
    assert reply["content"] == "answer"
    assert reply["citations"] == [], "none of these cites an excerpt that was supplied, so none may be listed"
    assert reply["plan_steps"] == []
    assert reply["status"] == "answered_unverified"
    assert [c["status"] for c in reply["grounding"]["citations"]] == ["invalid"] * 3


async def test_a_reply_in_the_old_free_text_format_is_not_accepted(async_client, project, monkeypatch, outbound, no_provider_keys_in_env):
    configure(monkeypatch, "openai", key="sk-from-settings", consent=True)
    outbound.respond = lambda url: openai_reply({"content": "an answer in the old format", "plan_steps": [], "citations": []})
    reply = await ask(async_client, project, "Explain what app/main.py does")
    assert reply["status"] == "unavailable" and "unusable format" in reply["content"]
    assert "old format" not in reply["content"]


# --- the configuration check itself ----------------------------------------------------------

def test_config_check_only_passes_for_a_supported_provider_with_a_real_key(monkeypatch):
    configure(monkeypatch, "openai", key="sk-real")
    assert llm.llm_config_problem() is None
    configure(monkeypatch, "openai", key="your-llm-api-key-here")
    assert llm.llm_config_problem() is not None
    configure(monkeypatch, "openai", key="   ")
    assert llm.llm_config_problem() is not None
    configure(monkeypatch, "anthropic", key="sk-real")
    assert "not supported" in llm.llm_config_problem()

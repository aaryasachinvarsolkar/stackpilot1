"""The one place where chat content can leave this machine.

This module only talks to providers. It reads no project files and builds no prompts: `grounding.py` decides what is
asked and `retrieval.py` finds the excerpts. Before anything is sent two things must hold: a supported provider is
configured with a real key (`llm_config_problem`), and the owner has switched on ALLOW_SENDING_CODE_TO_PROVIDER in the
backend's environment (`consent_problem`). `send_blocker` combines the two for callers that must check first, and
`call_external_llm`, the only function that builds an HTTP client, checks both again, so no caller can skip them.
"""
import asyncio
import json
import logging
import re
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger("stackpilot.llm")

SUPPORTED_PROVIDERS = ("openai", "groq", "gemini")
_PLACEHOLDER_KEYS = ("", "mock-key", "mock-dev-key", "your-llm-api-key-here")

# Free-tier providers limit tokens per minute; a short wait is better than failing, a long one is reported instead.
MAX_RATE_LIMIT_WAIT_SECONDS = 25.0
MAX_RATE_LIMIT_RETRIES = 2


def _loads_lenient(text: str) -> Any:
    """Parse a JSON reply, tolerating code fences or a sentence around the object. Raises ValueError if there is none."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except ValueError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


def _provider_message(res: Any) -> str:
    """The provider's own free-text explanation, used ONLY to read a wait time out of it. Never shown or logged: it can echo the prompt."""
    try:
        message = (res.json().get("error") or {}).get("message")
    except Exception:
        return ""
    return " ".join(message.split())[:400] if isinstance(message, str) else ""


_CODE = re.compile(r"[a-z][a-z_]{2,39}")


def _error_code(res: Any) -> str:
    """The provider's short machine code (e.g. json_validate_failed), only if it is a plain lowercase word; else empty."""
    try:
        code = (res.json().get("error") or {}).get("code")
    except Exception:
        return ""
    return code if isinstance(code, str) and _CODE.fullmatch(code) else ""


def _retry_wait(res: Any) -> Optional[float]:
    """Seconds the provider asks us to wait after HTTP 429, or None if it does not say."""
    headers = getattr(res, "headers", None) or {}
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        pass
    match = re.search(r"try again in (?:(\d+)m)?\s*([\d.]+)s", _provider_message(res), re.I)
    return (int(match.group(1) or 0) * 60 + float(match.group(2))) if match else None


class LLMCallError(Exception):
    """A configured model could not be reached or did not answer usably. The message is safe to show."""


class ConsentError(LLMCallError):
    """Sending to a provider is switched off. Raised before any request is built."""


def llm_config_problem() -> Optional[str]:
    """Return None if a supported provider is fully configured, else a plain-language reason it is not.

    Reads StackPilot's own settings only. Provider keys in the process environment (OPENAI_API_KEY and
    similar) are deliberately ignored: with LLM_PROVIDER=mock nothing may leave this machine, and a
    provider is only ever used because it was chosen in the settings.
    """
    provider = (settings.LLM_PROVIDER or "").strip().lower()
    if provider in ("", "mock"):
        return (
            "AI chat is not available yet: no model is connected (LLM_PROVIDER is 'mock'). "
            "Nothing was sent anywhere, and your files were not analysed."
        )
    if provider not in SUPPORTED_PROVIDERS:
        return (
            f"AI chat cannot use the '{provider}' provider: it is not supported in this build "
            f"(supported: {', '.join(SUPPORTED_PROVIDERS)}). Nothing was sent anywhere."
        )
    if (settings.LLM_API_KEY or "").strip() in _PLACEHOLDER_KEYS:
        return (
            f"LLM_PROVIDER is '{provider}' but LLM_API_KEY is not set to a real key. "
            "Nothing was sent anywhere."
        )
    return None


def consent_problem() -> Optional[str]:
    """Return None only if the owner has allowed sending to a provider, else why nothing will be sent."""
    if settings.ALLOW_SENDING_CODE_TO_PROVIDER is True:
        return None
    provider = (settings.LLM_PROVIDER or "").strip().lower()
    return (
        f"Sending your question to the '{provider}' AI provider is turned off (ALLOW_SENDING_CODE_TO_PROVIDER is "
        "false), so nothing was sent anywhere and your files were not read. To allow it, set "
        "ALLOW_SENDING_CODE_TO_PROVIDER=true in the backend's environment and restart the backend."
    )


def send_blocker() -> Optional[str]:
    """Why nothing may be sent right now (configuration first, then consent), or None if sending is allowed."""
    return llm_config_problem() or consent_problem()


def provider_status() -> Dict[str, Any]:
    """What the chat can do right now. Contains no key, and nothing that identifies a project."""
    config_problem = llm_config_problem()
    consent = settings.ALLOW_SENDING_CODE_TO_PROVIDER is True
    configured = config_problem is None
    return {
        "provider": (settings.LLM_PROVIDER or "").strip().lower() or "mock",
        "model": settings.LLM_MODEL if configured else None,
        "configured": configured,
        "consent": consent,
        "can_send": configured and consent,
        "reason": config_problem or consent_problem(),
    }


async def call_external_llm(system: str, user: str, max_tokens: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Send one prepared request to the configured provider and return its JSON reply.

    Raises LLMCallError if the provider cannot be reached or does not answer with JSON; never falls back silently. This
    is the only function in the chat path that builds an HTTP client. It refuses to run unless the provider is
    configured AND the owner has given consent. `system` holds the rules, `user` holds the delimited excerpts and the
    question; nothing else (no earlier message) is ever added.
    """
    if llm_config_problem():
        raise LLMCallError("No supported provider is configured.")
    if consent_problem():
        raise ConsentError("Sending to the provider is switched off.")
    provider = settings.LLM_PROVIDER.strip().lower()
    api_key = settings.LLM_API_KEY
    model = settings.LLM_MODEL

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if provider in ("openai", "groq"):
                base_url = "https://api.openai.com/v1" if provider == "openai" else "https://api.groq.com/openai/v1"
                body: Dict[str, Any] = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                }
                if max_tokens:
                    body["max_tokens" if provider == "groq" else "max_completion_tokens"] = max_tokens
                if provider == "groq" and "gpt-oss" in (model or ""):
                    body["reasoning_effort"] = "low"  # these models think before answering; keep that cheap
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                retries, lenient = 0, False
                while True:
                    res = await client.post(f"{base_url}/chat/completions", headers=headers, json=body)
                    if res.status_code == 200:
                        raw_content = res.json()["choices"][0]["message"]["content"]
                        return _loads_lenient(raw_content)
                    if res.status_code == 429 and retries < MAX_RATE_LIMIT_RETRIES:
                        wait = _retry_wait(res)
                        if wait is not None and wait <= MAX_RATE_LIMIT_WAIT_SECONDS:
                            retries += 1
                            await asyncio.sleep(wait + 0.5)
                            continue
                    if res.status_code == 400 and not lenient and _error_code(res) == "json_validate_failed":
                        lenient = True  # the model's JSON was rejected by the provider: ask once more without the strict mode
                        body.pop("response_format", None)
                        continue
                    detail = ""
                    if res.status_code == 429:
                        wait = _retry_wait(res)
                        detail = f"Rate limit reached; try again in about {int(wait) + 1}s." if wait is not None else "Rate limit reached; try again shortly."
                    elif _error_code(res):
                        detail = f"(code: {_error_code(res)})"
                    raise LLMCallError(f"{provider} answered HTTP {res.status_code}." + (f" {detail}" if detail else ""))

            elif provider == "gemini":
                # The key travels in a header, never in the URL, so it cannot end up in a logged or printed address.
                res = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
                    json={"contents": [{"parts": [{"text": f"{system}\n\n{user}\n\nRespond with valid JSON only."}]}]},
                )
                if res.status_code == 200:
                    text_resp = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                    cleaned = re.sub(r"^```json\s*", "", text_resp.strip())
                    cleaned = re.sub(r"\s*```$", "", cleaned)
                    return json.loads(cleaned)
                raise LLMCallError(f"{provider} answered HTTP {res.status_code}.")

    except LLMCallError:
        raise
    except Exception as e:
        # Only the exception type is logged or shown: httpx messages can contain the request URL.
        logger.warning("LLM request to %s failed: %s", provider, type(e).__name__)
        raise LLMCallError(f"{provider} request failed ({type(e).__name__}).") from None

    raise LLMCallError(f"{provider} is not supported.")

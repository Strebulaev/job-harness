"""Step 3.1: OpenRouter provider (httpx.MockTransport, offline)."""

from __future__ import annotations

import json
import logging

import httpx
import pytest
from pydantic import BaseModel

from jobharness.llm.openrouter_provider import (
    OpenRouterAuthError,
    OpenRouterError,
    OpenRouterProvider,
)
from jobharness.llm.provider import ProviderConfig
from jobharness.settings import Settings

KEY = "sk-or-SECRET-KEY-123"


class Out(BaseModel):
    answer: str


def _cfg(retries: int = 2) -> ProviderConfig:
    return ProviderConfig(
        model_ids={}, temperature={}, max_retries=retries, daily_token_budget=1000,
        redact_pii_in_logs=True,
    )


async def _nosleep(_: float) -> None:
    return None


def _provider(handler, retries: int = 2) -> OpenRouterProvider:  # type: ignore[no-untyped-def]
    return OpenRouterProvider(
        _cfg(retries), key_getter=lambda: KEY, transport=httpx.MockTransport(handler),
        sleep=_nosleep,
    )


def _ok(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}],
              "usage": {"prompt_tokens": 11, "completion_tokens": 7}},
    )


async def test_structured_call_sends_schema_and_preferences() -> None:
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers["Authorization"]
        seen["body"] = json.loads(req.content)
        return _ok('{"answer": "hi"}')

    p = _provider(handler)
    obj, meta = await p.generate_structured(
        purpose="t", model="m/x", system="s", user="u", schema=Out,
        temperature=0.0, max_tokens=50, prompt_version="v1",
    )
    assert isinstance(obj, Out) and obj.answer == "hi"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"]["properties"]["answer"]
    assert body["provider"]["require_parameters"] is True
    assert seen["auth"] == f"Bearer {KEY}"
    assert (meta.input_tokens, meta.output_tokens) == (11, 7)


async def test_validation_failure_retries_with_feedback() -> None:
    bodies: list[dict[str, object]] = []
    replies = iter(['{"wrong": 1}', '{"answer": "ok"}'])

    def handler(req: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(req.content))
        return _ok(next(replies))

    obj, _ = await _provider(handler).generate_structured(
        purpose="t", model="m", system="s", user="u", schema=Out,
        temperature=0.0, max_tokens=50, prompt_version="v1",
    )
    assert isinstance(obj, Out) and len(bodies) == 2
    assert "failed validation" in json.dumps(bodies[1])


async def test_429_is_retried() -> None:
    n = {"c": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        n["c"] += 1
        return httpx.Response(429, json={"error": {"message": "slow"}}) if n["c"] < 3 else _ok("hello")

    text, _ = await _provider(handler).generate_text(
        purpose="t", model="m", system="s", user="u", temperature=0.0,
        max_tokens=10, prompt_version="v1",
    )
    assert text == "hello" and n["c"] == 3


async def test_401_raises_auth_error_without_key_in_message(caplog: pytest.LogCaptureFixture) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    p = _provider(handler)
    with caplog.at_level(logging.DEBUG), pytest.raises(OpenRouterAuthError) as ei:
        await p.generate_text(
            purpose="t", model="m", system="s", user="u", temperature=0.0,
            max_tokens=10, prompt_version="v1",
        )
    assert KEY not in str(ei.value)
    assert all(KEY not in r.getMessage() for r in caplog.records)
    assert await p.check_key() is False


async def test_unsupported_structured_output_error_is_clear() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "No endpoints found that support response_format"}})

    with pytest.raises(OpenRouterError, match="No endpoints"):
        await _provider(handler).generate_structured(
            purpose="t", model="m", system="s", user="u", schema=Out,
            temperature=0.0, max_tokens=50, prompt_version="v1",
        )


async def test_list_models_and_check_key() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "b/m2"}, {"id": "a/m1"}]})
        return httpx.Response(200, json={"data": {"label": "k"}})

    p = _provider(handler)
    assert await p.list_models() == ["a/m1", "b/m2"]
    assert await p.check_key() is True


async def test_missing_key_raises_auth_error() -> None:
    p = OpenRouterProvider(_cfg(), key_getter=lambda: None,
                           transport=httpx.MockTransport(lambda r: _ok("x")))
    with pytest.raises(OpenRouterAuthError):
        await p.list_models()


def test_settings_accepts_openrouter() -> None:
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[2]
    raw = yaml.safe_load((root / "config" / "config.example.yaml").read_text())
    raw["llm"]["provider"] = "openrouter"
    assert Settings.model_validate(raw).llm.provider == "openrouter"

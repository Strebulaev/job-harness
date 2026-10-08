"""OpenRouter provider (decision 0015).

OpenAI-compatible chat completions at ``https://openrouter.ai/api/v1``. The
API key comes from an injected getter (the encrypted secret store), never from
settings, and is never logged or placed in exception text.

UNVERIFIED against live OpenRouter (plan step 3.1): the ``provider``
preference keys (``require_parameters``, ``data_collection``) follow the
public docs as understood on 2026-10-08. Structured output is requested with
``response_format: json_schema`` and always re-validated with Pydantic, with
bounded retries that feed the validation error back to the model.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from jobharness.llm import log_llm_call
from jobharness.llm.hashing import request_hash
from jobharness.llm.provider import LLMCallMeta, ProviderConfig
from jobharness.llm.structured import StructuredOutputError, extract_json

BASE_URL = "https://openrouter.ai/api/v1"
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class OpenRouterError(RuntimeError):
    """An OpenRouter call failed. ``str(self)`` never contains the API key."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class OpenRouterAuthError(OpenRouterError):
    """The API key is missing or rejected (HTTP 401/403)."""


def _error_text(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        err = body.get("error", body) if isinstance(body, dict) else body
        if isinstance(err, dict):
            return str(err.get("message", err))[:300]
        return str(err)[:300]
    except ValueError:
        return resp.text[:300]


class OpenRouterProvider:
    def __init__(
        self,
        config: ProviderConfig,
        *,
        key_getter: Callable[[], str | None],
        transport: httpx.AsyncBaseTransport | None = None,
        data_collection: Literal["allow", "deny"] = "deny",
        strict_schema: bool = False,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        timeout: float = 120.0,
        app_title: str = "jobharness",
    ) -> None:
        self._cfg = config
        self._key_getter = key_getter
        self._transport = transport
        self._data_collection = data_collection
        self._strict = strict_schema
        self._sleep = sleep
        self._timeout = timeout
        self._app_title = app_title

    # ------------------------------------------------------------ plumbing
    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=BASE_URL, timeout=self._timeout, transport=self._transport
        )

    def _headers(self) -> dict[str, str]:
        key = self._key_getter()
        if not key:
            raise OpenRouterAuthError("OpenRouter key is not connected")
        return {
            "Authorization": f"Bearer {key}",
            "X-Title": self._app_title,
            "Content-Type": "application/json",
        }

    async def _request(
        self, method: str, path: str, json_body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = self._headers()
        last: OpenRouterError | None = None
        async with self._client() as client:
            for attempt in range(self._cfg.max_retries + 1):
                try:
                    resp = await client.request(method, path, headers=headers, json=json_body)
                except httpx.HTTPError as e:
                    last = OpenRouterError(f"network error: {type(e).__name__}")
                    await self._sleep(min(2**attempt, 8))
                    continue
                if resp.status_code in (401, 403):
                    raise OpenRouterAuthError(
                        f"key rejected ({resp.status_code})", resp.status_code
                    )
                if resp.status_code in _RETRY_STATUS:
                    last = OpenRouterError(
                        f"HTTP {resp.status_code}: {_error_text(resp)}", resp.status_code
                    )
                    await self._sleep(min(2**attempt, 8))
                    continue
                if resp.status_code >= 400:
                    raise OpenRouterError(
                        f"HTTP {resp.status_code}: {_error_text(resp)}", resp.status_code
                    )
                data = resp.json()
                if not isinstance(data, dict):
                    raise OpenRouterError("unexpected response shape")
                return data
        raise last or OpenRouterError("request failed")

    # ---------------------------------------------------------- management
    async def check_key(self) -> bool:
        """True when the key is accepted; False when rejected. Other errors raise."""
        try:
            await self._request("GET", "/key")
        except OpenRouterAuthError:
            return False
        return True

    async def list_models(self) -> list[str]:
        data = await self._request("GET", "/models")
        items = data.get("data", [])
        return sorted(str(m["id"]) for m in items if isinstance(m, dict) and "id" in m)

    # ------------------------------------------------------------- calls
    def _body(
        self,
        *,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        schema: type[BaseModel] | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "provider": {
                "require_parameters": schema is not None,
                "data_collection": self._data_collection,
            },
        }
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": self._strict,
                    "schema": schema.model_json_schema(),
                },
            }
        return body

    def _meta(
        self,
        *,
        model: str,
        prompt_version: str,
        system: str,
        user: str,
        temperature: float,
        schema_name: str | None,
        usage: dict[str, Any],
        latency_ms: int,
    ) -> LLMCallMeta:
        return LLMCallMeta(
            model=model,
            prompt_version=prompt_version,
            request_hash=request_hash(
                model=model,
                prompt_version=prompt_version,
                system=system,
                user=user,
                temperature=temperature,
                schema_name=schema_name,
            ),
            input_tokens=int(usage.get("prompt_tokens", 0) or 0),
            output_tokens=int(usage.get("completion_tokens", 0) or 0),
            latency_ms=latency_ms,
            cost_usd=float(usage.get("cost", 0.0) or 0.0),
            ok=True,
        )

    @staticmethod
    def _content(data: dict[str, Any]) -> str:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise OpenRouterError("response has no message content") from e
        return str(content or "")

    async def generate_structured(
        self,
        *,
        purpose: str,
        model: str,
        system: str,
        user: str,
        schema: type[BaseModel],
        temperature: float,
        max_tokens: int,
        prompt_version: str,
        request_tags: dict[str, str] | None = None,
    ) -> tuple[BaseModel, LLMCallMeta]:
        last_err: Exception | None = None
        current_user = user
        for _attempt in range(self._cfg.max_retries + 1):
            t0 = time.monotonic()
            data = await self._request(
                "POST",
                "/chat/completions",
                self._body(
                    model=model,
                    system=system,
                    user=current_user,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    schema=schema,
                ),
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            try:
                validated = schema.model_validate(extract_json(self._content(data)))
            except (StructuredOutputError, ValueError) as e:
                last_err = e
                current_user = (
                    f"{user}\n\nPrevious response failed validation: {e}\n"
                    "Retry with valid JSON only."
                )
                continue
            meta = self._meta(
                model=model,
                prompt_version=prompt_version,
                system=system,
                user=user,
                temperature=temperature,
                schema_name=schema.__name__,
                usage=data.get("usage") or {},
                latency_ms=latency_ms,
            )
            log_llm_call(purpose, meta)
            return validated, meta
        err = f"OpenRouter structured output failed validation: {last_err}"
        fail = self._meta(
            model=model,
            prompt_version=prompt_version,
            system=system,
            user=user,
            temperature=temperature,
            schema_name=schema.__name__,
            usage={},
            latency_ms=0,
        )
        log_llm_call(purpose, fail, error=err)
        raise OpenRouterError(err)

    async def generate_text(
        self,
        *,
        purpose: str,
        model: str,
        system: str,
        user: str,
        temperature: float,
        max_tokens: int,
        prompt_version: str,
        request_tags: dict[str, str] | None = None,
    ) -> tuple[str, LLMCallMeta]:
        t0 = time.monotonic()
        data = await self._request(
            "POST",
            "/chat/completions",
            self._body(
                model=model,
                system=system,
                user=user,
                temperature=temperature,
                max_tokens=max_tokens,
                schema=None,
            ),
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        meta = self._meta(
            model=model,
            prompt_version=prompt_version,
            system=system,
            user=user,
            temperature=temperature,
            schema_name=None,
            usage=data.get("usage") or {},
            latency_ms=latency_ms,
        )
        log_llm_call(purpose, meta)
        return self._content(data), meta


__all__ = ["BASE_URL", "OpenRouterAuthError", "OpenRouterError", "OpenRouterProvider"]

"""Thin Anthropic SDK wrapper (spec §12).

Model ids come from config, never hard-coded. Structured output uses the
provider's tool-use mechanism where available; the result is always validated
with Pydantic. Bounded retries with error feedback on parse/validation failure.
"""

from __future__ import annotations

import os
import time
from typing import Any

from pydantic import BaseModel

from jobharness.llm import log_llm_call
from jobharness.llm.hashing import request_hash
from jobharness.llm.provider import LLMCallMeta, ProviderConfig
from jobharness.llm.structured import StructuredOutputError, extract_json


class AnthropicKeyError(Exception):
    """Raised when the Anthropic API key is not present in the environment."""


class AnthropicProvider:
    """Async Anthropic provider. Raises :class:`AnthropicKeyError` when the
    ``ANTHROPIC_API_KEY`` env var is missing."""

    def __init__(self, config: ProviderConfig) -> None:
        if not config.api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            raise AnthropicKeyError(
                "ANTHROPIC_API_KEY not set — export it or use provider: fake"
            )
        self._cfg = config
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._cfg.api_key)
        return self._client

    def _log_failure(
        self,
        purpose: str,
        model: str,
        prompt_version: str,
        system: str,
        user: str,
        temperature: float,
        schema_name: str | None,
        error: str,
    ) -> None:
        meta = self._meta(
            model=model,
            prompt_version=prompt_version,
            system=system,
            user=user,
            temperature=temperature,
            schema_name=schema_name,
            usage=None,
            latency_ms=0,
            cost_usd=0.0,
        )
        log_llm_call(purpose, meta, error=error)

    def _meta(
        self,
        *,
        model: str,
        prompt_version: str,
        system: str,
        user: str,
        temperature: float,
        schema_name: str | None,
        usage: Any,
        latency_ms: int,
        cost_usd: float,
    ) -> LLMCallMeta:
        rh = request_hash(
            model=model,
            prompt_version=prompt_version,
            system=system,
            user=user,
            temperature=temperature,
            schema_name=schema_name,
        )
        return LLMCallMeta(
            model=model,
            prompt_version=prompt_version,
            request_hash=rh,
            input_tokens=getattr(usage, "input_tokens", 0) if usage else 0,
            output_tokens=getattr(usage, "output_tokens", 0) if usage else 0,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            ok=True,
        )

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
        client = self._ensure_client()
        last_err: Exception | None = None
        for _attempt in range(self._cfg.max_retries + 1):
            t0 = time.monotonic()
            resp = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            raw_text = "".join(
                block.text for block in resp.content if hasattr(block, "text")
            )
            try:
                obj = extract_json(raw_text)
                validated = schema.model_validate(obj)
            except (StructuredOutputError, ValueError) as e:
                last_err = e
                # bounded retry with the validation error appended
                user = f"{user}\n\nPrevious response failed validation: {e}\nRetry with valid JSON."
                continue
            meta = self._meta(
                model=model,
                prompt_version=prompt_version,
                system=system,
                user=user,
                temperature=temperature,
                schema_name=schema.__name__,
                usage=getattr(resp, "usage", None),
                latency_ms=latency_ms,
                cost_usd=0.0,  # cost tracking is wired in M5
            )
            log_llm_call(purpose, meta)
            return validated, meta
        err = (
            f"Anthropic structured output failed after "
            f"{self._cfg.max_retries + 1} attempts: {last_err}"
        )
        self._log_failure(
            purpose, model, prompt_version, system, user, temperature, schema.__name__, err
        )
        raise RuntimeError(err)

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
        client = self._ensure_client()
        t0 = time.monotonic()
        resp = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        text = "".join(
            block.text for block in resp.content if hasattr(block, "text")
        )
        meta = self._meta(
            model=model,
            prompt_version=prompt_version,
            system=system,
            user=user,
            temperature=temperature,
            schema_name=None,
            usage=getattr(resp, "usage", None),
            latency_ms=latency_ms,
            cost_usd=0.0,
        )
        log_llm_call(purpose, meta)
        return text, meta

"""LLM provider protocol + metadata (spec §12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass(slots=True)
class LLMCallMeta:
    model: str
    prompt_version: str
    request_hash: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
    ok: bool = True
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


# A schema is a Pydantic model class; the provider returns an instance of it.
Schema = type[BaseModel]


@runtime_checkable
class LLMProvider(Protocol):
    """Async provider interface. Every call MUST be logged to ``llm_calls``."""

    async def generate_structured(
        self,
        *,
        purpose: str,
        model: str,
        system: str,
        user: str,
        schema: Schema,
        temperature: float,
        max_tokens: int,
        prompt_version: str,
        request_tags: dict[str, str] | None = None,
    ) -> tuple[BaseModel, LLMCallMeta]: ...

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
    ) -> tuple[str, LLMCallMeta]: ...


@dataclass(slots=True)
class ProviderConfig:
    """What a provider needs to be constructed."""

    model_ids: dict[str, str]
    temperature: dict[str, float]
    max_retries: int
    daily_token_budget: int
    redact_pii_in_logs: bool
    api_key: str | None = None

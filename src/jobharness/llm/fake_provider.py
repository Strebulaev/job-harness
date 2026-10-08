"""FakeProvider — deterministic, offline LLM provider for tests (spec §12).

Fixtures live in ``tests/fixtures/llm/`` keyed by ``request_hash``. Two
JSON files per hash:

- ``<hash>.text.json``  -> ``{"text": "..."}`` for ``generate_text``
- ``<hash>.json``       -> the JSON object the structured output must validate
  against, plus optional ``{"meta": {...}}`` for token/latency/cost.

The whole test suite MUST run offline with this provider.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from jobharness.llm import log_llm_call
from jobharness.llm.hashing import request_hash
from jobharness.llm.provider import LLMCallMeta


class NoFixtureError(KeyError):
    """Raised when no fixture matches the request hash."""


class FakeProvider:
    """Returns deterministic outputs from fixtures keyed by ``request_hash``."""

    def __init__(self, fixtures_dir: str | Path = "tests/fixtures/llm") -> None:
        self._dir = Path(fixtures_dir)

    def _load(self, request_hash_: str, suffix: str) -> dict[str, Any]:
        path = self._dir / f"{request_hash_}{suffix}.json"
        if not path.exists():
            raise NoFixtureError(f"no fixture at {path}")
        with path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)
        return data

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
        rh = request_hash(
            model=model,
            prompt_version=prompt_version,
            system=system,
            user=user,
            temperature=temperature,
            schema_name=schema.__name__,
        )
        data = self._load(rh, suffix="")
        meta = data.get("meta", {})
        obj = data.get("object", data)  # allow flat or nested
        validated = schema.model_validate(obj)
        # Defensive re-wrap: if the fixture passed validation but the schema
        # rejects re-validation of its own dump (should not happen), surface
        # it now rather than later in the post-check.
        schema.model_validate(validated.model_dump())
        meta_obj = LLMCallMeta(
            model=model,
            prompt_version=prompt_version,
            request_hash=rh,
            input_tokens=meta.get("input_tokens", 0),
            output_tokens=meta.get("output_tokens", 0),
            latency_ms=meta.get("latency_ms", 0),
            cost_usd=meta.get("cost_usd", 0.0),
            ok=True,
            raw=meta,
        )
        log_llm_call(purpose, meta_obj)
        return validated, meta_obj

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
        rh = request_hash(
            model=model,
            prompt_version=prompt_version,
            system=system,
            user=user,
            temperature=temperature,
        )
        data = self._load(rh, suffix=".text")
        meta = data.get("meta", {})
        text = data.get("text", "")
        meta_obj = LLMCallMeta(
            model=model,
            prompt_version=prompt_version,
            request_hash=rh,
            input_tokens=meta.get("input_tokens", 0),
            output_tokens=meta.get("output_tokens", 0),
            latency_ms=meta.get("latency_ms", 0),
            cost_usd=meta.get("cost_usd", 0.0),
            ok=True,
            raw=meta,
        )
        log_llm_call(purpose, meta_obj)
        return text, meta_obj

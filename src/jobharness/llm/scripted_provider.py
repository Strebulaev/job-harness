"""ScriptedProvider — an offline test double keyed by call ``purpose``.

Where :class:`FakeProvider` replays hash-keyed fixture files, this returns
whatever a per-purpose handler produces, so tests for composers, gates and the
pipeline need no fixture files. Handlers receive the call's keyword arguments.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from jobharness.llm.hashing import request_hash
from jobharness.llm.provider import LLMCallMeta

Handler = Callable[..., Any]


class NoHandlerError(KeyError):
    """No handler was registered for the purpose."""


class ScriptedProvider:
    def __init__(self, handlers: dict[str, Handler] | None = None) -> None:
        self.handlers: dict[str, Handler] = dict(handlers or {})
        self.calls: list[dict[str, Any]] = []

    def _meta(self, model: str, prompt_version: str, system: str, user: str,
              temperature: float, schema_name: str | None) -> LLMCallMeta:
        return LLMCallMeta(
            model=model,
            prompt_version=prompt_version,
            request_hash=request_hash(
                model=model, prompt_version=prompt_version, system=system,
                user=user, temperature=temperature, schema_name=schema_name,
            ),
            input_tokens=len(user) // 4,
            output_tokens=50,
            latency_ms=0,
            cost_usd=0.0,
        )

    def _handler(self, purpose: str) -> Handler:
        try:
            return self.handlers[purpose]
        except KeyError:
            raise NoHandlerError(f"no scripted handler for purpose {purpose!r}") from None

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
        self.calls.append({"purpose": purpose, "model": model, "user": user})
        out = self._handler(purpose)(system=system, user=user, schema=schema, model=model)
        obj = out if isinstance(out, BaseModel) else schema.model_validate(out)
        return obj, self._meta(model, prompt_version, system, user, temperature, schema.__name__)

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
        self.calls.append({"purpose": purpose, "model": model, "user": user})
        text = str(self._handler(purpose)(system=system, user=user, model=model))
        return text, self._meta(model, prompt_version, system, user, temperature, None)


__all__ = ["NoHandlerError", "ScriptedProvider"]

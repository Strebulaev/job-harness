"""M1-5 unit tests: FakeProvider, AnthropicProvider key error, llm_calls logging.

Fixtures live in ``tests/fixtures/llm/`` keyed by request_hash. The whole
suite MUST run offline with FakeProvider.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from jobharness.db.models import LLMCall
from jobharness.llm import log_llm_call
from jobharness.llm.anthropic_provider import AnthropicKeyError, AnthropicProvider
from jobharness.llm.fake_provider import FakeProvider, NoFixtureError
from jobharness.llm.provider import LLMCallMeta, ProviderConfig

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "llm"


class Echo(BaseModel):
    echo: str

@pytest.fixture()
def provider() -> FakeProvider:
    return FakeProvider(fixtures_dir=FIXTURES_DIR)


@pytest.fixture()
def db_engine(tmp_path) -> AsyncIterator[object]:
    import jobharness.db.session as s
    from jobharness.db.session import create_schema, init_session_factory, make_engine

    engine = make_engine(tmp_path / "test.db")
    create_schema(engine)
    factory = init_session_factory(engine)
    try:
        yield engine
    finally:
        del factory
        s._SessionLocal = None


def _structured_kwargs() -> dict:
    return {
        "purpose": "echo",
        "model": "fake-model",
        "system": "systext",
        "user": "usertext",
        "temperature": 0.0,
        "max_tokens": 100,
        "prompt_version": "v1",
    }


def _text_kwargs() -> dict:
    return {
        "purpose": "echo_text",
        "model": "fake-model",
        "system": "systext",
        "user": "usertext",
        "temperature": 0.0,
        "max_tokens": 100,
        "prompt_version": "v1",
    }


# ---------------------------------------------------------------- FakeProvider
async def test_fake_provider_generate_structured(provider, db_engine):
    obj, meta = await provider.generate_structured(schema=Echo, **_structured_kwargs())
    assert obj.echo == "usertext"
    assert meta.ok is True
    assert meta.request_hash
    assert meta.input_tokens == 10
    assert meta.output_tokens == 5
    assert meta.cost_usd == 0.0


async def test_fake_provider_generate_text(provider, db_engine):
    text, meta = await provider.generate_text(**_text_kwargs())
    assert text == "hello world"
    assert meta.ok is True
    assert meta.request_hash


async def test_fake_provider_missing_fixture_raises(provider):
    with pytest.raises(NoFixtureError):
        await provider.generate_structured(
            purpose="nope",
            model="fake-model",
            system="systext",
            user="unknown-user",
            schema=Echo,
            temperature=0.0,
            max_tokens=100,
            prompt_version="v1",
        )


# ---------------------------------------------------------------- llm_calls logging
async def test_fake_provider_logs_llm_call(provider, db_engine):
    from sqlalchemy import select

    from jobharness.db.session import get_session

    await provider.generate_structured(schema=Echo, **_structured_kwargs())
    factory = get_session()
    with factory() as session:
        rows = session.scalars(select(LLMCall).where(LLMCall.purpose == "echo")).all()
    assert len(rows) == 1
    assert rows[0].model == "fake-model"
    assert rows[0].ok is True
    assert rows[0].input_tokens == 10
    assert rows[0].prompt_version == "v1"


def test_log_llm_call_direct():
    meta = LLMCallMeta(
        model="m",
        prompt_version="v1",
        request_hash="h",
        input_tokens=1,
        output_tokens=2,
        latency_ms=3,
        cost_usd=0.0,
    )
    log_llm_call("unit_test", meta, error="boom")


def test_log_llm_call_uninitialized_session_does_not_raise():
    """A DB error in log_llm_call is swallowed (best-effort), never raised."""
    import jobharness.db.session as s

    s._SessionLocal = None
    meta = LLMCallMeta(
        model="m",
        prompt_version="v1",
        request_hash="h",
        input_tokens=1,
        output_tokens=2,
        latency_ms=3,
        cost_usd=0.0,
    )
    log_llm_call("swallowed", meta)


# ---------------------------------------------------------------- AnthropicProvider
def test_anthropic_provider_raises_without_api_key():
    cfg = ProviderConfig(
        model_ids={"parse": "m"},
        temperature={"parse": 0.0},
        max_retries=2,
        daily_token_budget=100000,
        redact_pii_in_logs=True,
        api_key=None,
    )
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        with pytest.raises(AnthropicKeyError, match="ANTHROPIC_API_KEY not set"):
            AnthropicProvider(cfg)


def test_anthropic_provider_accepts_env_key():
    cfg = ProviderConfig(
        model_ids={"parse": "m"},
        temperature={"parse": 0.0},
        max_retries=2,
        daily_token_budget=100000,
        redact_pii_in_logs=True,
        api_key=None,
    )
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
        p = AnthropicProvider(cfg)
        assert p is not None

"""Step 4.5: provider connection, key handling and model selection."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from jobharness.bot.testing import BotHarness, make_transport

OR_KEY = "sk-or-VERY-SECRET-123"
SJ_KEY = "sj-SECRET-456"


def _world(harness_ref: list[BotHarness], calls: list[tuple[str, int]], or_ok: bool = True):  # type: ignore[no-untyped-def]
    def openrouter(req: httpx.Request) -> httpx.Response:
        h = harness_ref[0]
        calls.append((req.url.path, len(h.messenger.deleted)))  # deleted-count at call time
        if not or_ok or req.headers.get("Authorization") != f"Bearer {OR_KEY}":
            return httpx.Response(401, json={"error": {"message": "bad key"}})
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "vendor/small"}, {"id": "vendor/strong"}]})
        return httpx.Response(200, json={"data": {"label": "ok"}})

    def superjob(req: httpx.Request) -> httpx.Response:
        if req.headers.get("X-Api-App-Id") != SJ_KEY:
            return httpx.Response(401)
        return httpx.Response(200, json={"objects": [], "more": False})

    return make_transport({"openrouter.ai": openrouter, "api.superjob.ru": superjob})


def _harness(tmp_path: Path, repo_root: Path, or_ok: bool = True):  # type: ignore[no-untyped-def]
    ref: list[BotHarness] = []
    calls: list[tuple[str, int]] = []
    h = BotHarness(tmp_path, repo_root, transport=_world(ref, calls, or_ok))
    ref.append(h)
    return h, calls


async def test_key_message_deleted_before_provider_call_and_stored_encrypted(
    tmp_path: Path, repo_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    h, calls = _harness(tmp_path, repo_root)
    with caplog.at_level(logging.DEBUG):
        await h.say("/connect openrouter")
        out = await h.say(OR_KEY)
    assert "connected" in out[0] and OR_KEY not in " ".join(h.messenger.texts())
    assert h.messenger.deleted, "the key message must be deleted"
    assert calls and calls[0][1] >= 1, "deletion must precede the first provider call"
    assert h.services.secrets.get("openrouter_api_key") == OR_KEY
    assert all(OR_KEY not in r.getMessage() for r in caplog.records)
    # the key never lands in wizard state or the database in clear
    assert OR_KEY not in json.dumps(h.services.state.get("wizard:active"))
    from jobharness.db.models import BotState, Secret

    with h.session_factory() as s:
        assert all(OR_KEY.encode() not in row.ciphertext for row in s.query(Secret))
        assert all(OR_KEY not in row.value_json for row in s.query(BotState))


async def test_rejected_key_stores_nothing(tmp_path: Path, repo_root: Path) -> None:
    h, _ = _harness(tmp_path, repo_root, or_ok=False)
    await h.say("/connect openrouter")
    out = await h.say(OR_KEY)
    assert "not connected" in out[0] and OR_KEY not in out[0]
    assert h.services.secrets.get("openrouter_api_key") is None


async def test_superjob_connect_disconnect_and_status(tmp_path: Path, repo_root: Path) -> None:
    h, _ = _harness(tmp_path, repo_root)
    await h.script("/connect superjob", SJ_KEY)
    assert h.services.secrets.get("superjob_api_key") == SJ_KEY
    assert "superjob: connected" in (await h.say("/providers"))[0]
    assert "disconnected" in (await h.say("/disconnect superjob"))[0]
    assert h.services.secrets.get("superjob_api_key") is None


async def test_models_validated_against_openrouter_list(tmp_path: Path, repo_root: Path) -> None:
    h, _ = _harness(tmp_path, repo_root)
    await h.script("/connect openrouter", OR_KEY)
    assert "not on OpenRouter" in (await h.say("/models set compose nope/model"))[0]
    assert "Role must be" in (await h.say("/models set poet vendor/strong"))[0]
    assert "set to" in (await h.say("/models set compose vendor/strong"))[0]
    listing = (await h.say("/models"))[0]
    assert "compose: vendor/strong" in listing and "parse: <model-id-small>" in listing


async def test_models_requires_connected_key(tmp_path: Path, repo_root: Path) -> None:
    h, _ = _harness(tmp_path, repo_root)
    assert "Connect OpenRouter first" in (await h.say("/models set compose vendor/strong"))[0]

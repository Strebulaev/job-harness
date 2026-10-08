"""Step 6.1: the whole user story, offline.

Open the bot, fill in the profile, set preferences, connect providers, pick
models, add a feed, start the search, and receive documents in chat.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from jobharness.bot.testing import (
    FEED_URL,
    BotHarness,
    golden_feed,
    golden_provider,
    make_transport,
)
from jobharness.render.typst_renderer import typst_available

OR_KEY = "sk-or-E2E-SECRET-KEY"
SJ_KEY = "sj-E2E-SECRET-KEY"
NAMES = ["g01_rag_remote_ok", "g03_employee_rejected"]
OWNER_ONLY_PROBE = 777

PROFILE = [
    "/profile_start",
    "Jane A. Doe", "jane@example.com", "/skip", "Kyiv", "UA", "Europe/Kiev",
    "English C1, Russian native", "/skip", "/skip",
    "Backend & AI/LLM engineer with 12 years across SaaS, fintech, and data platforms.",
    "backend, ai",
    "Acme Corp", "CTO", "2019-03", "2024-08", "full_time",
    "B2B SaaS company (~300 employees)", "CTO (hands-on, backend & ML)",
    "Built RAG pipeline over internal docs; reduced support ticket volume by 25%.",
    "ai, rag, evals", "hands_on", "support_ticket_reduction=0.25", "support analytics export", "yes",
    "Designed event-driven ingestion pipeline handling 2M req/day.",
    "backend, performance, python", "hands_on", "/skip", "no",
    "Python:expert:12, SQL:expert:11, RAG:working:3",
    "yes", "/skip",
]
PREFS = [
    "/preferences", "2000", "4000", "15", "30", "Europe/Kiev", "09:00-18:00",
    "/skip", "/skip", "contractor, b2b, freelance, project", "anonymized",
    "handson_descriptor", "60",
]


def _transport(repo_root: Path, calls: list[str]) -> httpx.MockTransport:
    feed = golden_feed(repo_root, NAMES)

    def openrouter(req: httpx.Request) -> httpx.Response:
        calls.append(f"openrouter {req.url.path}")
        if req.headers.get("Authorization") != f"Bearer {OR_KEY}":
            return httpx.Response(401, json={"error": {"message": "bad key"}})
        if req.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "vendor/small"}, {"id": "vendor/strong"}]})
        return httpx.Response(200, json={"data": {"label": "ok"}})

    def superjob(req: httpx.Request) -> httpx.Response:
        calls.append("superjob")
        if req.headers.get("X-Api-App-Id") != SJ_KEY:
            return httpx.Response(401)
        return httpx.Response(200, json={"objects": [], "total": 0, "more": False})

    return make_transport({
        "openrouter.ai": openrouter,
        "api.superjob.ru": superjob,
        "feeds.example.com": lambda r: httpx.Response(200, text=feed),
    })


async def test_whole_flow(tmp_path: Path, repo_root: Path, caplog: pytest.LogCaptureFixture) -> None:
    calls: list[str] = []
    h = BotHarness(
        tmp_path, repo_root, provider=golden_provider(repo_root, NAMES),
        transport=_transport(repo_root, calls),
    )
    with caplog.at_level(logging.DEBUG):
        assert "Setup, in order" in (await h.say("/start"))[0]
        await h.script(*PROFILE)
        assert (h.data_dir / "profile.yaml").exists(), h.messenger.texts()[-3:]
        assert "Preferences saved" in (await h.script(*PREFS))[-1]

        await h.script("/connect openrouter", OR_KEY)
        for role, model in (("parse", "vendor/small"), ("classify", "vendor/small"),
                            ("compose", "vendor/strong"), ("judge", "vendor/strong")):
            assert "set to" in (await h.say(f"/models set {role} {model}"))[0]
        await h.script("/connect superjob", SJ_KEY)
        await h.script(f"/feed_add {FEED_URL} Test feed", "yes")

        out = await h.say("/run")
        assert "Search started" in out[0]

    # documents arrived in chat: message with link, resume file, cover letter
    texts = h.messenger.texts()
    assert any("https://remoteok.com/1234567" in t for t in texts)
    assert not any("careers.acme-corp.example" in t for t in texts)  # rejected job not delivered
    docs = h.messenger.documents()
    assert len(docs) == 1 and docs[0].path is not None and docs[0].path.exists()
    if typst_available():
        assert docs[0].path.suffix == ".pdf"
    assert any("Dear Hiring Team" in t and "Jane A. Doe" in t for t in texts)
    assert "Search: active" in (await h.say("/status"))[0]

    # employers are anonymized in what was sent (positioning), real name never leaks
    visible = texts + ([docs[0].path.read_text()] if docs[0].path.suffix == ".txt" else [])
    assert "Acme Corp" not in " ".join(visible)

    # owner-only
    sent_before = len(h.messenger.sent)
    assert await h.say("/status", user_id=OWNER_ONLY_PROBE) == []
    assert len(h.messenger.sent) == sent_before

    # no secret anywhere: chat, logs, database
    blob = json.dumps(h.messenger.texts()) + " ".join(r.getMessage() for r in caplog.records)
    for secret in (OR_KEY, SJ_KEY):
        assert secret not in blob
    assert len(h.messenger.deleted) >= 2  # both key messages were deleted

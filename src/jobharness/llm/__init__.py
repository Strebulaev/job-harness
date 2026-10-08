"""Shared LLM-call logging (spec §12: "Log every call to ``llm_calls``").

The provider does not own a session: it logs through this helper, which
opens a short transaction on the globally initialized session factory.
"""

from __future__ import annotations

import logging

from jobharness.db.models import LLMCall
from jobharness.db.session import get_session
from jobharness.llm.provider import LLMCallMeta

_log = logging.getLogger(__name__)


def log_llm_call(purpose: str, meta: LLMCallMeta, error: str | None = None) -> None:
    """Insert one ``llm_calls`` row.

    Best-effort: a DB failure here is logged, never raised — the LLM call's
    result must not be lost because the log write failed.
    """
    session = None
    try:
        factory = get_session()
        session = factory()
        row = LLMCall(
            purpose=purpose,
            model=meta.model,
            prompt_version=meta.prompt_version,
            input_tokens=meta.input_tokens,
            output_tokens=meta.output_tokens,
            latency_ms=meta.latency_ms,
            cost_usd=meta.cost_usd,
            request_hash=meta.request_hash,
            ok=meta.ok,
            error=error or meta.error,
        )
        session.add(row)
        session.commit()
    except Exception:
        if session is not None:
            session.rollback()
        _log.exception("failed to write llm_calls row for purpose=%s", purpose)
    finally:
        if session is not None:
            session.close()

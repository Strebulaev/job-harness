"""Request hashing — stable, canonical, and cheap.

The hash covers everything that affects the LLM's output: model, prompt
version, system+user text, temperature, and the schema name. Two calls with
identical inputs produce identical hashes; any change changes the hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _canonical(value: Any) -> str:
    """Serialize ``value`` to a canonical JSON string (sorted keys, no extra
    whitespace) suitable for hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def request_hash(
    *,
    model: str,
    prompt_version: str,
    system: str,
    user: str,
    temperature: float,
    schema_name: str | None = None,
) -> str:
    """Return the hex SHA-256 of the canonicalized request parameters.

    Used to key FakeProvider fixtures and to log ``llm_calls.request_hash``.
    """
    payload = {
        "model": model,
        "prompt_version": prompt_version,
        "system": system,
        "user": user,
        "temperature": temperature,
        "schema": schema_name,
    }
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()

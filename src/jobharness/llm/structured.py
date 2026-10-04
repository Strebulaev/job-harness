"""Structured-output helpers: strip code fences, coerce JSON, bounded retry.

The LLM is instructed to return JSON only, but in practice it sometimes wraps
the JSON in a code fence or adds prose. :func:`extract_json` is tolerant of
both; it raises :class:`StructuredOutputError` when no parseable JSON object
is found.
"""

from __future__ import annotations

import json
import re
from typing import Any


class StructuredOutputError(Exception):
    """Raised when the LLM output cannot be parsed into a JSON object."""

    def __init__(self, message: str, raw: str | None = None) -> None:
        super().__init__(message)
        self.raw = raw


_FENCE_RE = re.compile(
    r"```(?:json|javascript|js)?\s*\n?(.*?)\n?```",
    re.DOTALL | re.IGNORECASE,
)


def strip_code_fences(text: str) -> str:
    """Remove a single markdown code fence (and its language tag) if present."""
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def extract_json(text: str) -> dict[str, Any]:
    """Parse ``text`` into a JSON dict.

    Strategy: strip fences, try ``json.loads``; on failure, find the first
    ``{`` ... last ``}`` pair and retry. Raises :class:`StructuredOutputError`
    with the raw text attached so the caller can feed it back to the LLM.
    """
    candidate = strip_code_fences(text)

    def _parse(s: str) -> dict[str, Any]:
        parsed = json.loads(s)
        if not isinstance(parsed, dict):
            raise StructuredOutputError(
                f"top-level JSON must be an object, got {type(parsed).__name__}",
                raw=text,
            )
        return parsed

    try:
        return _parse(candidate)
    except json.JSONDecodeError as e:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise StructuredOutputError(
                f"no JSON object found: {e}", raw=text
            ) from e
        try:
            return _parse(candidate[start : end + 1])
        except json.JSONDecodeError as e2:
            raise StructuredOutputError(
                f"JSON object not parseable: {e2}", raw=text
            ) from e2

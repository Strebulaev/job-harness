"""Hashing + URL canonicalization + fuzzy similarity (spec §11.1 dedup).

- :func:`canonicalize_url` — lowercase host, drop default ports, trailing
  slash, fragments, and common tracking params (``utm_*``, ``ref``,
  ``source``). Returns the canonical form used for ``url_hash``.
- :func:`url_hash` — SHA-256 of the canonical URL.
- :func:`jd_raw_hash` — SHA-256 of the raw JD text (whitespace-normalized).
- :func:`fuzzy_similarity` — quick-ratio over the lowercased
  ``company + " " + title`` pair; the pipeline treats >= 0.92 as a duplicate.
"""

from __future__ import annotations

import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

#: Query params that are dropped during URL canonicalization.
_TRACKING_PARAMS = frozenset({
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "source",
    "fbclid",
    "gclid",
    "mkvid",
})


def canonicalize_url(url: str) -> str:
    """Return a canonical form of ``url`` for hashing.

    Lowercases the scheme+host, drops default ports (80/443), strips the
    fragment, removes trailing slash from the path, and drops tracking
    query params. The remaining query is sorted so that equivalent
    URLs with different param order hash the same.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    netloc = parts.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    # Drop tracking params; sort the rest for stability.
    query_pairs = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_pairs))
    return urlunsplit((scheme, netloc, path, query, ""))


def url_hash(url: str) -> str:
    """SHA-256 hex of the canonical URL."""
    return hashlib.sha256(canonicalize_url(url).encode("utf-8")).hexdigest()


def _norm_ws(s: str) -> str:
    return " ".join(s.lower().split())


def jd_raw_hash(jd_raw: str) -> str:
    """SHA-256 hex of the whitespace-normalized JD text."""
    return hashlib.sha256(_norm_ws(jd_raw).encode("utf-8")).hexdigest()


def _bigrams(s: str) -> set[str]:
    """Return the set of character bigrams in ``s``."""
    if len(s) < 2:
        return {s} if s else set()
    return {s[i : i + 2] for i in range(len(s) - 1)}


def fuzzy_similarity(a: str, b: str) -> float:
    """Return a 0..1 similarity between ``a`` and ``b``.

    Uses the Dice coefficient over character bigrams of the lowercased,
    whitespace-normalized strings. Two identical strings score 1.0;
    two strings with one character difference on a 30-char string
    score ~0.97. The pipeline treats a score >= 0.92 (combined with
    matching company+title) as a duplicate.
    """
    a = _norm_ws(a)
    b = _norm_ws(b)
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    ba = _bigrams(a)
    bb = _bigrams(b)
    intersection = len(ba & bb)
    total = len(ba) + len(bb)
    if total == 0:
        return 0.0
    return 2.0 * intersection / total


def company_title_key(company: str | None, title: str | None) -> str:
    """Build the dedup key for fuzzy matching."""
    c = (company or "").strip().lower()
    t = (title or "").strip().lower()
    return f"{c} :: {t}"


__all__ = [
    "canonicalize_url",
    "company_title_key",
    "fuzzy_similarity",
    "jd_raw_hash",
    "url_hash",
]

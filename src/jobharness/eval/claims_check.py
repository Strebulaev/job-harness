"""Numeric and entity support checks for gate G1b (spec §13.1).

A statement is *supported* when every number and every proper-noun-like token
it contains also appears in the facts it cites. The checks are deliberately
conservative: a rewording that introduces a new capitalized term or number is
flagged, which is the point.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jobharness.schemas.profile import Profile

_NUM_RE = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(bn|b|k|m|%|x)?(?!\w)", re.IGNORECASE)
_MULT = {"k": 1e3, "m": 1e6, "b": 1e9, "bn": 1e9}
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#.\-]*")
_SENT_END = re.compile(r"[.!?:;]\s*$")
#: Capitalized words that are never treated as entities.
_COMMON_CAPS = frozenset(
    [
        "i", "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "for", "with", "by",
        "from", "as", "is", "are", "was", "were", "it", "we", "my", "our", "their", "this",
        "that", "these", "those", "if", "so", "but", "not", "no", "yes", "dear", "hello", "hi",
        "regards", "sincerely", "thanks", "thank", "your", "you", "present", "earlier",
        "experience", "skills", "education",
    ]
)


@dataclass(frozen=True)
class Issue:
    kind: str  # "number" | "entity"
    token: str

    def __str__(self) -> str:
        return f"{self.kind}:{self.token}"


def numbers(text: str) -> set[float]:
    """Absolute numeric values in ``text`` (``2M`` -> 2e6, ``40%`` -> 40)."""
    out: set[float] = set()
    for m in _NUM_RE.finditer(text):
        raw = m.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        suffix = (m.group(2) or "").lower()
        out.add(round(value * _MULT.get(suffix, 1.0), 6))
    return out


def _norm(token: str) -> str:
    return re.sub(r"[^a-z0-9+#]", "", token.lower())


def entities(text: str) -> set[str]:
    """Normalized proper-noun-like tokens: capitalized mid-sentence, or with
    inner capitals / all caps anywhere (``RAG``, ``PostgreSQL``, ``VP``)."""
    found: set[str] = set()
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", text):
        words = _WORD_RE.findall(sentence)
        for i, w in enumerate(words):
            core = w.strip(".-")
            if len(core) < 2 and core != "C":
                continue
            low = core.lower()
            if low in _COMMON_CAPS:
                continue
            inner_caps = any(c.isupper() for c in core[1:])
            capitalized = core[0].isupper()
            if inner_caps or (capitalized and i > 0):
                found.add(_norm(core))
    found.discard("")
    return found


def _fact_tokens(texts: list[str]) -> set[str]:
    toks: set[str] = set()
    for t in texts:
        for w in _WORD_RE.findall(t):
            toks.add(_norm(w))
            for part in re.split(r"[.\-]", w):
                toks.add(_norm(part))
    return toks


def check_text(
    text: str,
    support_texts: list[str],
    extra_numbers: set[float] | None = None,
    entity_support: list[str] | None = None,
) -> list[Issue]:
    """Issues for numbers/entities in ``text`` absent from ``support_texts``.

    ``entity_support`` texts widen the allowed entities only (not numbers).
    """
    allowed_nums = set(extra_numbers or ())
    for t in support_texts:
        allowed_nums |= numbers(t)
    issues = [Issue("number", f"{n:g}") for n in sorted(numbers(text) - allowed_nums)]
    allowed_toks = _fact_tokens([*support_texts, *(entity_support or [])])
    issues += [Issue("entity", e) for e in sorted(entities(text) - allowed_toks)]
    return issues


@dataclass(frozen=True)
class FactInfo:
    text: str
    metric_numbers: frozenset[float] = frozenset()


def fact_index(profile: Profile) -> dict[str, FactInfo]:
    """Map every profile fact id to the text a claim may be checked against."""
    idx: dict[str, FactInfo] = {}
    for s in profile.summary_facts:
        idx[s.id] = FactInfo(s.text)
    for e in profile.experience:
        end = e.end or "present"
        opts = [e.employer_display_options.full, e.employer_display_options.anonymized or ""]
        titles = [e.title_display_options.exact, e.title_display_options.handson_descriptor or ""]
        idx[e.id] = FactInfo(
            f"{e.title_real} {e.employer_real} {' '.join(opts)} {' '.join(titles)} {e.start} {end}"
        )
        for b in e.bullets:
            idx[b.id] = _bullet_info(b.text, b.metrics)
    for ed in profile.education:
        idx[ed.id] = FactInfo(f"{ed.degree} {ed.field} {ed.institution} {ed.start} {ed.end or ''}")
    for c in profile.certifications:
        idx[c.id] = FactInfo(f"{c.name} {c.issuer} {c.date}")
    for p in profile.projects:
        idx[p.id] = FactInfo(f"{p.name} {p.summary or ''}")
        for b in p.bullets:
            idx[b.id] = _bullet_info(b.text, b.metrics)
    for sk in profile.skills:
        idx[sk.id] = FactInfo(f"{sk.name} {sk.level} {sk.years:g} years")
    return idx


def _bullet_info(text: str, metrics: list) -> FactInfo:  # type: ignore[type-arg]
    nums: set[float] = set()
    for m in metrics:
        v = abs(float(m.value))
        nums.add(round(v, 6))
        if v <= 1:
            nums.add(round(v * 100, 6))
    return FactInfo(text, frozenset(nums))


def check_claim(
    text: str,
    cited_ids: list[str],
    index: dict[str, FactInfo],
    entity_support: list[str] | None = None,
) -> list[Issue]:
    """Issues for a claim citing ``cited_ids``; unknown ids are an issue too."""
    unknown = [Issue("unknown_fact", i) for i in cited_ids if i not in index]
    infos = [index[i] for i in cited_ids if i in index]
    extra_nums: set[float] = set()
    for info in infos:
        extra_nums |= set(info.metric_numbers)
    return unknown + check_text(text, [i.text for i in infos], extra_nums, entity_support)


__all__ = [
    "FactInfo",
    "Issue",
    "check_claim",
    "check_text",
    "entities",
    "fact_index",
    "numbers",
]

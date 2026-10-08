"""Fact retrieval for resume composition (spec §11.4 steps 1-4).

Candidate facts -> positioning/archetype filter -> BM25 ranking against the JD
(+ archetype ``prefer_tags`` boost) -> per-role bullet cap -> skill selection.
Pure and deterministic: ``today`` is injected, ties break on profile order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from rank_bm25 import BM25Okapi

from jobharness.schemas.archetype import Archetype
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import Positioning
from jobharness.schemas.profile import Bullet, Experience, Profile, Project, Skill, SummaryFact

#: Roles ending within this many years of ``today`` use the ``recent`` bullet cap.
RECENT_YEARS = 3
#: Score added per archetype ``prefer_tags`` tag carried by a fact.
PREFER_TAG_BOOST = 0.5
MAX_SKILLS = 12
MAX_SUMMARY_FACTS = 3
MAX_PROJECTS = 2
MAX_BULLETS_PER_PROJECT = 2

_LEVEL_RANK = {"familiar": 0, "working": 1, "proficient": 2, "expert": 3}
#: Bullet kinds hidden by each ``leadership_visibility`` setting.
_HIDDEN_BY_VISIBILITY: dict[str, frozenset[str]] = {
    "none": frozenset({"leadership", "strategy", "budget"}),
    "minimal": frozenset({"strategy", "budget"}),
    "full": frozenset(),
}
_TOKEN = re.compile(r"[a-z0-9+#]+")


@dataclass(frozen=True)
class RankedBullet:
    bullet: Bullet
    score: float


@dataclass(frozen=True)
class SelectedRole:
    experience: Experience
    bullets: tuple[RankedBullet, ...]
    recent: bool


@dataclass(frozen=True)
class SelectedProject:
    project: Project
    bullets: tuple[RankedBullet, ...]


@dataclass(frozen=True)
class RetrievalResult:
    summary_facts: tuple[SummaryFact, ...]
    roles: tuple[SelectedRole, ...]
    earlier_roles: tuple[Experience, ...]
    projects: tuple[SelectedProject, ...]
    skills: tuple[Skill, ...]

    def fact_ids(self) -> set[str]:
        """Every fact id the composer may cite from this selection."""
        ids = {s.id for s in self.summary_facts}
        for role in self.roles:
            ids.add(role.experience.id)
            ids.update(b.bullet.id for b in role.bullets)
        for proj in self.projects:
            ids.add(proj.project.id)
            ids.update(b.bullet.id for b in proj.bullets)
        ids.update(s.id for s in self.skills)
        return ids


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _month(value: str) -> date:
    return date.fromisoformat(f"{value}-01")


def _years_before(today: date, years: int) -> date:
    return date(today.year - years, today.month, 1)


def _hidden_kinds(archetype: Archetype, positioning: Positioning) -> frozenset[str]:
    return (
        frozenset(archetype.fact_selection.suppress_kinds)
        | frozenset(positioning.suppress_kinds_default)
        | _HIDDEN_BY_VISIBILITY[positioning.leadership_visibility]
    )


def _query_tokens(jd: JDParsed) -> list[str]:
    out: list[str] = []
    for item in (*jd.must_have, *jd.tech_stack, *jd.responsibilities):
        out.extend(_tokens(item))
    return out


@dataclass(frozen=True)
class _Doc:
    fact_id: str
    text: str
    tags: tuple[str, ...]


def _score_docs(docs: list[_Doc], query: list[str], prefer_tags: set[str]) -> dict[str, float]:
    if not docs:
        return {}
    base = [0.0] * len(docs)
    if query:
        bm25 = BM25Okapi([_tokens(f"{d.text} {' '.join(d.tags)}") or ["_"] for d in docs])
        base = [float(x) for x in bm25.get_scores(query)]
    return {
        d.fact_id: base[i] + PREFER_TAG_BOOST * len(prefer_tags & set(d.tags))
        for i, d in enumerate(docs)
    }


def _rank(bullets: list[Bullet], scores: dict[str, float]) -> list[RankedBullet]:
    order = {b.id: i for i, b in enumerate(bullets)}
    ranked = sorted(bullets, key=lambda b: (-scores[b.id], order[b.id]))
    return [RankedBullet(bullet=b, score=scores[b.id]) for b in ranked]


def _matches(name: str, items: list[str]) -> bool:
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(name.lower())}(?![a-z0-9])")
    return any(pattern.search(item.lower()) for item in items)


def select_skills(profile: Profile, jd: JDParsed, archetype: Archetype) -> tuple[Skill, ...]:
    """JD-required skills first, then archetype/JD nice-to-have; cap at 12.

    Skills below ``working`` are never listed. A skill with no evidence is
    listed only when the JD requires it (spec §7 lint rule).
    """
    required = [*jd.must_have, *jd.tech_stack]
    nice = [*archetype.nice_to_have_keywords, *jd.nice_to_have]
    position = {s.id: i for i, s in enumerate(profile.skills)}

    def sort_key(s: Skill) -> tuple[int, float, int]:
        return (-_LEVEL_RANK[s.level], -s.years, position[s.id])

    eligible = [s for s in profile.skills if _LEVEL_RANK[s.level] >= _LEVEL_RANK["working"]]
    req = sorted((s for s in eligible if _matches(s.name, required)), key=sort_key)
    req_ids = {s.id for s in req}
    opt = sorted(
        (s for s in eligible if s.id not in req_ids and s.evidence_fact_ids
         and _matches(s.name, nice)),
        key=sort_key,
    )
    return tuple([*req, *opt][:MAX_SKILLS])


def retrieve_facts(
    profile: Profile,
    archetype: Archetype,
    positioning: Positioning,
    jd: JDParsed,
    *,
    today: date,
) -> RetrievalResult:
    """Select and rank the facts the composer may use for ``jd``."""
    hidden = _hidden_kinds(archetype, positioning)
    window_start = _years_before(today, positioning.recency_window_years)
    recent_start = _years_before(today, RECENT_YEARS)
    cap = archetype.fact_selection.max_bullets_per_role

    experiences = sorted(profile.experience, key=lambda e: _month(e.start), reverse=True)
    in_window = [e for e in experiences if e.end is None or _month(e.end) >= window_start]
    earlier = tuple(e for e in experiences if e not in in_window)

    kept: dict[str, list[Bullet]] = {
        e.id: [b for b in e.bullets if b.kind not in hidden] for e in in_window
    }
    proj_kept: dict[str, list[Bullet]] = {
        p.id: [b for b in p.bullets if b.kind not in hidden] for p in profile.projects
    }

    docs = [_Doc(s.id, s.text, tuple(s.tags)) for s in profile.summary_facts]
    docs += [_Doc(b.id, b.text, tuple(b.tags)) for bs in kept.values() for b in bs]
    docs += [_Doc(b.id, b.text, tuple(b.tags)) for bs in proj_kept.values() for b in bs]
    scores = _score_docs(docs, _query_tokens(jd), set(archetype.fact_selection.prefer_tags))

    summary_order = {s.id: i for i, s in enumerate(profile.summary_facts)}
    summary = tuple(
        sorted(profile.summary_facts, key=lambda s: (-scores[s.id], summary_order[s.id]))[
            :MAX_SUMMARY_FACTS
        ]
    )

    roles: list[SelectedRole] = []
    for e in in_window:
        is_recent = e.end is None or _month(e.end) >= recent_start
        limit = cap.recent if is_recent else cap.older
        roles.append(
            SelectedRole(
                experience=e,
                bullets=tuple(_rank(kept[e.id], scores)[:limit]),
                recent=is_recent,
            )
        )

    ranked_projects = [
        SelectedProject(
            project=p,
            bullets=tuple(_rank(proj_kept[p.id], scores)[:MAX_BULLETS_PER_PROJECT]),
        )
        for p in profile.projects
        if proj_kept[p.id]
    ]
    proj_order = {sp.project.id: i for i, sp in enumerate(ranked_projects)}
    projects = tuple(
        sorted(
            ranked_projects,
            key=lambda sp: (-sp.bullets[0].score, proj_order[sp.project.id]),
        )[:MAX_PROJECTS]
    )

    return RetrievalResult(
        summary_facts=summary,
        roles=tuple(roles),
        earlier_roles=earlier,
        projects=projects,
        skills=select_skills(profile, jd, archetype),
    )


__all__ = [
    "MAX_SKILLS",
    "PREFER_TAG_BOOST",
    "RECENT_YEARS",
    "RankedBullet",
    "RetrievalResult",
    "SelectedProject",
    "SelectedRole",
    "retrieve_facts",
    "select_skills",
]

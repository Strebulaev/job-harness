"""Prompt catalogue: name -> default version (docs/PROMPTS.md).

The prompt *files* live in ``jobharness/llm/prompts/<name>/v<N>.md`` (loaded
by :mod:`jobharness.llm.prompts`); this module only maps a prompt name to
its currently released version so the pipeline has one stable import.
"""

from __future__ import annotations

#: name -> default version (docs/PROMPTS.md catalogue).
PROMPT_DEFAULTS: dict[str, str] = {
    "jd_parse": "v1",
    "claims_extract": "v1",
    "claims_verify": "v1",
    "resume_compose": "v1",
    "cover_compose": "v1",
    "judge_resume": "v1",
    "judge_cover": "v1",
    "fit_sound_judge": "v1",
    "email_classify": "v1",
    "followup_draft": "v1",
    "interview_prep": "v1",
}


def default_version(name: str) -> str:
    try:
        return PROMPT_DEFAULTS[name]
    except KeyError:
        raise ValueError(f"prompt {name!r} has no default version") from None


__all__ = [
    "PROMPT_DEFAULTS",
    "default_version",
]

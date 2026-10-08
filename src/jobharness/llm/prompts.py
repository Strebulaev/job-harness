"""Prompt files: load, version, render (spec §12).

Prompt files live in ``jobharness/llm/prompts/<name>/v<N>.md`` with
YAML front-matter (``name``, ``version``, ``purpose``, ``schema``). Released
versions are immutable; changes create ``v<N+1>`` (docs/PROMPTS.md).
"""

from __future__ import annotations

import re
from importlib import resources
from typing import Any

_PROMPT_DIR = "prompts"
_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


class PromptNotFoundError(FileNotFoundError):
    """Raised when a prompt file or version does not exist."""


def _parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    m = _FRONT_MATTER_RE.match(text)
    if m is None:
        raise ValueError("prompt file has no YAML front-matter block")
    meta_lines = m.group(1)
    meta: dict[str, Any] = {}
    for line in meta_lines.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    body = text[m.end() :].lstrip("\n")
    return meta, body


def load_prompt(
    name: str, version: str = "v1", *, as_system: bool = False
) -> tuple[dict[str, Any], str]:
    """Load a prompt file. Returns ``(meta, body)``.

    ``meta`` contains at least ``name`` and ``version``. ``body`` is the
    prompt text after the front-matter.
    """
    try:
        ref = resources.files("jobharness.llm") / _PROMPT_DIR / name / f"{version}.md"
        text = ref.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, OSError) as e:
        raise PromptNotFoundError(
            f"prompt {name!r} version {version!r} not found under llm/prompts/"
        ) from e
    meta, body = _parse_front_matter(text)
    if meta.get("name") != name:
        raise ValueError(f"prompt front-matter name {meta.get('name')!r} != {name!r}")
    if "version" not in meta:
        raise ValueError(f"prompt {name!r} front-matter missing version")
    del as_system  # reserved for future use; system vs user split is caller-side
    return meta, body


def load_system_prompt(name: str, version: str = "v1") -> str:
    """Body of the prompt, used as the system message."""
    _, body = load_prompt(name, version)
    return body


__all__ = [
    "PromptNotFoundError",
    "load_prompt",
    "load_system_prompt",
]

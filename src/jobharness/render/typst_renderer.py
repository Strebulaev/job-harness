"""Typst renderer (decision 0012): ResumeContent -> PDF + .txt + .json.

Typst is installed in CI only (plan step 0.1); callers and tests check
:func:`typst_available`. The verification block is never written to any
output. UNVERIFIED against a real Typst binary at the time of writing.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from jobharness.schemas.documents import CoverLetter, ResumeContent


class RenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderedFiles:
    pdf: Path
    txt: Path
    json: Path


def typst_available(binary: str = "typst") -> bool:
    return shutil.which(binary) is not None


def resume_to_text(content: ResumeContent) -> str:
    """Plain-text rendering (also what the PDF text layer should contain)."""
    d = content.rendered()
    lines: list[str] = [d["header"]["full_name"], d["headline"]]
    contact = [d["header"]["email"], d["header"]["phone"], d["header"]["location"]]
    lines.append(" | ".join(c for c in contact if c))
    lines += [""] + list(d["summary"])
    lines += ["", "EXPERIENCE"]
    for e in d["experience"]:
        lines.append(f"{e['title_display']}, {e['employer_display']}")
        lines.append(f"{e['start']} - {e['end'] or 'Present'}")
        lines += [f"- {b['text']}" for b in e["bullets"]]
    if d["earlier_experience_line"]:
        lines.append(d["earlier_experience_line"])
    for p in d["projects"]:
        lines.append(f"Project: {p['name']}")
        lines += [f"- {b['text']}" for b in p["bullets"]]
    lines += ["", "EDUCATION"]
    for ed in d["education"]:
        lines.append(
            f"{ed['degree']}, {ed['field']}, {ed['institution']} "
            f"({ed['start']} - {ed['end'] or 'Present'})"
        )
    lines += [f"{c['name']}, {c['issuer']} ({c['date']})" for c in d["certifications"]]
    lines += ["", "SKILLS", ", ".join(d["skills_core"])]
    if d["languages"]:
        lines.append("Languages: " + ", ".join(f"{x['lang']} ({x['level']})" for x in d["languages"]))
    return "\n".join(lines) + "\n"


def render_resume(
    content: ResumeContent, out_dir: Path, stem: str, *, typst_bin: str = "typst",
    timeout: int = 60,
) -> RenderedFiles:
    if not typst_available(typst_bin):
        raise RenderError("typst binary not found on PATH")
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf, txt, js = (out_dir / f"{stem}.{x}" for x in ("pdf", "txt", "json"))
    data = json.dumps(content.rendered(), ensure_ascii=False, sort_keys=True, indent=2)
    template = resources.files("jobharness.render").joinpath("templates/resume.typ").read_text(
        encoding="utf-8"
    )
    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        (tdir / "resume.typ").write_text(template, encoding="utf-8")
        (tdir / "data.json").write_text(data, encoding="utf-8")
        env = {**os.environ, "SOURCE_DATE_EPOCH": "0"}
        try:
            proc = subprocess.run(
                [typst_bin, "compile", "--root", str(tdir), str(tdir / "resume.typ"), str(pdf)],
                capture_output=True, text=True, timeout=timeout, env=env, check=False,
            )
        except subprocess.TimeoutExpired as e:
            raise RenderError("typst timed out") from e
    if proc.returncode != 0:
        raise RenderError(f"typst failed: {proc.stderr.strip()[:400]}")
    txt.write_text(resume_to_text(content), encoding="utf-8")
    js.write_text(data + "\n", encoding="utf-8")
    return RenderedFiles(pdf=pdf, txt=txt, json=js)


def write_cover(letter: CoverLetter, out_dir: Path, stem: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{stem}.txt"
    path.write_text(letter.text + "\n", encoding="utf-8")
    return path


__all__ = [
    "RenderError",
    "RenderedFiles",
    "render_resume",
    "resume_to_text",
    "typst_available",
    "write_cover",
]

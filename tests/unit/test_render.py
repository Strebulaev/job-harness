"""Step 1.4: rendering. PDF assertions skip when `typst` is absent (CI has it)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from jobharness.compose.resume import compose_resume
from jobharness.llm.scripted_provider import ScriptedProvider
from jobharness.render.typst_renderer import (
    render_resume,
    resume_to_text,
    typst_available,
)
from jobharness.schemas.archetype import load_archetypes
from jobharness.schemas.jd import JDParsed
from jobharness.schemas.positioning import load_positioning
from jobharness.schemas.profile import load_profile

ROOT = Path(__file__).resolve().parents[2]
ARCHETYPES = load_archetypes(ROOT / "config" / "archetypes")
PROFILE = load_profile(str(ROOT / "config" / "profile.example.yaml"))
POSITIONING = load_positioning(ROOT / "config" / "positioning.example.yaml")


def _boom(**_: object) -> dict[str, object]:
    raise RuntimeError("offline")  # forces verbatim, always-truthful bullets


async def _content(archetype_id: str):  # type: ignore[no-untyped-def]
    res = await compose_resume(
        PROFILE, ARCHETYPES[archetype_id], POSITIONING, JDParsed(title="Engineer"),
        ScriptedProvider({"resume_compose": _boom}), model="m", today=date(2026, 10, 8),
    )
    return res.content


async def test_text_rendering_has_headings_in_order_and_hides_real_employer() -> None:
    content = await _content("a_ai_llm_engineer")
    text = resume_to_text(content)
    assert text.index("EXPERIENCE") < text.index("EDUCATION") < text.index("SKILLS")
    assert "Acme Corp" not in text  # anonymized by positioning


@pytest.mark.skipif(not typst_available(), reason="typst not installed (CI only)")
@pytest.mark.parametrize("archetype_id", sorted(ARCHETYPES))
async def test_pdf_has_headings_and_pages(archetype_id: str, tmp_path: Path) -> None:
    from pypdf import PdfReader

    content = await _content(archetype_id)
    files = render_resume(content, tmp_path, archetype_id)
    reader = PdfReader(str(files.pdf))
    assert 1 <= len(reader.pages) <= 2
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert text.index("EXPERIENCE") < text.index("EDUCATION") < text.index("SKILLS")
    assert files.txt.exists() and files.json.exists()
    assert "Acme Corp" not in files.json.read_text(encoding="utf-8")

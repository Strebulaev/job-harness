"""M2-3 integration test: ``jh parse run`` CLI end-to-end with FakeProvider.

Covers the done-when: ``jh parse run`` on the golden jobs produces valid
``JDParsed`` offline with FakeProvider, transitions jobs from ``new`` to
``parsed``, and stores the parsed JSON + model + prompt version.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from jobharness.cli import app
from jobharness.db.models import Base, Job
from jobharness.db.session import init_session_factory, make_engine
from jobharness.schemas.jd import JDParsed

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "eval_data" / "golden_jobs"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "llm"
CONFIG_EXAMPLE = REPO_ROOT / "config" / "config.example.yaml"


@pytest.fixture(autouse=True)
def db(tmp_path, monkeypatch):
    """Fresh SQLite DB + session factory + fake-provider env."""
    db_path = tmp_path / "data" / "jobharness.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(db_path)
    Base.metadata.create_all(engine)
    init_session_factory(engine)
    monkeypatch.setenv("JH_LLM_FIXTURES", str(FIXTURES_DIR))
    yield engine
    engine.dispose()


def _fake_config(tmp_path: Path, data_dir: Path) -> Path:
    """Write a config with provider=fake and data_dir pointing at the
    test DB's directory. The parse model id is set to ``fake-parse-v1``
    so the fixture hashes match."""
    src = CONFIG_EXAMPLE.read_text(encoding="utf-8")
    cfg = src.replace("provider: anthropic", "provider: fake")
    cfg = cfg.replace('parse: "<model-id-small>"', 'parse: "fake-parse-v1"')
    cfg = cfg.replace("data_dir: ./data", f"data_dir: {data_dir}")
    cfg = cfg.replace("output_dir: ./data/out", f"output_dir: {data_dir}/out")
    p = tmp_path / "config.yaml"
    p.write_text(cfg, encoding="utf-8")
    return p


def test_parse_run_cli_on_golden_jobs(db, tmp_path) -> None:
    """Insert 5 golden jobs with status=new; run ``jh parse run``; assert
    they transition to parsed and carry a valid jd_parsed_json."""
    from sqlalchemy import select

    from jobharness.db.session import get_session

    data_dir = tmp_path / "data"
    files = sorted(
        p for p in GOLDEN_DIR.glob("*.json") if p.stem not in ("expected_downgrades", "baseline")
    )
    with get_session()() as s:
        for p in files[:5]:
            data = json.loads(p.read_text(encoding="utf-8"))
            s.add(
                Job(
                    source=None,
                    url=data["url"],
                    jd_raw=data["jd_raw"],
                    status="new",
                )
            )
        s.commit()

    cfg = _fake_config(tmp_path, data_dir)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["parse", "run", "--limit", "5", "--config", str(cfg), "--json"],
        env={"JH_LLM_FIXTURES": str(FIXTURES_DIR)},
    )
    assert result.exit_code == 0, f"jh parse run failed: {result.output}\n{result.exception}"
    out = json.loads(result.output)
    assert out["ok"] is True
    assert out["parsed"] == 5
    assert out["failed"] == 0

    with get_session()() as s:
        jobs = list(s.execute(select(Job)).scalars())
        assert len(jobs) == 5
        for j in jobs:
            assert j.status == "parsed", f"job {j.id} status={j.status}"
            assert j.jd_parsed_json is not None
            parsed = JDParsed.model_validate(json.loads(j.jd_parsed_json))
            assert parsed.title
            assert j.parse_model is not None
            assert j.parse_prompt_version is not None
            # comp_confidence is set when compensation was normalized
            if j.comp_min_usd_month is not None:
                assert j.comp_confidence in ("high", "low")


def test_parse_run_cli_no_jobs(db, tmp_path) -> None:
    """``jh parse run`` with no jobs returns ok with 0 parsed."""
    cfg = _fake_config(tmp_path, tmp_path / "data")
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["parse", "run", "--limit", "5", "--config", str(cfg), "--json"],
        env={"JH_LLM_FIXTURES": str(FIXTURES_DIR)},
    )
    assert result.exit_code == 0
    out = json.loads(result.output)
    assert out["ok"] is True
    assert out["parsed"] == 0
    assert out["failed"] == 0

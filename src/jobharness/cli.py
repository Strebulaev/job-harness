"""jobharness CLI (Typer).

M1 commands: ``init``, ``doctor``, ``profile validate|lint|show``.
All commands: ``--json`` output option, non-zero exit on error, idempotent
where reasonable.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="jh",
    help="jobharness — local-first contractor job-search agent harness.",
    no_args_is_help=True,
)
console = Console()

profile_app = typer.Typer(help="Profile commands.")
app.add_typer(profile_app, name="profile")

parse_app = typer.Typer(help="JD parse commands.")
app.add_typer(parse_app, name="parse")

ingest_app = typer.Typer(help="Ingest commands.")
app.add_typer(ingest_app, name="ingest")

job_app = typer.Typer(help="Job commands.")
app.add_typer(job_app, name="job")

route_app = typer.Typer(help="Router commands.")
app.add_typer(route_app, name="route")

eval_app = typer.Typer(help="Eval commands.")
app.add_typer(eval_app, name="eval")

EXAMPLES = {
    "config/config.example.yaml": "config/config.yaml",
    "config/profile.example.yaml": "config/profile.yaml",
    "config/positioning.example.yaml": "config/positioning.yaml",
}


def _fail(msg: str, *, as_json: bool = False) -> None:
    if as_json:
        console.print_json(json.dumps({"ok": False, "error": msg}))
    else:
        console.print(f"[red]error:[/red] {msg}", style="bold")
    raise typer.Exit(code=1)


# ---------------------------------------------------------------- init
@app.command()
def init(
    data_dir: str = typer.Option("./data", help="data directory"),
    as_json: bool = typer.Option(False, "--json", help="JSON output"),
) -> None:
    """Create dirs, DB, copy example configs."""
    base = Path.cwd()
    for sub in (
        "data",
        "config",
        "eval_data/golden_jobs",
        "eval_data/golden_claims",
        "eval_data/golden_emails",
    ):
        (base / sub).mkdir(parents=True, exist_ok=True)

    for src, dst in EXAMPLES.items():
        s = base / src
        d = base / dst
        if s.exists() and not d.exists():
            shutil.copy(s, d)
            console.print(f"[green]copied[/green] {src} -> {dst}")

    # Run Alembic migrations to create the DB schema.
    import subprocess

    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=str(base),
    )
    if result.returncode != 0:
        _fail(f"alembic upgrade failed:\n{result.stderr}", as_json=as_json)
    console.print("[green]DB schema created via alembic[/green]")

    if as_json:
        console.print_json(json.dumps({"ok": True, "data_dir": data_dir}))


# ---------------------------------------------------------------- doctor
@app.command()
def doctor(as_json: bool = typer.Option(False, "--json", help="JSON output")) -> None:
    """Check config, DB, Typst binary, mailbox connectivity, LLM key presence."""
    checks: dict[str, dict[str, object]] = {}
    base = Path.cwd()

    # 1. config
    cfg_path = base / "config" / "config.yaml"
    if cfg_path.exists():
        from jobharness.settings import Settings

        try:
            Settings.from_yaml(cfg_path)
            checks["config"] = {"ok": True, "path": str(cfg_path)}
        except Exception as e:
            checks["config"] = {"ok": False, "error": str(e)}
    else:
        checks["config"] = {"ok": False, "error": "config/config.yaml not found (run `jh init`)"}

    # 2. DB
    db_path = base / "data" / "jobharness.db"
    checks["db"] = {"ok": db_path.exists(), "path": str(db_path)}

    # 3. Typst binary
    typst = shutil.which("typst")
    checks["typst"] = {"ok": typst is not None, "path": typst}

    # 4. LLM key (CLI mode only; the bot stores the OpenRouter key encrypted)
    import os

    checks["llm_key"] = {
        "ok": True,
        "note": "ANTHROPIC_API_KEY set"
        if os.environ.get("ANTHROPIC_API_KEY")
        else "not set (bot mode: connect OpenRouter in Telegram with /connect openrouter)",
    }

    # 5. Telegram bot environment (plan step 4.1 / 3.4)
    from jobharness.secrets.store import master_key_from_env, master_key_valid

    checks["telegram_bot_token"] = {
        "ok": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "error": None if os.environ.get("TELEGRAM_BOT_TOKEN") else "TELEGRAM_BOT_TOKEN is not set",
    }
    owner = os.environ.get("TELEGRAM_OWNER_ID", "")
    checks["telegram_owner_id"] = {
        "ok": owner.isdigit(),
        "error": None if owner.isdigit() else "TELEGRAM_OWNER_ID must be your numeric Telegram id",
    }
    mk = master_key_from_env()
    checks["master_key"] = {
        "ok": master_key_valid(mk),
        "error": None if master_key_valid(mk) else "JH_MASTER_KEY is missing or invalid "
        "(generate: python -c \"from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())\")",
    }

    all_ok = all(c["ok"] for c in checks.values() if c.get("ok") is not None)
    if as_json:
        console.print_json(json.dumps({"ok": all_ok, "checks": checks}))
        raise typer.Exit(code=0 if all_ok else 1)

    table = Table(title="jh doctor")
    table.add_column("check", style="bold")
    table.add_column("status")
    table.add_column("detail")
    for name, c in checks.items():
        status = "[green]ok[/green]" if c.get("ok") else "[red]fail[/red]"
        detail = str(c.get("error") or c.get("note") or c.get("path") or "")
        table.add_row(name, status, detail)
    console.print(table)
    raise typer.Exit(code=0 if all_ok else 1)


# ---------------------------------------------------------------- profile
@profile_app.command("validate")
def profile_validate(
    path: str = typer.Option("config/profile.yaml", help="profile.yaml path"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Validate the profile (fatal on error)."""
    from jobharness.schemas.profile import (
        ProfileValidationError,
        load_profile,
        validate_profile,
    )

    try:
        profile = load_profile(path)
        errors = validate_profile(profile)
    except ProfileValidationError as e:
        errors = e.errors
    except FileNotFoundError:
        _fail(f"profile not found: {path}", as_json=as_json)
        return
    except Exception as e:
        _fail(f"profile parse failed: {e}", as_json=as_json)
        return

    if errors:
        _fail("profile invalid:\n" + "\n".join(f"  - {e}" for e in errors), as_json=as_json)
        return
    if as_json:
        console.print_json(json.dumps({"ok": True, "path": path}))
    else:
        console.print(f"[green]profile valid[/green] ({path})")


@profile_app.command("lint")
def profile_lint(
    path: str = typer.Option("config/profile.yaml", help="profile.yaml path"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Lint the profile (warnings only, non-fatal)."""
    from jobharness.schemas.profile import lint_profile, load_profile

    try:
        profile = load_profile(path)
        warnings = lint_profile(profile)
    except FileNotFoundError:
        _fail(f"profile not found: {path}", as_json=as_json)
        return
    except Exception as e:
        _fail(f"profile parse failed: {e}", as_json=as_json)
        return

    if as_json:
        console.print_json(json.dumps({"ok": True, "warnings": warnings}))
    else:
        if not warnings:
            console.print("[green]no warnings[/green]")
        for w in warnings:
            console.print(f"[yellow]warn:[/yellow] {w}")


@profile_app.command("show")
def profile_show(
    path: str = typer.Option("config/profile.yaml", help="profile.yaml path"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Pretty-print the profile as JSON."""
    from jobharness.schemas.profile import load_profile

    try:
        profile = load_profile(path)
    except FileNotFoundError:
        _fail(f"profile not found: {path}", as_json=as_json)
        return
    except Exception as e:
        _fail(f"profile parse failed: {e}", as_json=as_json)
        return
    data = profile.model_dump(mode="json")
    if as_json:
        console.print_json(json.dumps(data))
    else:
        console.print_json(json.dumps(data, indent=2))


# ---------------------------------------------------------------- parse
@parse_app.command("run")
def parse_run(
    limit: int = typer.Option(10, help="max jobs to parse"),
    concurrency: int = typer.Option(4, help="concurrent LLM calls (spec §11.2)"),
    config: str = typer.Option("config/config.yaml", help="config path"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Parse jobs with status=new into ``jd_parsed_json`` (spec §11.2)."""
    import asyncio
    import os

    from sqlalchemy import select

    from jobharness.db.models import Job
    from jobharness.db.session import get_session, init_session_factory, make_engine
    from jobharness.llm.anthropic_provider import AnthropicProvider
    from jobharness.llm.fake_provider import FakeProvider
    from jobharness.llm.prompt_versions import default_version
    from jobharness.llm.provider import LLMProvider, ProviderConfig
    from jobharness.parse.jd_parser import parse_jd
    from jobharness.parse.normalizers import (
        UnknownCurrencyError,
        normalize_compensation,
    )
    from jobharness.settings import Settings

    cfg_path = Path(config)
    if not cfg_path.is_absolute():
        cfg_path = Path.cwd() / cfg_path
    if not cfg_path.exists():
        _fail(f"config not found: {config}", as_json=as_json)
        return
    try:
        settings: Settings = Settings.from_yaml(cfg_path)
    except Exception as e:
        _fail(f"config invalid: {e}", as_json=as_json)
        return

    # The DB lives at <data_dir>/jobharness.db; data_dir is relative to the
    # config file's directory when it's a relative path.
    data_dir = Path(settings.paths.data_dir)
    if not data_dir.is_absolute():
        data_dir = cfg_path.parent / data_dir
    db_path = data_dir / "jobharness.db"
    engine = make_engine(db_path)
    init_session_factory(engine)

    if settings.llm.provider == "fake":
        fixtures = os.environ.get("JH_LLM_FIXTURES", "tests/fixtures/llm")
        provider: LLMProvider = FakeProvider(fixtures_dir=fixtures)
    else:
        provider = AnthropicProvider(
            ProviderConfig(
                model_ids=settings.llm.models.model_dump(),
                temperature=settings.llm.temperature.model_dump(),
                max_retries=settings.llm.max_retries,
                daily_token_budget=settings.llm.daily_token_budget,
                redact_pii_in_logs=settings.llm.redact_pii_in_logs,
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
            )
        )

    model = settings.llm.models.parse
    temperature = settings.llm.temperature.parse

    with get_session()() as s:
        jobs: list[Job] = list(
            s.execute(select(Job).where(Job.status == "new").limit(limit))
            .scalars()
            .all()
        )
    if not jobs:
        if as_json:
            console.print_json(json.dumps({"ok": True, "parsed": 0, "failed": 0}))
        else:
            console.print("[yellow]no jobs with status=new[/yellow]")
        return

    def _mark_parse_failed(job: Job, reason: str) -> tuple[Job, bool, str]:
        with get_session()() as s:
            row = s.get(Job, job.id)
            assert row is not None
            row.status = "rejected"
            row.reject_reasons_json = json.dumps(["parse_failed: " + reason])
            s.commit()
        return job, False, f"parse_failed: {reason}"

    async def _one(job: Job) -> tuple[Job, bool, str]:
        try:
            result = await parse_jd(
                job.jd_raw or "", provider, model=model, temperature=temperature
            )
        except Exception as e:  # provider retries exhausted -> parse_failed
            return _mark_parse_failed(job, str(e))
        comp_confidence: str | None = None
        comp_min: float | None = None
        comp_max: float | None = None
        if result.parsed.compensation is not None:
            try:
                norm = normalize_compensation(
                    result.parsed.compensation,
                    settings,
                    hours_per_week=result.parsed.hours_per_week,
                )
            except UnknownCurrencyError as e:
                return _mark_parse_failed(job, str(e))
            comp_confidence = norm.confidence
            comp_min = norm.usd_min_month
            comp_max = norm.usd_max_month

        payload = json.dumps(result.parsed.model_dump(), sort_keys=True)
        with get_session()() as s:
            row = s.get(Job, job.id)
            assert row is not None
            row.jd_parsed_json = payload
            row.parse_model = model
            row.parse_prompt_version = default_version("jd_parse")
            row.engagement_type = result.parsed.engagement_type
            row.remote_policy = result.parsed.remote_policy
            row.exclusivity = (
                1
                if result.parsed.exclusivity == "required"
                else 0
                if result.parsed.exclusivity == "none"
                else None
            )
            row.ai_policy = result.parsed.ai_tools_policy
            row.subcontracting_policy = result.parsed.subcontracting_policy
            row.comp_confidence = comp_confidence
            row.comp_min_usd_month = comp_min
            row.comp_max_usd_month = comp_max
            if result.parsed.company:
                row.company = result.parsed.company
            if result.parsed.title:
                row.title = result.parsed.title
            row.status = "parsed"
            s.commit()
        return job, True, "ok"

    sem = asyncio.Semaphore(concurrency)

    async def _bounded(job: Job) -> tuple[Job, bool, str]:
        async with sem:
            return await _one(job)

    async def _all() -> list[tuple[Job, bool, str]]:
        return list(await asyncio.gather(*(_bounded(j) for j in jobs)))

    results: list[tuple[Job, bool, str]] = asyncio.run(_all())

    n_ok = sum(1 for _, ok_flag, _ in results if ok_flag)
    failed = [(j.id, msg) for j, ok_flag, msg in results if not ok_flag]
    if as_json:
        console.print_json(
            json.dumps(
                {
                    "ok": True,
                    "parsed": n_ok,
                    "failed": len(failed),
                    "failed_jobs": [{"id": i, "error": m} for i, m in failed],
                }
            )
        )
        raise typer.Exit(code=1 if failed else 0)

    table = Table(title=f"jh parse run ({n_ok} ok, {len(failed)} failed)")
    table.add_column("job")
    table.add_column("status")
    table.add_column("detail")
    for j, ok_flag, msg in results:
        table.add_row(
            f"{j.id} {j.title or ''}".strip(),
            "[green]parsed[/green]" if ok_flag else "[red]failed[/red]",
            msg,
        )
    console.print(table)
    if failed:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------- job
@job_app.command("add")
def job_add(
    url: str = typer.Option(..., "--url", help="Job URL"),
    paste: bool = typer.Option(False, "--paste", help="Read JD text from stdin"),
    title: str = typer.Option(None, "--title", help="Job title (optional)"),
    company: str = typer.Option(None, "--company", help="Company name (optional)"),
    config: str = typer.Option("config/config.yaml", help="config path"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Manually add a job by pasting a URL and/or JD text (spec §11.1)."""
    import httpx

    from jobharness.db.session import get_session, init_session_factory, make_engine
    from jobharness.ingest.dedup import Deduper
    from jobharness.ingest.manual import ManualAdapter
    from jobharness.settings import Settings

    cfg_path = Path(config)
    if not cfg_path.is_absolute():
        cfg_path = Path.cwd() / cfg_path
    if not cfg_path.exists():
        _fail(f"config not found: {config}", as_json=as_json)
        return
    try:
        settings: Settings = Settings.from_yaml(cfg_path)
    except Exception as e:
        _fail(f"config invalid: {e}", as_json=as_json)
        return

    data_dir = Path(settings.paths.data_dir)
    if not data_dir.is_absolute():
        data_dir = cfg_path.parent / data_dir
    engine = make_engine(data_dir / "jobharness.db")
    init_session_factory(engine)

    if paste:
        jd_text = sys.stdin.read()
    else:
        # Fetch the JD text from the URL.
        try:
            resp = httpx.get(url, timeout=30.0, follow_redirects=True)
            resp.raise_for_status()
            jd_text = resp.text
        except httpx.HTTPError as e:
            _fail(f"failed to fetch {url}: {e}", as_json=as_json)
            return

    adapter = ManualAdapter()
    raw = adapter.make_raw(
        url=url, jd_text=jd_text, title=title, company=company
    )

    with get_session()() as s:
        deduper = Deduper(s)
        report = deduper.check_batch([raw])
        result = report.results[0]
        if result.action == "insert":
            deduper.insert_job(raw, url_hash_=result.url_hash, jd_hash_=result.jd_hash)
            s.commit()
            action = "inserted"
            job_id = None
        else:
            s.commit()
            action = result.action
            job_id = result.matched_job_id
        if as_json:
            console.print_json(
                json.dumps(
                    {
                        "ok": True,
                        "action": action,
                        "url_hash": result.url_hash,
                        "jd_hash": result.jd_hash,
                        "matched_job_id": job_id,
                    }
                )
            )
        else:
            if action == "insert":
                console.print(f"[green]inserted[/green] {url}")
            else:
                console.print(
                    f"[yellow]{action}[/yellow] {url} "
                    f"(matched job {job_id})"
                )


# ---------------------------------------------------------------- ingest
@ingest_app.command("run")
def ingest_run(
    source: str = typer.Option("manual", "--source", help="Source adapter name"),
    since: str = typer.Option(None, "--since", help="Only fetch jobs posted since this date (ISO)"),
    config: str = typer.Option("config/config.yaml", help="config path"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run an ingest adapter and insert new jobs (spec §11.1)."""
    import asyncio
    from datetime import datetime as _dt

    from jobharness.db.session import get_session, init_session_factory, make_engine
    from jobharness.ingest.dedup import Deduper
    from jobharness.ingest.email_alerts import EmailAlertsAdapter
    from jobharness.ingest.rss import RssAdapter
    from jobharness.settings import Settings

    cfg_path = Path(config)
    if not cfg_path.is_absolute():
        cfg_path = Path.cwd() / cfg_path
    if not cfg_path.exists():
        _fail(f"config not found: {config}", as_json=as_json)
        return
    try:
        settings: Settings = Settings.from_yaml(cfg_path)
    except Exception as e:
        _fail(f"config invalid: {e}", as_json=as_json)
        return

    data_dir = Path(settings.paths.data_dir)
    if not data_dir.is_absolute():
        data_dir = cfg_path.parent / data_dir
    engine = make_engine(data_dir / "jobharness.db")
    init_session_factory(engine)

    since_dt: _dt | None = None
    if since:
        try:
            since_dt = _dt.fromisoformat(since)
        except ValueError:
            _fail(f"invalid --since date: {since}", as_json=as_json)
            return

    if source == "manual":
        _fail("manual source: use `jh job add` instead", as_json=as_json)
        return

    if source == "rss":
        feeds = settings.ingest.rss_feeds if settings.ingest else []
        if not feeds:
            _fail(
                "no RSS feeds configured (config.ingest.rss_feeds)",
                as_json=as_json,
            )
            return
        from jobharness.ingest.base import RawJob

        async def _collect_rss() -> list[RawJob]:
            adapter = RssAdapter(feed_urls=feeds)
            raws: list[RawJob] = []
            async for raw in adapter.fetch(since=since_dt):
                raws.append(raw)
            return raws

        try:
            raw_jobs = asyncio.run(_collect_rss())
        except Exception as e:
            _fail(f"ingest failed: {e}", as_json=as_json)
            return

    elif source == "email_alerts":
        ia = settings.ingest
        if ia is None or ia.email_alerts_imap is None:
            _fail(
                "email_alerts not configured (config.ingest.email_alerts_imap)",
                as_json=as_json,
            )
            return
        import os

        from jobharness.ingest.base import RawJob

        password = os.environ.get("IMAP_PASSWORD", "")
        imap_host = ia.email_alerts_imap
        assert imap_host is not None  # checked above

        async def _collect_email() -> list[RawJob]:
            adapter = EmailAlertsAdapter(
                imap_host=imap_host,
                username=os.environ.get("IMAP_USERNAME", ""),
                password=password,
                mailbox=ia.email_alerts_label or "INBOX",
            )
            raws: list[RawJob] = []
            async for raw in adapter.fetch(since=since_dt):
                raws.append(raw)
            return raws

        try:
            raw_jobs = asyncio.run(_collect_email())
        except Exception as e:
            _fail(f"ingest failed: {e}", as_json=as_json)
            return

    elif source == "superjob":
        import os as _os

        from jobharness.ingest.base import RawJob
        from jobharness.ingest.superjob import SuperJobAdapter, build_superjob_queries
        from jobharness.schemas.profile import load_profile

        sj_key = _os.environ.get("SUPERJOB_API_KEY")
        if not sj_key:
            _fail("SUPERJOB_API_KEY is not set", as_json=as_json)
            return
        profile_path = Path("config/profile.yaml")
        if not profile_path.is_absolute():
            profile_path = Path.cwd() / profile_path
        if not profile_path.exists():
            _fail("config/profile.yaml not found (queries are built from it)", as_json=as_json)
            return
        sj_queries = build_superjob_queries(load_profile(str(profile_path)))

        async def _collect_sj() -> list[RawJob]:
            adapter = SuperJobAdapter(lambda: sj_key, sj_queries)
            return [r async for r in adapter.fetch(since=since_dt)]

        try:
            raw_jobs = asyncio.run(_collect_sj())
        except Exception as e:
            _fail(f"ingest failed: {e}", as_json=as_json)
            return

    else:
        _fail(f"unknown source: {source}", as_json=as_json)
        return

    if not raw_jobs:
        if as_json:
            console.print_json(json.dumps({"ok": True, "fetched": 0, "inserted": 0}))
        else:
            console.print("[yellow]no new jobs found[/yellow]")
        return

    with get_session()() as s:
        deduper = Deduper(s)
        report = deduper.check_batch(raw_jobs)
        inserted = 0
        for r in report.results:
            if r.action == "insert":
                deduper.insert_job(
                    r.raw, url_hash_=r.url_hash, jd_hash_=r.jd_hash
                )
                inserted += 1
        s.commit()

    if as_json:
        console.print_json(
            json.dumps(
                {
                    "ok": True,
                    "fetched": len(raw_jobs),
                    "inserted": inserted,
                    "summary": report.summary(),
                }
            )
        )
    else:
        table = Table(title=f"jh ingest run ({len(raw_jobs)} fetched, {inserted} new)")
        table.add_column("action")
        table.add_column("url")
        table.add_column("matched")
        for r in report.results:
            table.add_row(
                r.action,
                r.raw.url,
                str(r.matched_job_id) if r.matched_job_id else "-",
            )
        console.print(table)


# ---------------------------------------------------------------- route
@route_app.command("run")
def route_run(
    explain: int | None = typer.Option(
        None,
        "--explain",
        help="Print the full filter/score breakdown for this job id",
    ),
    config: str = typer.Option("config/config.yaml", help="config path"),
    profile: str = typer.Option("config/profile.yaml", help="profile path"),
    positioning: str = typer.Option(
        "config/positioning.yaml", help="positioning path"
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Route all jobs with status=parsed (spec §11.3, M3)."""
    import json as _json

    from sqlalchemy import select

    from jobharness.db.models import Job
    from jobharness.db.session import get_session, init_session_factory, make_engine
    from jobharness.db.state_machine import assert_transition
    from jobharness.parse.normalizers import UnknownCurrencyError, normalize_compensation
    from jobharness.route.router import RouteResult, route_job
    from jobharness.schemas.archetype import load_archetypes
    from jobharness.schemas.jd import JDParsed
    from jobharness.schemas.positioning import load_positioning
    from jobharness.schemas.profile import load_profile
    from jobharness.settings import Settings

    def _resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else Path.cwd() / path

    cfg_path = _resolve(config)
    if not cfg_path.exists():
        _fail(f"config not found: {config}", as_json=as_json)
        return
    try:
        settings: Settings = Settings.from_yaml(cfg_path)
    except Exception as e:
        _fail(f"config invalid: {e}", as_json=as_json)
        return

    prof_path = _resolve(profile)
    pos_path = _resolve(positioning)
    if not prof_path.exists():
        _fail(f"profile not found: {profile}", as_json=as_json)
        return
    if not pos_path.exists():
        _fail(f"positioning not found: {positioning}", as_json=as_json)
        return
    prof = load_profile(str(prof_path))
    pos = load_positioning(pos_path)
    arch_dir = _resolve("config/archetypes")
    if not arch_dir.is_dir():
        _fail(f"archetypes dir not found: {arch_dir}", as_json=as_json)
        return
    archetypes = load_archetypes(arch_dir)

    data_dir = Path(settings.paths.data_dir)
    if not data_dir.is_absolute():
        data_dir = cfg_path.parent / data_dir
    engine = make_engine(data_dir / "jobharness.db")
    init_session_factory(engine)

    with get_session()() as s:
        jobs: list[Job] = list(
            s.execute(select(Job).where(Job.status == "parsed")).scalars().all()
        )

    if not jobs:
        if as_json:
            console.print_json(_json.dumps({"ok": True, "routed": 0}))
        else:
            console.print("[yellow]no jobs with status=parsed[/yellow]")
        return

    def _route_one(job: Job) -> tuple[RouteResult, str]:
        parsed = JDParsed.model_validate_json(job.jd_parsed_json or "{}")
        norm = None
        if parsed.compensation is not None:
            try:
                norm = normalize_compensation(
                    parsed.compensation,
                    settings,
                    hours_per_week=parsed.hours_per_week,
                )
            except UnknownCurrencyError:
                norm = None
        result = route_job(
            parsed, prof, pos, archetypes, settings, normalized_comp=norm
        )
        target = "rejected" if result.rejected else "shortlisted"
        with get_session()() as s:
            row = s.get(Job, job.id)
            assert row is not None
            assert_transition(row.status, target, kind="job")
            row.status = target
            row.score = result.score
            row.score_breakdown_json = _json.dumps(
                result.breakdown or {}, sort_keys=True
            )
            row.archetype = result.archetype
            row.reject_reasons_json = _json.dumps(result.reject_reasons)
            row.overlap_hours = result.overlap_hours
            s.commit()
        return result, target

    results: list[tuple[int, str, RouteResult, str]] = []
    for job in jobs:
        result, target = _route_one(job)
        results.append((job.id, job.title or "", result, target))

    if not as_json:
        table = Table(title=f"jh route run ({len(results)} jobs)")
        table.add_column("job")
        table.add_column("status")
        table.add_column("score")
        table.add_column("archetype")
        table.add_column("reasons/flags")
        for job_id, title, result, target in results:
            detail = ", ".join(result.reject_reasons) or ", ".join(result.flags) or "-"
            table.add_row(
                f"{job_id} {title}".strip(),
                f"[red]{target}[/red]" if target == "rejected" else f"[green]{target}[/green]",
                str(result.score if result.score is not None else "-"),
                result.archetype or "-",
                detail,
            )
        console.print(table)

    if explain is not None:
        for job_id, _title, result, target in results:
            if job_id != explain:
                continue
            table = Table(title=f"route explain {job_id}")
            table.add_column("filter/component")
            table.add_column("outcome")
            table.add_column("detail")
            for d in result.filter_details:
                table.add_row(d["filter"], d["outcome"], d["detail"])
            if result.breakdown:
                for k, v in result.breakdown.items():
                    table.add_row(f"score:{k}", "score", str(v))
            table.add_row("archetype_top2", "info", str(result.archetype_top2))
            table.add_row("status", "info", target)
            console.print(table)

    if as_json:
        out = [
            {
                "job_id": job_id,
                "title": title,
                "status": target,
                "score": result.score,
                "archetype": result.archetype,
                "reject_reasons": result.reject_reasons,
                "flags": result.flags,
            }
            for job_id, title, result, target in results
        ]
        console.print_json(
            _json.dumps({"ok": True, "routed": len(results), "results": out})
        )


@eval_app.command("run")
def eval_run(
    suite: str = typer.Option("router", "--suite", help="Eval suite to run"),
    config: str = typer.Option("config/config.yaml", help="config path"),
    profile: str = typer.Option("config/profile.yaml", help="profile path"),
    positioning: str = typer.Option("config/positioning.yaml", help="positioning path"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run eval suite (spec §13.3)."""
    import json as _json
    from pathlib import Path

    from jobharness.route.golden import evaluate_router
    from jobharness.schemas.archetype import load_archetypes
    from jobharness.schemas.positioning import load_positioning
    from jobharness.schemas.profile import load_profile
    from jobharness.settings import Settings

    def _resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else Path.cwd() / path

    cfg_path = _resolve(config)
    if not cfg_path.exists():
        _fail(f"config not found: {config}", as_json=as_json)
        return
    try:
        settings: Settings = Settings.from_yaml(cfg_path)
    except Exception as e:
        _fail(f"config invalid: {e}", as_json=as_json)
        return

    prof_path = _resolve(profile)
    pos_path = _resolve(positioning)
    if not prof_path.exists():
        _fail(f"profile not found: {profile}", as_json=as_json)
        return
    if not pos_path.exists():
        _fail(f"positioning not found: {positioning}", as_json=as_json)
        return
    prof = load_profile(str(prof_path))
    pos = load_positioning(pos_path)
    arch_dir = _resolve("config/archetypes")
    if not arch_dir.is_dir():
        _fail(f"archetypes dir not found: {arch_dir}", as_json=as_json)
        return
    archetypes = load_archetypes(arch_dir)

    if suite not in ("router", "claims", "all"):
        _fail(f"unknown suite: {suite}", as_json=as_json)
        return

    problems: list[str] = []
    payload: dict[str, object] = {"ok": True}

    if suite in ("router", "all"):
        golden_dir = _resolve("eval_data/golden_jobs")
        metrics = evaluate_router(golden_dir, prof, pos, archetypes, settings)
        payload["router"] = metrics.as_dict()
        if not as_json:
            print(
                f"router: precision={metrics.precision:.3f} "
                f"recall={metrics.recall:.3f} arch_acc={metrics.archetype_accuracy:.3f}"
            )
        baseline_path = _resolve("eval_data/golden_jobs/baseline.json")
        if baseline_path.exists():
            baseline = _json.loads(baseline_path.read_text())
            if metrics.precision < baseline["precision"] - 0.03:
                problems.append(
                    f"router precision dropped > 3 points: "
                    f"{metrics.precision:.3f} < {baseline['precision']:.3f} - 0.03"
                )

    if suite in ("claims", "all"):
        from jobharness.eval.runner import CLAIMS_MIN_RECALL, evaluate_claims

        claims_res = evaluate_claims(_resolve("eval_data/golden_claims"), prof)
        payload["claims"] = claims_res.as_dict()
        if not as_json:
            print(
                f"claims: recall={claims_res.recall:.3f} "
                f"clean_pass_rate={claims_res.clean_pass_rate:.3f} "
                f"({claims_res.n_fabricated} fabricated, {claims_res.n_clean} clean)"
            )
        if claims_res.recall < CLAIMS_MIN_RECALL:
            problems.append(
                f"claims fabrication recall {claims_res.recall:.3f} < {CLAIMS_MIN_RECALL}"
            )
        cbase = _resolve("eval_data/baselines/claims.json")
        if cbase.exists():
            base = _json.loads(cbase.read_text())
            if claims_res.clean_pass_rate < base["clean_pass_rate"] - 0.03:
                problems.append(
                    f"claims clean pass rate dropped > 3 points: "
                    f"{claims_res.clean_pass_rate:.3f} < {base['clean_pass_rate']:.3f} - 0.03"
                )

    if as_json:
        payload["ok"] = not problems
        payload["problems"] = problems
        console.print_json(_json.dumps(payload))
        if problems:
            raise typer.Exit(code=1)
        return
    if problems:
        _fail("; ".join(problems), as_json=False)


@eval_app.command("doc")
def eval_doc(
    doc_id: int = typer.Argument(..., help="documents.id of a resume"),
    config: str = typer.Option("config/config.yaml", help="config path"),
    profile: str = typer.Option("config/profile.yaml", help="profile path"),
    positioning: str = typer.Option("config/positioning.yaml", help="positioning path"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run gates G1-G7 on one stored resume (+ its cover letter) and record an eval run."""
    import json as _json
    from pathlib import Path

    from sqlalchemy import select

    from jobharness.db.models import Document, Job
    from jobharness.db.session import get_session, init_session_factory, make_engine
    from jobharness.eval.gates import run_gates
    from jobharness.eval.runner import record_eval_run
    from jobharness.schemas.archetype import load_archetypes
    from jobharness.schemas.documents import CoverLetter, ResumeContent
    from jobharness.schemas.jd import JDParsed
    from jobharness.schemas.positioning import load_positioning
    from jobharness.schemas.profile import load_profile
    from jobharness.settings import Settings

    def _resolve(p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else Path.cwd() / path

    cfg_path = _resolve(config)
    if not cfg_path.exists():
        _fail(f"config not found: {config}", as_json=as_json)
        return
    settings = Settings.from_yaml(cfg_path)
    data_dir = Path(settings.paths.data_dir)
    if not data_dir.is_absolute():
        data_dir = cfg_path.parent / data_dir
    init_session_factory(make_engine(data_dir / "jobharness.db"))
    prof = load_profile(str(_resolve(profile)))
    pos = load_positioning(_resolve(positioning))
    archetypes = load_archetypes(_resolve("config/archetypes"))

    with get_session()() as s:
        doc = s.get(Document, doc_id)
        if doc is None or doc.kind != "resume" or not doc.content_json:
            _fail(f"resume document {doc_id} not found", as_json=as_json)
            return
        job = s.get(Job, doc.job_id) if doc.job_id else None
        cover_doc = s.execute(
            select(Document).where(Document.job_id == doc.job_id, Document.kind == "cover")
        ).scalars().first()
        content = ResumeContent.model_validate_json(doc.content_json)
        letter = (
            CoverLetter.model_validate_json(cover_doc.content_json)
            if cover_doc and cover_doc.content_json
            else None
        )
        jd = JDParsed.model_validate_json((job.jd_parsed_json if job else None) or '{"title": ""}')
        arch = archetypes.get((job.archetype if job else None) or "") or next(iter(archetypes.values()))
        pdf = Path(doc.pdf_path) if doc.pdf_path and Path(doc.pdf_path).exists() else None
        gates = run_gates(
            content, letter, prof, pos, arch, jd,
            company=job.company if job else None, pdf_path=pdf,
        )
        passed = all(g.passed for g in gates)
        results: dict[str, object] = {"gates": [{"gate": g.gate, "passed": g.passed, "messages": list(g.messages)} for g in gates]}
        record_eval_run(s, "doc", doc_id, results, passed)
        doc.eval_json = _json.dumps(results, sort_keys=True)
        doc.eval_pass = passed
        s.commit()

    if as_json:
        console.print_json(_json.dumps({"ok": passed, **results}))
    else:
        table = Table(title=f"jh eval doc {doc_id}")
        table.add_column("gate")
        table.add_column("result")
        table.add_column("messages")
        for g in gates:
            table.add_row(g.gate, "[green]pass[/green]" if g.passed else "[red]fail[/red]", "; ".join(g.messages))
        console.print(table)
    if not passed:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------- bot
bot_app = typer.Typer(help="Telegram bot.")
app.add_typer(bot_app, name="bot")


@bot_app.command("run")
def bot_run() -> None:
    """Run the Telegram bot (long polling). Needs TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_ID, JH_MASTER_KEY."""
    import asyncio

    from jobharness.bot.app import ConfigError, run_bot

    try:
        asyncio.run(run_bot())
    except ConfigError as e:
        _fail(str(e))


# ---------------------------------------------------------------- pipeline
pipeline_app = typer.Typer(help="Search pipeline.")
app.add_typer(pipeline_app, name="pipeline")


@pipeline_app.command("run-once")
def pipeline_run_once(as_json: bool = typer.Option(False, "--json")) -> None:
    """Run one search cycle (no Telegram delivery) using the bot's data directory."""
    import asyncio

    from jobharness.bot.app import ConfigError, build_services_from_env, default_provider_factory
    from jobharness.bot.provider_commands import SUPERJOB_SECRET
    from jobharness.bot.user_settings import load_runtime
    from jobharness.pipeline.cycle import CycleDeps, run_cycle

    try:
        services = build_services_from_env()
        rt = load_runtime(services.config_path, services.data_dir)
    except (ConfigError, RuntimeError) as e:
        _fail(str(e), as_json=as_json)
        return
    deps = CycleDeps(
        rt, default_provider_factory(rt, services),
        lambda: services.secrets.get(SUPERJOB_SECRET), services.clock(), services.transport,
    )
    report = asyncio.run(run_cycle(deps))
    if as_json:
        console.print_json(json.dumps({"ok": report.refused is None, **report.as_dict()}))
    else:
        console.print(report.as_dict())
    if report.refused:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

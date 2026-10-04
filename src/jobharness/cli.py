"""jobharness CLI (Typer).

M1 commands: ``init``, ``doctor``, ``profile validate|lint|show``.
All commands: ``--json`` output option, non-zero exit on error, idempotent
where reasonable.
"""

from __future__ import annotations

import json
import shutil
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

    # 4. LLM key
    import os

    key_present = bool(os.environ.get("ANTHROPIC_API_KEY"))
    checks["llm_key"] = {"ok": key_present}

    # 5. Mailbox (informational; not a hard fail in M1)
    checks["mailbox"] = {"ok": False, "note": "mailbox check is wired in M6"}

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


if __name__ == "__main__":
    app()

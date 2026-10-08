"""Preferences wizard (plan step 4.4): rate, hours, timezone, filters, display."""

from __future__ import annotations

from typing import Any

from jobharness.bot.core import BotCore, Ctx
from jobharness.bot.profile_wizard import p_choice, p_tz
from jobharness.bot.user_settings import (
    load_runtime,
    load_settings,
    save_positioning,
    save_user_settings,
)
from jobharness.bot.wizard import Answers, Step, Wizard, WizardRunner

ENGAGEMENTS = ("contractor", "b2b", "freelance", "project")


def p_float(minimum: float = 0.0):  # type: ignore[no-untyped-def]
    def parse(text: str, _a: Answers) -> float:
        try:
            v = float(text.strip().replace(",", "").replace("$", ""))
        except ValueError:
            raise ValueError("Please send a number.") from None
        if v < minimum:
            raise ValueError(f"Must be at least {minimum:g}.")
        return v

    return parse


def p_window(text: str, _a: Answers) -> tuple[str, str]:
    parts = text.replace("–", "-").split("-")
    if len(parts) != 2:
        raise ValueError('Use "09:00-18:00".')
    out = []
    for p in parts:
        hh, _, mm = p.strip().partition(":")
        if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
            raise ValueError('Use "09:00-18:00".')
        out.append(f"{int(hh):02d}:{int(mm):02d}")
    return out[0], out[1]


def p_countries(text: str, _a: Answers) -> list[str]:
    codes = [c.strip().upper() for c in text.replace(";", ",").split(",") if c.strip()]
    if any(len(c) != 2 or not c.isalpha() for c in codes):
        raise ValueError('Use 2-letter codes, e.g. "US, DE".')
    return codes


def p_engagements(text: str, _a: Answers) -> list[str]:
    items = [t.strip().lower() for t in text.replace(";", ",").split(",") if t.strip()]
    if not items or any(i not in ENGAGEMENTS for i in items):
        raise ValueError("Choose from: " + ", ".join(ENGAGEMENTS))
    return items


def register_preferences(core: BotCore, runner: WizardRunner) -> None:
    async def done(ctx: Ctx, a: Answers) -> None:
        cfg, data = ctx.services.config_path, ctx.services.data_dir
        start, end = a["window"]
        settings_patch: dict[str, Any] = {
            "router": {
                "rate_floor_usd_month": a["rate_min"],
                "rate_ceiling_usd_month": a["rate_max"],
                "countries_allow": a.get("allow") or [],
                "countries_deny": a.get("deny") or [],
                "engagement_types_allow": a["engagements"],
            },
            "principal": {"timezone": a["timezone"], "work_window_local": {"start": start, "end": end}},
            "bot": {"search_interval_minutes": int(a["interval"])},
        }
        pos_patch = {
            "rate_expectation_usd_month": {"min": a["rate_min"], "max": a["rate_max"]},
            "hours_week": {"min": a["hours_min"], "max": a["hours_max"]},
            "employer_display": a["employer_display"],
            "title_display": a["title_display"],
        }
        try:
            save_user_settings(cfg, data, settings_patch)
            save_positioning(cfg.parent, data, pos_patch)
        except ValueError as e:
            await ctx.reply(f"Not saved: {e}\nSend /preferences to try again.")
            return
        await ctx.reply("Preferences saved. Next: /providers, /feeds, then /run.")

    def default_tz(a: Answers) -> str:
        try:
            return load_runtime(core.services.config_path, core.services.data_dir).profile.identity.location.timezone
        except Exception:
            return load_settings(core.services.config_path, core.services.data_dir).principal.timezone

    runner.register(Wizard("preferences", [
        Step("rate_min", "Minimum acceptable rate, USD per month?", p_float()),
        Step("rate_max", "Typical target rate (upper end), USD per month?", p_float()),
        Step("hours_min", "Minimum hours per week you want?", p_float()),
        Step("hours_max", "Maximum hours per week?", p_float()),
        Step("timezone", lambda a: f"Your timezone (IANA)? Suggested: {default_tz(a)}", p_tz),
        Step("window", 'Daily working window, e.g. "09:00-18:00"?', p_window),
        Step("allow", 'Only these countries (2-letter codes, comma separated)? /skip for worldwide',
             p_countries, optional=True, default=[]),
        Step("deny", "Exclude these countries? /skip for none", p_countries, optional=True, default=[]),
        Step("engagements", "Accepted engagement types: " + ", ".join(ENGAGEMENTS) + "?", p_engagements),
        Step("employer_display", "Show employer names on resumes: full or anonymized?",
             p_choice(("full", "anonymized"))),
        Step("title_display", "Job titles: exact or handson_descriptor?",
             p_choice(("exact", "handson_descriptor"))),
        Step("interval", "Search every how many minutes? (minimum 15)", p_float(15)),
    ], done, intro="Preferences. They decide which jobs are shown to you."))

    @core.command("preferences", "set rate, hours, filters and display options")
    async def prefs(ctx: Ctx, _args: str) -> None:
        await runner.start(ctx, "preferences")


__all__ = ["register_preferences"]

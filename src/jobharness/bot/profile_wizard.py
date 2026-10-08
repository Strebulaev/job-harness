"""Profile wizard (plan step 4.3). Writes only what the Principal typed.

The profile is built as a draft dict (persisted in ``bot_state``), validated
with the real :class:`Profile` model plus :func:`validate_profile`, and written
atomically to ``<data_dir>/profile.yaml``. Fact ids are generated from slugs;
the user never types them.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from pydantic import ValidationError

from jobharness.bot.core import BotCore, Ctx
from jobharness.bot.user_settings import profile_path, write_yaml_atomic
from jobharness.bot.wizard import Answers, Step, Wizard, WizardRunner, yes_no
from jobharness.schemas.profile import Profile, lint_profile, validate_profile

DRAFT_KEY = "profile:draft"
LEVELS = ("familiar", "working", "proficient", "expert")
KINDS = ("hands_on", "leadership", "strategy", "budget")
EMPLOYMENT = ("full_time", "part_time", "contractor", "b2b", "intern")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def unique_id(base: str, taken: set[str]) -> str:
    cand, n = base, 2
    while cand in taken:
        cand = f"{base}-{n}"
        n += 1
    return cand


# ------------------------------------------------------------------ parsers
def p_text(text: str, _a: Answers) -> str:
    if not text.strip():
        raise ValueError("Please send some text.")
    return text.strip()


def p_email(text: str, _a: Answers) -> str:
    if not _EMAIL.match(text.strip()):
        raise ValueError("That does not look like an email address.")
    return text.strip()


def p_tz(text: str, _a: Answers) -> str:
    try:
        ZoneInfo(text.strip())
    except Exception:
        raise ValueError("Unknown timezone. Use an IANA name like Europe/Berlin.") from None
    return text.strip()


def p_month(text: str, _a: Answers) -> str:
    t = text.strip()
    try:
        date.fromisoformat(f"{t}-01")
    except ValueError:
        raise ValueError("Use the format YYYY-MM, for example 2021-03.") from None
    return t


def p_month_or_present(text: str, a: Answers) -> str | None:
    if text.strip().lower() in {"present", "now", "current"}:
        return None
    return p_month(text, a)


def p_choice(options: tuple[str, ...]):  # type: ignore[no-untyped-def]
    def parse(text: str, _a: Answers) -> str:
        t = text.strip().lower().replace(" ", "_").replace("-", "_")
        if t not in options:
            raise ValueError("Choose one of: " + ", ".join(options))
        return t

    return parse


def p_tags(text: str, _a: Answers) -> list[str]:
    return [t.strip().lower() for t in text.replace(";", ",").split(",") if t.strip()]


def p_languages(text: str, _a: Answers) -> list[dict[str, str]]:
    out = []
    for item in text.split(","):
        lang, _, level = item.strip().rpartition(" ")
        if not lang or not level:
            raise ValueError('Use "English C1, Russian native" (language then level).')
        out.append({"lang": lang.strip(), "level": level.strip()})
    return out


def p_metric(text: str, _a: Answers) -> dict[str, Any]:
    name, sep, value = text.partition("=")
    try:
        return {"name": name.strip(), "value": float(value.strip().replace(",", ""))}
    except ValueError:
        raise ValueError('Use name=number, for example "req/day=2000000".') from None


def p_skills(text: str, _a: Answers) -> list[dict[str, Any]]:
    out = []
    for item in text.split(","):
        parts = [x.strip() for x in item.split(":")]
        if len(parts) != 3:
            raise ValueError('Use "Python:expert:12, SQL:proficient:8" (name:level:years).')
        name, level, years = parts
        if level.lower() not in LEVELS:
            raise ValueError("Level must be one of: " + ", ".join(LEVELS))
        try:
            y = float(years)
        except ValueError:
            raise ValueError("Years must be a number.") from None
        if y < 0:
            raise ValueError("Years cannot be negative.")
        out.append({"name": name, "level": level.lower(), "years": y})
    if not out:
        raise ValueError("Send at least one skill.")
    return out


# ------------------------------------------------------------------ draft IO
def load_draft(ctx: Ctx) -> dict[str, Any]:
    draft = ctx.services.state.get(DRAFT_KEY)
    if isinstance(draft, dict):
        return draft
    pp = profile_path(ctx.services.data_dir)
    if pp.exists():
        raw = yaml.safe_load(pp.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    return {
        "version": 1, "summary_facts": [], "experience": [], "education": [],
        "certifications": [], "projects": [], "skills": [],
        "disclosure_rules": {"allow_employer_anonymization": False,
                             "must_disclose_real_employer_on": [], "never_claim": []},
    }


async def commit_draft(ctx: Ctx, draft: dict[str, Any]) -> bool:
    """Validate and write the draft. Replies with problems or lint advice."""
    ctx.services.state.set(DRAFT_KEY, draft)
    if "identity" not in draft:
        await ctx.reply("Saved. Still needed: identity (/profile_identity).")
        return False
    try:
        profile = Profile.model_validate(draft)
    except ValidationError as e:
        err = e.errors()[0]
        await ctx.reply(f"Profile problem at {'.'.join(str(x) for x in err['loc'])}: {err['msg']}")
        return False
    fatal = validate_profile(profile)
    if fatal:
        await ctx.reply("Profile problems:\n- " + "\n- ".join(fatal))
        return False
    write_yaml_atomic(profile_path(ctx.services.data_dir), profile.model_dump(mode="json"))
    warnings = lint_profile(profile)
    msg = "Profile saved."
    if warnings:
        msg += "\nAdvice:\n- " + "\n- ".join(warnings[:6])
    await ctx.reply(msg)
    return True


def missing_for_run(profile: Profile) -> list[str]:
    out = []
    if not profile.experience:
        out.append("at least one role (/profile_role)")
    if not profile.skills:
        out.append("skills (/profile_skills)")
    return out


# ------------------------------------------------------------------ wizards
def register_profile(core: BotCore, runner: WizardRunner) -> None:
    async def chain(ctx: Ctx, answers: Answers) -> None:
        rest = list(answers.get("_chain") or [])
        if rest:
            nxt = rest.pop(0)
            await runner.start(ctx, nxt, {"_chain": rest})
        else:
            await ctx.reply("Next: /preferences, /providers, /feeds, then /run. See /profile for status.")

    # -- identity
    async def done_identity(ctx: Ctx, a: Answers) -> None:
        d = load_draft(ctx)
        d["identity"] = {
            "full_name": a["full_name"], "email": a["email"], "phone": a.get("phone"),
            "location": {"city": a["city"], "country": a["country"], "timezone": a["timezone"]},
            "links": {"github": a.get("github"), "linkedin": a.get("linkedin"), "site": None},
            "languages": a.get("languages") or [],
        }
        if await commit_draft(ctx, d):
            await chain(ctx, a)

    runner.register(Wizard("profile_identity", [
        Step("full_name", "Your full name as it should appear on the resume?", p_text),
        Step("email", "Contact email?", p_email),
        Step("phone", "Phone number?", p_text, optional=True),
        Step("city", "City?", p_text),
        Step("country", "Country (2-letter code, e.g. DE)?", p_text),
        Step("timezone", "Timezone (IANA name, e.g. Europe/Berlin)?", p_tz),
        Step("languages", 'Languages and levels, e.g. "English C1, Russian native"?',
             p_languages, optional=True, default=[]),
        Step("github", "GitHub URL?", p_text, optional=True),
        Step("linkedin", "LinkedIn URL?", p_text, optional=True),
    ], done_identity, intro="Identity. Everything on your resume comes only from what you type here."))

    # -- summary
    async def done_summary(ctx: Ctx, a: Answers) -> None:
        d = load_draft(ctx)
        d["summary_facts"] = [{"id": "sum.1", "text": a["text"], "tags": a.get("tags") or []}]
        if await commit_draft(ctx, d):
            await chain(ctx, a)

    runner.register(Wizard("profile_summary", [
        Step("text", "One or two sentences summarizing your profile (only true statements).", p_text),
        Step("tags", "Topic tags, comma separated (e.g. backend, ai)?", p_tags, optional=True, default=[]),
    ], done_summary))

    # -- role (with bullet loop)
    def save_more(a: Answers, value: bool) -> None:
        bullet: dict[str, Any] = {
            "text": a.pop("b_text"), "tags": a.pop("b_tags", None) or [],
            "kind": a.pop("b_kind", None) or "hands_on", "metrics": [], "evidence": None,
        }
        metric = a.pop("b_metric", None)
        evidence = a.pop("b_evidence", None)
        if metric:
            bullet["metrics"] = [metric]
        if evidence:
            bullet["evidence"] = evidence
        a.setdefault("_bullets", []).append(bullet)
        a["_more"] = value

    async def done_role(ctx: Ctx, a: Answers) -> None:
        d = load_draft(ctx)
        taken = {e["id"] for e in d["experience"]}
        eid = unique_id(f"exp.{slug(a['employer'])}", taken)
        bullets = [
            {**b, "id": f"{eid}.b{i}"} for i, b in enumerate(a.get("_bullets", []), start=1)
        ]
        d["experience"].append({
            "id": eid, "employer_real": a["employer"],
            "employer_display_options": {"full": a["employer"], "anonymized": a.get("anon")},
            "title_real": a["title"],
            "title_display_options": {"exact": a["title"], "handson_descriptor": a.get("descriptor")},
            "start": a["start"], "end": a.get("end"),
            "employment_type": a["etype"], "concurrent": False, "bullets": bullets,
        })
        if await commit_draft(ctx, d):
            await chain(ctx, a)

    runner.register(Wizard("profile_role", [
        Step("employer", "Employer name (real)?", p_text),
        Step("title", "Your real job title there?", p_text),
        Step("start", "Start month (YYYY-MM)?", p_month),
        Step("end", 'End month (YYYY-MM) or "present"?', p_month_or_present),
        Step("etype", "Employment type: " + ", ".join(EMPLOYMENT) + "?", p_choice(EMPLOYMENT)),
        Step("anon", 'Optional truthful descriptor if you want the employer hidden, e.g. "Fintech (~150 employees)"?',
             p_text, optional=True),
        Step("descriptor", 'Optional hands-on title variant, e.g. "Staff Engineer (hands-on, payments)"?',
             p_text, optional=True),
        Step("b_text", "Describe one accomplishment. Only true facts; keep numbers exact.", p_text),
        Step("b_tags", "Tags for it, comma separated (e.g. backend, python)?", p_tags, optional=True, default=[]),
        Step("b_kind", "Kind: " + ", ".join(KINDS) + " (default hands_on)?", p_choice(KINDS),
             optional=True, default="hands_on"),
        Step("b_metric", 'A measurable number in it as name=value (e.g. "req/day=2000000")?', p_metric,
             optional=True, next=lambda a: "b_evidence" if a.get("b_metric") else "b_more"),
        Step("b_evidence", "How could that number be verified (a dashboard, report, repo)?", p_text),
        Step("b_more", "Add another accomplishment for this role? (yes/no)", yes_no, save=save_more,
             next=lambda a: "b_text" if a["_more"] else ""),
    ], done_role, intro="Adding a role."))

    # -- education
    async def done_edu(ctx: Ctx, a: Answers) -> None:
        d = load_draft(ctx)
        taken = {e["id"] for e in d["education"]}
        d["education"].append({
            "id": unique_id(f"edu.{slug(a['institution'])}", taken), "institution": a["institution"],
            "degree": a["degree"], "field": a["field"], "start": a["start"], "end": a.get("end"),
        })
        if await commit_draft(ctx, d):
            await chain(ctx, a)

    runner.register(Wizard("profile_education", [
        Step("institution", "Institution?", p_text),
        Step("degree", "Degree?", p_text),
        Step("field", "Field of study?", p_text),
        Step("start", "Start month (YYYY-MM)?", p_month),
        Step("end", 'End month (YYYY-MM) or "present"?', p_month_or_present),
    ], done_edu))

    # -- skills
    async def done_skills(ctx: Ctx, a: Answers) -> None:
        d = load_draft(ctx)
        taken: set[str] = set()
        skills = []
        for s in a["skills"]:
            sid = unique_id(f"skill.{slug(s['name'])}", taken)
            taken.add(sid)
            skills.append({**s, "id": sid, "last_used": None, "evidence_fact_ids": []})
        d["skills"] = skills
        if await commit_draft(ctx, d):
            await chain(ctx, a)

    runner.register(Wizard("profile_skills", [
        Step("skills", 'Skills as name:level:years, comma separated. Levels: '
             + ", ".join(LEVELS) + '. Example: "Python:expert:12, SQL:proficient:8"', p_skills),
    ], done_skills))

    # -- disclosure
    async def done_disclosure(ctx: Ctx, a: Answers) -> None:
        d = load_draft(ctx)
        d["disclosure_rules"] = {
            "allow_employer_anonymization": a["anon"],
            "must_disclose_real_employer_on": ["offer_stage", "background_check"],
            "never_claim": [x.strip() for x in (a.get("never") or "").split(";") if x.strip()],
        }
        if await commit_draft(ctx, d):
            await chain(ctx, a)

    runner.register(Wizard("profile_disclosure", [
        Step("anon", "May resumes show a truthful descriptor instead of an employer's name? (yes/no)", yes_no),
        Step("never", 'Claims that must never appear, separated by ";" (e.g. "Kubernetes certified")?',
             p_text, optional=True, default=""),
    ], done_disclosure))

    # -- commands
    def starter(name: str):  # type: ignore[no-untyped-def]
        async def cmd(ctx: Ctx, _args: str) -> None:
            await runner.start(ctx, name)
        return cmd

    for cmd_name, wiz_name, helptext in (
        ("profile_identity", "profile_identity", "edit identity and contact"),
        ("profile_summary", "profile_summary", "set the summary"),
        ("profile_role", "profile_role", "add a role with accomplishments"),
        ("profile_education", "profile_education", "add education"),
        ("profile_skills", "profile_skills", "set skills"),
        ("profile_disclosure", "profile_disclosure", "anonymization and never-claim rules"),
    ):
        core.command(cmd_name, helptext)(starter(wiz_name))

    @core.command("profile_start", "guided profile setup (identity, summary, role, skills, disclosure)")
    async def profile_start(ctx: Ctx, _args: str) -> None:
        await runner.start(
            ctx, "profile_identity",
            {"_chain": ["profile_summary", "profile_role", "profile_skills", "profile_disclosure"]},
        )

    @core.command("profile", "show your profile status")
    async def profile_cmd(ctx: Ctx, _args: str) -> None:
        pp = profile_path(ctx.services.data_dir)
        if not pp.exists():
            await ctx.reply("No profile yet. Send /profile_start to create it.")
            return
        profile = Profile.model_validate(yaml.safe_load(pp.read_text(encoding="utf-8")))
        lines = [
            f"Profile: {profile.identity.full_name}",
            f"Roles: {len(profile.experience)}, bullets: "
            f"{sum(len(e.bullets) for e in profile.experience)}, skills: {len(profile.skills)}, "
            f"education: {len(profile.education)}",
        ]
        todo = missing_for_run(profile)
        if todo:
            lines.append("Still needed: " + "; ".join(todo))
        lines.append("Edit: /profile_identity /profile_summary /profile_role /profile_education "
                     "/profile_skills /profile_disclosure — export: /profile_export")
        await ctx.reply("\n".join(lines))

    @core.command("profile_export", "send your profile as a YAML file")
    async def profile_export(ctx: Ctx, _args: str) -> None:
        pp = profile_path(ctx.services.data_dir)
        if not pp.exists():
            await ctx.reply("No profile yet.")
            return
        await ctx.messenger.send_document(ctx.chat_id, pp, "Your profile")


__all__ = ["commit_draft", "load_draft", "missing_for_run", "register_profile", "slug"]

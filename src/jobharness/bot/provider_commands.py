"""Provider connection and model selection (plan step 4.5).

Guardrail provider-keys-never-persisted-in-clear: the user's key message is
deleted FIRST, the key is validated against the provider, stored only through
the encrypted :class:`SecretStore`, and never echoed, logged or put in errors.
"""

from __future__ import annotations

import logging

from jobharness.bot.core import BotCore, Ctx
from jobharness.bot.user_settings import load_settings, save_user_settings
from jobharness.bot.wizard import Answers, Step, Wizard, WizardRunner
from jobharness.ingest.superjob import SuperJobAdapter
from jobharness.llm.openrouter_provider import OpenRouterError, OpenRouterProvider
from jobharness.llm.provider import ProviderConfig

_log = logging.getLogger(__name__)
OPENROUTER_SECRET = "openrouter_api_key"
SUPERJOB_SECRET = "superjob_api_key"
ROLES = ("parse", "compose", "judge", "classify")
MODELS_HINT = (
    "Copy model ids from openrouter.ai/models. Use a small, cheap model for parse and "
    "classify and a stronger one for compose and judge (judge should differ from compose)."
)


def _provider_cfg() -> ProviderConfig:
    return ProviderConfig(
        model_ids={}, temperature={}, max_retries=1, daily_token_budget=1,
        redact_pii_in_logs=True,
    )


def openrouter_client(ctx: Ctx, key: str | None = None) -> OpenRouterProvider:
    secrets = ctx.services.secrets
    return OpenRouterProvider(
        _provider_cfg(), key_getter=(lambda: key) if key is not None else (
            lambda: secrets.get(OPENROUTER_SECRET)
        ), transport=ctx.services.transport,
    )


def superjob_client(ctx: Ctx, key: str | None = None) -> SuperJobAdapter:
    secrets = ctx.services.secrets
    return SuperJobAdapter(
        (lambda: key) if key is not None else (lambda: secrets.get(SUPERJOB_SECRET)),
        [], transport=ctx.services.transport,
    )


async def _check_openrouter(ctx: Ctx, key: str) -> tuple[bool, str]:
    try:
        ok = await openrouter_client(ctx, key).check_key()
    except OpenRouterError as e:
        return False, f"could not reach OpenRouter ({e.status or 'network'})"
    return (ok, "" if ok else "OpenRouter rejected the key")


async def _check_superjob(ctx: Ctx, key: str) -> tuple[bool, str]:
    try:
        ok = await superjob_client(ctx, key).check_key()
    except Exception as e:
        return False, f"could not reach SuperJob ({type(e).__name__})"
    return (ok, "" if ok else "SuperJob rejected the key")


def register_providers(core: BotCore, runner: WizardRunner) -> None:
    checkers = {"openrouter": (OPENROUTER_SECRET, _check_openrouter),
                "superjob": (SUPERJOB_SECRET, _check_superjob)}

    @core.command("providers", "show provider connections")
    async def providers(ctx: Ctx, _args: str) -> None:
        have = ctx.services.secrets.status()
        lines = ["Providers:"]
        for name, (secret, _chk) in checkers.items():
            lines.append(f"- {name}: {'connected' if secret in have else 'not connected'}")
        lines.append("Connect: /connect openrouter or /connect superjob. Disconnect: /disconnect <name>.")
        await ctx.reply("\n".join(lines))

    @core.command("connect", "connect a provider: /connect openrouter|superjob")
    async def connect(ctx: Ctx, args: str) -> None:
        name = args.strip().lower()
        if name not in checkers:
            await ctx.reply("Usage: /connect openrouter or /connect superjob")
            return
        await runner.start(ctx, f"connect_{name}")

    async def key_step_done(ctx: Ctx, a: Answers) -> None:  # never reached with the key
        return None

    def make_key_wizard(name: str) -> None:
        # The key step is handled outside the generic wizard text path so the key
        # never gets persisted in wizard answers/state.
        runner.register(Wizard(f"connect_{name}", [
            Step("key", f"Paste your {name} API key. I will delete your message right away.",
                 lambda t, a: "<redacted>"),
        ], key_step_done))

    for provider_name in checkers:
        make_key_wizard(provider_name)

    original_handle = runner.handle_text

    async def handle_text(ctx: Ctx, text: str) -> bool:
        state = runner.active(ctx)
        if state and str(state.get("wizard", "")).startswith("connect_"):
            name = state["wizard"].removeprefix("connect_")
            secret, check = checkers[name]
            await ctx.delete_incoming()  # first thing: remove the key from the chat
            ctx.services.state.delete("wizard:active")
            key = text.strip()
            ok, reason = await check(ctx, key)
            if ok:
                ctx.services.secrets.set(secret, key)
                await ctx.reply(f"{name} connected.")
            else:
                await ctx.reply(f"{name} not connected: {reason}. Send /connect {name} to retry.")
            del key
            return True
        return await original_handle(ctx, text)

    core.text_handler = handle_text

    @core.command("disconnect", "remove a stored key: /disconnect openrouter|superjob")
    async def disconnect(ctx: Ctx, args: str) -> None:
        name = args.strip().lower()
        if name not in checkers:
            await ctx.reply("Usage: /disconnect openrouter or /disconnect superjob")
            return
        removed = ctx.services.secrets.delete(checkers[name][0])
        await ctx.reply(f"{name} disconnected." if removed else f"{name} was not connected.")

    # ---------------------------------------------------------------- models
    @core.command("models", "show or set OpenRouter models: /models set <role> <model-id>")
    async def models(ctx: Ctx, args: str) -> None:
        parts = args.split()
        settings = load_settings(ctx.services.config_path, ctx.services.data_dir)
        if len(parts) == 3 and parts[0] == "set":
            role, model = parts[1].lower(), parts[2]
            if role not in ROLES:
                await ctx.reply("Role must be one of: " + ", ".join(ROLES))
                return
            try:
                available = await openrouter_client(ctx).list_models()
            except OpenRouterError as e:
                await ctx.reply(f"Could not load the model list: {e}. Connect OpenRouter first (/connect openrouter).")
                return
            if model not in available:
                await ctx.reply("That model id is not on OpenRouter's list. Check the spelling.")
                return
            try:
                save_user_settings(
                    ctx.services.config_path, ctx.services.data_dir,
                    {"llm": {"provider": "openrouter", "models": {role: model}}},
                )
            except ValueError as e:
                await ctx.reply(f"Not saved: {e}")
                return
            await ctx.reply(f"{role} model set to {model}.")
            return
        cur = settings.llm.models
        lines = ["Models:"] + [f"- {r}: {getattr(cur, r)}" for r in ROLES]
        lines.append("Set one: /models set <role> <model-id>")
        lines.append(MODELS_HINT)
        lines.append("Set all four roles before /run.")
        await ctx.reply("\n".join(lines))


def models_configured(model_ids: dict[str, str]) -> list[str]:
    """Roles whose model id is still a placeholder."""
    return [r for r in ROLES if "<" in model_ids.get(r, "<") or not model_ids.get(r)]


__all__ = [
    "OPENROUTER_SECRET",
    "ROLES",
    "SUPERJOB_SECRET",
    "models_configured",
    "openrouter_client",
    "register_providers",
    "superjob_client",
]

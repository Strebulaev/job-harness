"""Assembly: services from the environment, command registration, bot runner."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

from jobharness.bot.core import BotCore, Ctx, Services
from jobharness.bot.delivery import register_delivery
from jobharness.bot.feed_commands import register_feeds
from jobharness.bot.messenger import Messenger
from jobharness.bot.preferences import register_preferences
from jobharness.bot.profile_wizard import register_profile
from jobharness.bot.provider_commands import OPENROUTER_SECRET, register_providers
from jobharness.bot.run_controls import ApScheduler, register_run_controls, restore
from jobharness.bot.user_settings import Runtime
from jobharness.bot.wizard import WizardRunner
from jobharness.db.session import create_schema, init_session_factory, make_engine
from jobharness.llm.provider import LLMProvider, ProviderConfig
from jobharness.secrets.store import SecretError, SecretStore, master_key_valid

_log = logging.getLogger(__name__)

WELCOME = (
    "Hi! I find contractor jobs that fit your profile and send you a tailored resume, "
    "a cover letter and the job link. Nothing is ever sent to an employer.\n\n"
    "Setup, in order:\n"
    "1. /profile_start — your profile (everything on the resume comes only from what you type)\n"
    "2. /preferences — rate, hours, filters\n"
    "3. /connect openrouter — then /models set <role> <model-id> for parse, compose, judge, classify\n"
    "4. /connect superjob and/or /feed_add <url> — job sources\n"
    "5. /run — start. /status shows progress.\n\n"
    "/help lists every command."
)


class ConfigError(RuntimeError):
    """Missing or invalid host configuration (environment variables)."""


def default_provider_factory(rt: Runtime, services: Services) -> LLMProvider:
    cfg = ProviderConfig(
        model_ids=rt.settings.llm.models.model_dump(),
        temperature=rt.settings.llm.temperature.model_dump(),
        max_retries=rt.settings.llm.max_retries,
        daily_token_budget=rt.settings.llm.daily_token_budget,
        redact_pii_in_logs=rt.settings.llm.redact_pii_in_logs,
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )
    if rt.settings.llm.provider == "openrouter":
        from jobharness.llm.openrouter_provider import OpenRouterProvider

        return OpenRouterProvider(
            cfg, key_getter=lambda: services.secrets.get(OPENROUTER_SECRET),
            transport=services.transport,
        )
    if rt.settings.llm.provider == "anthropic":
        from jobharness.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(cfg)
    from jobharness.llm.fake_provider import FakeProvider

    return FakeProvider(os.environ.get("JH_LLM_FIXTURES", "tests/fixtures/llm"))


def build_services_from_env(env: Mapping[str, str] | None = None) -> Services:
    e = env if env is not None else os.environ
    missing = [k for k in ("TELEGRAM_OWNER_ID", "JH_MASTER_KEY") if not e.get(k)]
    if missing:
        raise ConfigError("missing environment variables: " + ", ".join(missing))
    if not e["TELEGRAM_OWNER_ID"].isdigit():
        raise ConfigError("TELEGRAM_OWNER_ID must be your numeric Telegram user id")
    if not master_key_valid(e["JH_MASTER_KEY"]):
        raise ConfigError("JH_MASTER_KEY is not a valid Fernet key")
    data_dir = Path(e.get("JH_DATA_DIR", "./data")).resolve()
    config_path = Path(e.get("JH_CONFIG", "config/config.yaml")).resolve()
    engine = make_engine(data_dir / "jobharness.db")
    create_schema(engine)
    sf = init_session_factory(engine)
    try:
        secrets = SecretStore(sf, e["JH_MASTER_KEY"])
    except SecretError as err:
        raise ConfigError(str(err)) from None
    return Services(
        session_factory=sf, secrets=secrets, config_path=config_path, data_dir=data_dir,
        owner_id=int(e["TELEGRAM_OWNER_ID"]),
    )


def build_core(services: Services, messenger: Messenger) -> BotCore:
    core = BotCore(services, messenger)
    runner = WizardRunner(core)
    core.wizard_runner = runner
    register_profile(core, runner)
    register_preferences(core, runner)
    register_providers(core, runner)
    register_feeds(core, runner)
    register_delivery(core)
    register_run_controls(core)

    @core.command("start", "introduction and setup steps")
    async def start(ctx: Ctx, _args: str) -> None:
        await ctx.reply(WELCOME)

    @core.command("help", "list commands")
    async def help_(ctx: Ctx, _args: str) -> None:
        await ctx.reply("Commands:\n" + "\n".join(sorted(core.help_lines)) +
                        "\n/back /skip /cancel — while answering questions")

    return core


async def run_bot() -> None:
    from jobharness.bot.telegram_app import run_polling

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ConfigError("missing environment variable: TELEGRAM_BOT_TOKEN")
    services = build_services_from_env()
    scheduler = ApScheduler()
    services.extras["scheduler"] = scheduler

    def factory(messenger: Messenger) -> BotCore:
        core = build_core(services, messenger)
        scheduler.start()
        restore(services, messenger)
        return core

    await run_polling(token, factory)


__all__ = [
    "ConfigError",
    "build_core",
    "build_services_from_env",
    "default_provider_factory",
    "run_bot",
]

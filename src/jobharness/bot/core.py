"""Framework-independent bot core: access control, routing, shared services."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy.orm import Session, sessionmaker

from jobharness.bot.messenger import Button, Messenger
from jobharness.bot.state import StateStore
from jobharness.llm.provider import LLMProvider
from jobharness.secrets import SecretStore

if TYPE_CHECKING:
    from jobharness.bot.user_settings import Runtime


_log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class Services:
    session_factory: sessionmaker[Session]
    secrets: SecretStore
    config_path: Path
    data_dir: Path
    owner_id: int
    transport: httpx.AsyncBaseTransport | None = None  # tests inject mocked HTTP
    provider_factory: Callable[[Runtime, Services], LLMProvider] | None = None
    clock: Callable[[], datetime] = _now
    extras: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.state = StateStore(self.session_factory)


@dataclass(frozen=True)
class Incoming:
    user_id: int
    chat_id: int
    message_id: int = 0
    text: str = ""
    callback_data: str | None = None


@dataclass
class Ctx:
    services: Services
    messenger: Messenger
    chat_id: int
    message_id: int
    core: BotCore

    async def reply(self, text: str, buttons: list[list[Button]] | None = None) -> int:
        return await self.messenger.send_text(self.chat_id, text, buttons)

    async def delete_incoming(self) -> bool:
        return await self.messenger.delete_message(self.chat_id, self.message_id)


CommandHandler = Callable[[Ctx, str], Awaitable[None]]
CallbackHandler = Callable[[Ctx, str], Awaitable[None]]


class BotCore:
    def __init__(self, services: Services, messenger: Messenger) -> None:
        self.services = services
        self.messenger = messenger
        self.commands: dict[str, CommandHandler] = {}
        self.callbacks: dict[str, CallbackHandler] = {}
        self.text_handler: Callable[[Ctx, str], Awaitable[bool]] | None = None
        self.help_lines: list[str] = []
        self.wizard_runner: Any = None

    def command(self, name: str, help_text: str = "") -> Callable[[CommandHandler], CommandHandler]:
        def deco(fn: CommandHandler) -> CommandHandler:
            self.commands[name] = fn
            if help_text:
                self.help_lines.append(f"/{name} — {help_text}")
            return fn

        return deco

    def callback(self, prefix: str) -> Callable[[CallbackHandler], CallbackHandler]:
        def deco(fn: CallbackHandler) -> CallbackHandler:
            self.callbacks[prefix] = fn
            return fn

        return deco

    async def handle(self, inc: Incoming) -> None:
        """Entry point for every update. Non-owners are ignored silently.

        Handler errors are reported generically (never with message text, which
        could contain a pasted key) and logged by exception type only.
        """
        if inc.user_id != self.services.owner_id:
            return
        ctx = Ctx(self.services, self.messenger, inc.chat_id, inc.message_id, self)
        try:
            await self._dispatch(ctx, inc)
        except Exception as e:
            _log.error("handler failed: %s", type(e).__name__)
            await ctx.reply("Something went wrong on my side. Try again, or send /help.")

    async def _dispatch(self, ctx: Ctx, inc: Incoming) -> None:
        if inc.callback_data is not None:
            handler = self.callbacks.get(inc.callback_data.split(":", 1)[0])
            if handler is not None:
                await handler(ctx, inc.callback_data)
            return
        text = inc.text.strip()
        if text.startswith("/"):
            head, _, args = text[1:].partition(" ")
            name = head.split("@", 1)[0].lower()
            cmd = self.commands.get(name)
            if cmd is None:
                await ctx.reply("Unknown command. Send /help for the list.")
                return
            await cmd(ctx, args.strip())
            return
        if self.text_handler is not None and await self.text_handler(ctx, text):
            return
        await ctx.reply("I did not understand that. Send /help to see what I can do.")


__all__ = ["BotCore", "CallbackHandler", "CommandHandler", "Ctx", "Incoming", "Services"]

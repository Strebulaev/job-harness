"""aiogram adapter: TelegramMessenger + long-polling loop (plan step 4.1).

UNVERIFIED against live Telegram (no token in development): the adapter is
deliberately thin; all behavior lives in :class:`jobharness.bot.core.BotCore`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jobharness.bot.core import BotCore, Incoming
from jobharness.bot.messenger import Button, Messenger

_log = logging.getLogger(__name__)


class TelegramMessenger:
    def __init__(self, bot: Any) -> None:
        self._bot = bot

    async def send_text(
        self, chat_id: int, text: str, buttons: list[list[Button]] | None = None
    ) -> int:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        markup = None
        if buttons:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=b.text, callback_data=b.data) for b in row]
                for row in buttons
            ])
        msg = await self._bot.send_message(chat_id, text, reply_markup=markup)
        return int(msg.message_id)

    async def send_document(self, chat_id: int, path: Path, caption: str | None = None) -> int:
        from aiogram.types import FSInputFile

        msg = await self._bot.send_document(chat_id, FSInputFile(path), caption=caption)
        return int(msg.message_id)

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        try:
            await self._bot.delete_message(chat_id, message_id)
        except Exception:
            return False
        return True

    async def edit_text(self, chat_id: int, message_id: int, text: str) -> None:
        await self._bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id)


async def run_polling(token: str, core_factory: Callable[[Messenger], BotCore]) -> None:
    from aiogram import Bot, Dispatcher
    from aiogram.types import CallbackQuery, Message

    bot = Bot(token)
    messenger = TelegramMessenger(bot)
    core = core_factory(messenger)
    dp = Dispatcher()

    @dp.message()
    async def on_message(m: Message) -> None:
        if m.from_user is None:
            return
        await core.handle(Incoming(m.from_user.id, m.chat.id, m.message_id, m.text or ""))

    @dp.callback_query()
    async def on_callback(q: CallbackQuery) -> None:
        await q.answer()
        if q.message is None or q.data is None:
            return
        await core.handle(
            Incoming(q.from_user.id, q.message.chat.id, q.message.message_id, callback_data=q.data)
        )

    await dp.start_polling(bot)


__all__ = ["TelegramMessenger", "run_polling"]

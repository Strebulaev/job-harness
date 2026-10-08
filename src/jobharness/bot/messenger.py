"""Messenger port: the only thing bot logic knows about Telegram.

Handlers talk to :class:`Messenger`; ``TelegramMessenger`` (aiogram) and the
in-memory :class:`FakeMessenger` both implement it, so every flow is testable
offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable


@dataclass(frozen=True)
class Button:
    text: str
    data: str


@runtime_checkable
class Messenger(Protocol):
    async def send_text(
        self, chat_id: int, text: str, buttons: list[list[Button]] | None = None
    ) -> int: ...

    async def send_document(self, chat_id: int, path: Path, caption: str | None = None) -> int: ...

    async def delete_message(self, chat_id: int, message_id: int) -> bool: ...

    async def edit_text(self, chat_id: int, message_id: int, text: str) -> None: ...


@dataclass
class Sent:
    kind: Literal["text", "document"]
    chat_id: int
    message_id: int
    text: str = ""
    path: Path | None = None
    buttons: list[list[Button]] | None = None


@dataclass
class FakeMessenger:
    """Records everything; ``fail_send`` / ``fail_delete`` simulate Telegram errors."""

    sent: list[Sent] = field(default_factory=list)
    deleted: list[tuple[int, int]] = field(default_factory=list)
    edits: list[tuple[int, int, str]] = field(default_factory=list)
    fail_send: bool = False
    fail_delete: bool = False
    _next_id: int = 1000

    def _id(self) -> int:
        self._next_id += 1
        return self._next_id

    async def send_text(
        self, chat_id: int, text: str, buttons: list[list[Button]] | None = None
    ) -> int:
        if self.fail_send:
            raise RuntimeError("telegram send failed")
        mid = self._id()
        self.sent.append(Sent("text", chat_id, mid, text=text, buttons=buttons))
        return mid

    async def send_document(self, chat_id: int, path: Path, caption: str | None = None) -> int:
        if self.fail_send:
            raise RuntimeError("telegram send failed")
        mid = self._id()
        self.sent.append(Sent("document", chat_id, mid, text=caption or "", path=path))
        return mid

    async def delete_message(self, chat_id: int, message_id: int) -> bool:
        if self.fail_delete:
            return False
        self.deleted.append((chat_id, message_id))
        return True

    async def edit_text(self, chat_id: int, message_id: int, text: str) -> None:
        self.edits.append((chat_id, message_id, text))

    # test helpers
    def texts(self) -> list[str]:
        return [s.text for s in self.sent if s.kind == "text"]

    def documents(self) -> list[Sent]:
        return [s for s in self.sent if s.kind == "document"]

    def last_text(self) -> str:
        return self.texts()[-1]


__all__ = ["Button", "FakeMessenger", "Messenger", "Sent"]

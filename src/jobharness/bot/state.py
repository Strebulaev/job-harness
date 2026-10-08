"""Persistent key/value JSON state for the bot (``bot_state`` table)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobharness.db.models import BotState


class StateStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def get(self, key: str, default: Any = None) -> Any:
        with self._sf() as s:
            row = s.execute(select(BotState).where(BotState.key == key)).scalar_one_or_none()
            return default if row is None else json.loads(row.value_json)

    def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value, sort_keys=True)
        with self._sf() as s:
            row = s.execute(select(BotState).where(BotState.key == key)).scalar_one_or_none()
            if row is None:
                s.add(BotState(key=key, value_json=payload))
            else:
                row.value_json = payload
            s.commit()

    def delete(self, key: str) -> None:
        with self._sf() as s:
            row = s.execute(select(BotState).where(BotState.key == key)).scalar_one_or_none()
            if row is not None:
                s.delete(row)
                s.commit()


__all__ = ["StateStore"]

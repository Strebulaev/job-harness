"""Fernet-encrypted secret store backed by the ``secrets`` table.

The master key comes from the host environment (``JH_MASTER_KEY``), never the
DB or repo. Plaintext is returned only by :meth:`SecretStore.get`; errors never
include secret values (guardrail provider-keys-never-persisted-in-clear).
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from jobharness.db.models import Secret

MASTER_KEY_ENV = "JH_MASTER_KEY"


class SecretError(Exception):
    """A secret operation failed (bad master key, undecryptable value)."""


def generate_master_key() -> str:
    return Fernet.generate_key().decode("ascii")


def master_key_from_env() -> str | None:
    return os.environ.get(MASTER_KEY_ENV) or None


def master_key_valid(key: str | None) -> bool:
    if not key:
        return False
    try:
        Fernet(key.encode("ascii"))
    except (ValueError, TypeError):
        return False
    return True


class SecretStore:
    def __init__(self, session_factory: sessionmaker[Session], master_key: str) -> None:
        if not master_key_valid(master_key):
            raise SecretError(f"{MASTER_KEY_ENV} is missing or not a valid Fernet key")
        self._sf = session_factory
        self._fernet = Fernet(master_key.encode("ascii"))

    def set(self, name: str, value: str) -> None:
        token = self._fernet.encrypt(value.encode("utf-8"))
        with self._sf() as s:
            row = s.execute(select(Secret).where(Secret.name == name)).scalar_one_or_none()
            if row is None:
                s.add(Secret(name=name, ciphertext=token))
            else:
                row.ciphertext = token
            s.commit()

    def get(self, name: str) -> str | None:
        with self._sf() as s:
            row = s.execute(select(Secret).where(Secret.name == name)).scalar_one_or_none()
            if row is None:
                return None
            token = row.ciphertext
        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except InvalidToken:
            raise SecretError(
                f"cannot decrypt secret {name!r}: wrong {MASTER_KEY_ENV}"
            ) from None

    def delete(self, name: str) -> bool:
        with self._sf() as s:
            row = s.execute(select(Secret).where(Secret.name == name)).scalar_one_or_none()
            if row is None:
                return False
            s.delete(row)
            s.commit()
            return True

    def status(self) -> dict[str, bool]:
        """Names of stored secrets mapped to True; never exposes values."""
        with self._sf() as s:
            return {n: True for n in s.execute(select(Secret.name)).scalars().all()}


__all__ = [
    "MASTER_KEY_ENV",
    "SecretError",
    "SecretStore",
    "generate_master_key",
    "master_key_from_env",
    "master_key_valid",
]

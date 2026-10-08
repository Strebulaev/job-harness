"""Step 3.4: encrypted secret store."""

from __future__ import annotations

import pytest

from jobharness.db.models import Secret
from jobharness.db.session import create_schema, init_session_factory, make_engine
from jobharness.secrets import SecretError, SecretStore, generate_master_key


@pytest.fixture
def sf(tmp_path):  # type: ignore[no-untyped-def]
    engine = make_engine(tmp_path / "t.db")
    create_schema(engine)
    factory = init_session_factory(engine)
    yield factory
    engine.dispose()


def test_round_trip_and_ciphertext_is_not_plaintext(sf) -> None:  # type: ignore[no-untyped-def]
    store = SecretStore(sf, generate_master_key())
    store.set("openrouter_api_key", "sk-or-PLAINTEXT-123")
    assert store.get("openrouter_api_key") == "sk-or-PLAINTEXT-123"
    with sf() as s:
        raw = s.query(Secret).one().ciphertext
    assert b"PLAINTEXT" not in raw


def test_overwrite_and_delete(sf) -> None:  # type: ignore[no-untyped-def]
    store = SecretStore(sf, generate_master_key())
    store.set("a", "one")
    store.set("a", "two")
    assert store.get("a") == "two"
    assert store.delete("a") is True and store.delete("a") is False
    assert store.get("a") is None


def test_wrong_master_key_fails_without_leaking(sf) -> None:  # type: ignore[no-untyped-def]
    SecretStore(sf, generate_master_key()).set("a", "very-secret-value")
    with pytest.raises(SecretError) as ei:
        SecretStore(sf, generate_master_key()).get("a")
    assert "very-secret-value" not in str(ei.value)


def test_status_has_names_only(sf) -> None:  # type: ignore[no-untyped-def]
    store = SecretStore(sf, generate_master_key())
    store.set("a", "hunter2")
    assert store.status() == {"a": True}


def test_invalid_master_key_rejected(sf) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SecretError):
        SecretStore(sf, "not-a-key")

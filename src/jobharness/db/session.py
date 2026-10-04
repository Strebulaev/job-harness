"""DB engine + session factory (SQLite WAL by default; portable to Postgres)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from jobharness.db.models import Base  # noqa: F401  (imported so autogen sees it)


def make_engine(db_path: str | Path = "./data/jobharness.db") -> Engine:
    """Create a SQLite engine with WAL mode enabled.

    The DB file's parent directory is created if missing. For Postgres, swap
    the URL; no SQLite-only features are used in business logic (spec §3).
    """
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{p.as_posix()}"
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()

    return engine


def create_schema(engine: Engine) -> None:
    """Create all tables (idempotent). Used by ``jh init`` as a fallback when
    Alembic is not run first. All 11 tables live on ``Base.metadata``."""
    Base.metadata.create_all(engine)


_SessionLocal: sessionmaker[Session] | None = None


def init_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Bind the global session factory to ``engine``. Call once at startup."""
    global _SessionLocal
    _SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    return _SessionLocal


def get_session() -> sessionmaker[Session]:
    if _SessionLocal is None:
        raise RuntimeError(
            "session factory not initialized — call init_session_factory(engine) first"
        )
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """A transactional scope: commits on success, rolls back on exception."""
    factory = get_session()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

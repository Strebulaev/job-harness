"""M1 integration test: schema creation + session factory + state machine on a real engine."""

from __future__ import annotations

from sqlalchemy import inspect

from jobharness.db.models import Application, Job
from jobharness.db.session import create_schema, init_session_factory, make_engine
from jobharness.db.state_machine import assert_transition

EXPECTED_TABLES = {
    "sources",
    "jobs",
    "documents",
    "applications",
    "contacts",
    "messages",
    "events",
    "followups",
    "contracts",
    "eval_runs",
    "llm_calls",
}


def test_all_11_tables_created(tmp_path):
    engine = make_engine(tmp_path / "test.db")
    create_schema(engine)
    tables = set(inspect(engine).get_table_names())
    missing = EXPECTED_TABLES - tables
    assert not missing, f"missing tables: {missing}"
    engine.dispose()


def test_job_insert_and_status(tmp_path):
    engine = make_engine(tmp_path / "test.db")
    create_schema(engine)
    factory = init_session_factory(engine)
    session = factory()
    job = Job(title="Senior Python Engineer", status="new", source=None)
    session.add(job)
    session.commit()
    assert job.id is not None
    assert job.status == "new"

    # legal transition
    assert_transition(job.status, "parsed", kind="job")
    job.status = "parsed"
    session.commit()
    assert job.status == "parsed"

    session.close()
    engine.dispose()


def test_application_roundtrip(tmp_path):
    engine = make_engine(tmp_path / "test.db")
    create_schema(engine)
    factory = init_session_factory(engine)
    session = factory()
    app_row = Application(status="queued")
    session.add(app_row)
    session.commit()
    assert app_row.status == "queued"
    assert_transition(app_row.status, "approved", kind="application")
    session.close()
    engine.dispose()

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from models.base import Base
from runtime.capabilities import CapabilityRegistry, CapabilityRunner
from runtime.loop import ScriptedDecisionProvider
from runtime.repositories import RuntimeRepository
from runtime.service import RuntimeCoreService
from runtime.tenant_context import TenantContext


NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)


@pytest.fixture
def engine():
    value = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(value)
    yield value
    Base.metadata.drop_all(value)
    value.dispose()


def _service(repository=None):
    return RuntimeCoreService(
        ScriptedDecisionProvider([]),
        CapabilityRunner(CapabilityRegistry()),
        repository=repository,
        clock=lambda: NOW,
    )


def test_initialize_run_atomically_persists_initial_bundle(engine):
    context = TenantContext("tenant-a", principal_id="user-1")
    repository = RuntimeRepository()
    with Session(engine) as session:
        state = _service(repository).initialize_run(
            session,
            context,
            "Run demo",
            runtime_run_id="run-1",
        )

    with Session(engine) as session:
        run = repository.get_run(session, context, "run-1")
        assert run is not None and run.status == "queued"
        assert state.version == 1
        assert [row.version for row in repository.list_state_snapshots(session, context, "run-1")] == [1]
        assert [row.sequence for row in repository.list_trace_events(session, context, "run-1")] == [1]
        audits = repository.list_audit_events(session, context, "run-1")
        assert [row.sequence for row in audits] == [1]
        assert audits[0].actor_id == "user-1"


def test_initialize_run_rolls_back_all_records_when_bundle_write_fails(engine):
    class FailingRepository(RuntimeRepository):
        def append_trace_event(self, session, context, event):
            raise RuntimeError("trace storage failed")

    context = TenantContext("tenant-a")
    with Session(engine) as session, pytest.raises(RuntimeError, match="trace storage failed"):
        _service(FailingRepository()).initialize_run(
            session,
            context,
            "Run demo",
            runtime_run_id="run-rollback",
        )

    with Session(engine) as session:
        assert RuntimeRepository().get_run(session, context, "run-rollback") is None

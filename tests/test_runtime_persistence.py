from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from models.base import Base
from runtime.repositories import (
    RuntimePersistenceError,
    RuntimeRecordNotFound,
    RuntimeRepository,
)
from runtime.tenant_context import TenantBoundaryError, TenantContext
from schemas.runtime import (
    ActionDecision,
    ActionKind,
    AgentStep,
    AgentStepStatus,
    AuditEvent,
    AuditOperation,
    AuditOutcome,
    CapabilityResult,
    CapabilityResultStatus,
    Run,
    RunStatus,
    StateSnapshot,
    TraceEvent,
    TraceEventKind,
)


NOW = datetime.now(timezone.utc)


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


def _run():
    return Run(
        runtime_run_id="runtime-run-1",
        tenant_id="tenant-a",
        goal="Run the demo capability",
        created_at=NOW,
        updated_at=NOW,
    )


def _state(version=1, status=RunStatus.QUEUED, results=None, latest_step_id=None):
    return StateSnapshot(
        snapshot_id=f"snapshot-{version}",
        runtime_run_id="runtime-run-1",
        tenant_id="tenant-a",
        version=version,
        goal="Run the demo capability",
        capability_results=results or [],
        status=status,
        latest_step_id=latest_step_id,
        updated_at=NOW,
    )


def _decision():
    return ActionDecision(
        action_id="action-1",
        runtime_run_id="runtime-run-1",
        tenant_id="tenant-a",
        action_kind=ActionKind.INVOKE_CAPABILITY,
        target="demo.echo",
        arguments={"value": "hello"},
        idempotency_key="runtime-run-1-step-1",
    )


def _result():
    return CapabilityResult(
        capability_name="demo.echo",
        runtime_run_id="runtime-run-1",
        tenant_id="tenant-a",
        execution_id="execution-1",
        idempotency_key="runtime-run-1-step-1",
        status=CapabilityResultStatus.SUCCEEDED,
        output={"echo": "hello"},
    )


def _pending_step():
    return AgentStep(
        step_id="step-1",
        runtime_run_id="runtime-run-1",
        tenant_id="tenant-a",
        step_index=1,
        idempotency_key="runtime-run-1-step-1",
        input_state_version=1,
        decision=_decision(),
        status=AgentStepStatus.RUNNING,
        started_at=NOW,
    )


def test_repository_persists_and_reloads_all_five_record_types(engine):
    context = TenantContext("tenant-a", principal_id="user-1")
    repository = RuntimeRepository()
    with Session(engine) as session, session.begin():
        repository.create_run(session, context, _run())
        repository.save_state_snapshot(session, context, _state())
        repository.create_agent_step(session, context, _pending_step())
        repository.append_trace_event(
            session,
            context,
            TraceEvent(
                event_id="trace-1",
                runtime_run_id="runtime-run-1",
                tenant_id="tenant-a",
                sequence=1,
                event_type=TraceEventKind.LIFECYCLE,
                occurred_at=NOW,
            ),
        )
        repository.append_audit_event(
            session,
            context,
            AuditEvent(
                audit_id="audit-1",
                runtime_run_id="runtime-run-1",
                tenant_id="tenant-a",
                sequence=1,
                actor_id="user-1",
                operation=AuditOperation.RUN_CREATED,
                target_type="run",
                target_id="runtime-run-1",
                outcome=AuditOutcome.SUCCEEDED,
                occurred_at=NOW,
            ),
        )

    with Session(engine) as new_session:
        assert repository.get_run(new_session, context, "runtime-run-1") is not None
        assert [row.version for row in repository.list_state_snapshots(new_session, context, "runtime-run-1")] == [1]
        assert [row.step_index for row in repository.list_agent_steps(new_session, context, "runtime-run-1")] == [1]
        assert [row.sequence for row in repository.list_trace_events(new_session, context, "runtime-run-1")] == [1]
        assert [row.sequence for row in repository.list_audit_events(new_session, context, "runtime-run-1")] == [1]


def test_agent_step_can_be_finalized_and_completed_result_is_immutable(engine):
    context = TenantContext("tenant-a")
    repository = RuntimeRepository()
    pending = _pending_step()
    completed = pending.model_copy(
        update={
            "output_state_version": 2,
            "capability_result": _result(),
            "status": AgentStepStatus.SUCCEEDED,
            "finished_at": NOW,
            "duration_ms": 1,
        }
    )
    with Session(engine) as session, session.begin():
        repository.create_run(session, context, _run())
        repository.create_agent_step(session, context, pending)
        record = repository.finalize_agent_step(session, context, completed)
        assert record.result_json["output"] == {"echo": "hello"}
        assert repository.finalize_agent_step(session, context, completed).id == record.id

        conflicting = completed.model_copy(update={"status": AgentStepStatus.FAILED})
        with pytest.raises(RuntimePersistenceError):
            repository.finalize_agent_step(session, context, conflicting)


def test_state_is_immutable_and_run_lifecycle_updates(engine):
    context = TenantContext("tenant-a")
    repository = RuntimeRepository()
    with Session(engine) as session, session.begin():
        repository.create_run(session, context, _run())
        repository.save_state_snapshot(session, context, _state())
        repository.update_run_status(
            session, context, "runtime-run-1", RunStatus.RUNNING, NOW
        )
        repository.update_run_status(
            session,
            context,
            "runtime-run-1",
            RunStatus.COMPLETED,
            NOW,
            "finished",
        )
        with pytest.raises(RuntimePersistenceError):
            repository.save_state_snapshot(session, context, _state())


def test_cross_tenant_reads_and_writes_are_denied(engine):
    owner = TenantContext("tenant-a")
    other = TenantContext("tenant-b")
    repository = RuntimeRepository()
    with Session(engine) as session, session.begin():
        repository.create_run(session, owner, _run())
        repository.save_state_snapshot(session, owner, _state())

    with Session(engine) as session:
        assert repository.get_run(session, other, "runtime-run-1") is None
        with pytest.raises(RuntimeRecordNotFound):
            repository.list_state_snapshots(session, other, "runtime-run-1")
        with pytest.raises(TenantBoundaryError):
            repository.create_agent_step(
                session,
                other,
                _pending_step(),
            )


def test_missing_tenant_context_is_rejected_before_persistence(engine):
    with Session(engine) as session, pytest.raises(TenantBoundaryError):
        RuntimeRepository().create_run(session, None, _run())

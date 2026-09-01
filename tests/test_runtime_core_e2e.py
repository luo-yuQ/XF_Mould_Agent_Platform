from datetime import datetime, timezone

import pytest
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from models.base import Base
from runtime.capabilities import (
    DEMO_CAPABILITY_NAME,
    CapabilityDefinition,
    CapabilityRegistry,
    CapabilityRunner,
    register_demo_capability,
)
from runtime.loop import ScriptedDecisionProvider
from runtime.repositories import RuntimeRepository
from runtime.service import RuntimeCoreService
from runtime.tenant_context import TenantContext
from schemas.runtime import (
    ActionDecision,
    ActionKind,
    AgentStep,
    AgentStepStatus,
    AuditOperation,
    CapabilityResult,
    RunStatus,
    StateSnapshot,
)


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


def _invoke(run_id="run-e2e", target=DEMO_CAPABILITY_NAME):
    return ActionDecision(
        action_id=f"{run_id}-action-1",
        runtime_run_id=run_id,
        tenant_id="tenant-a",
        action_kind=ActionKind.INVOKE_CAPABILITY,
        target=target,
        arguments={"value": "core"},
        idempotency_key=f"{run_id}-step-1",
    )


def _finish(run_id="run-e2e"):
    return ActionDecision(
        action_id=f"{run_id}-action-2",
        runtime_run_id=run_id,
        tenant_id="tenant-a",
        action_kind=ActionKind.FINISH,
        completion_requested=True,
        idempotency_key=f"{run_id}-step-2",
    )


def test_runtime_core_two_step_vertical_slice_is_durable_across_sessions(engine):
    registry = CapabilityRegistry()
    register_demo_capability(registry)
    provider = ScriptedDecisionProvider([_invoke(), _finish()])
    service = RuntimeCoreService(
        provider,
        CapabilityRunner(registry),
        clock=lambda: NOW,
    )
    context = TenantContext("tenant-a", principal_id="user-1")

    with Session(engine) as first_session:
        completed = service.execute(
            first_session,
            context,
            "Run the Core vertical slice",
            runtime_run_id="run-e2e",
        )
    assert completed.status is RunStatus.COMPLETED

    repository = RuntimeRepository()
    with Session(engine) as new_session:
        run = repository.get_run(new_session, context, "run-e2e")
        states = repository.list_state_snapshots(new_session, context, "run-e2e")
        steps = repository.list_agent_steps(new_session, context, "run-e2e")
        traces = repository.list_trace_events(new_session, context, "run-e2e")
        audits = repository.list_audit_events(new_session, context, "run-e2e")

        assert run is not None and run.status == RunStatus.COMPLETED.value
        assert [state.version for state in states] == [1, 2, 3]
        assert [StateSnapshot.model_validate(state.state_json).status for state in states] == [
            RunStatus.QUEUED,
            RunStatus.RUNNING,
            RunStatus.COMPLETED,
        ]
        assert [step.step_index for step in steps] == [1, 2]
        assert [step.action_kind for step in steps] == [
            ActionKind.INVOKE_CAPABILITY.value,
            ActionKind.FINISH.value,
        ]
        assert steps[0].result_json["output"] == {"echo": "core"}
        assert [trace.sequence for trace in traces] == list(range(1, len(traces) + 1))
        assert [audit.sequence for audit in audits] == list(range(1, len(audits) + 1))
        assert audits[-1].operation == AuditOperation.RUN_COMPLETED.value
        assert traces[0].__tablename__ == "runtime_trace_events"
        assert audits[0].__tablename__ == "runtime_audit_events"

    assert provider.observed_states[1].capability_results[0].output == {"echo": "core"}


def test_persisted_completed_step_reuses_result_without_second_invocation(engine):
    class CountInput(BaseModel):
        value: str

    calls = 0

    def handler(_context, arguments):
        nonlocal calls
        calls += 1
        return {"echo": arguments["value"]}

    registry = CapabilityRegistry()
    registry.register(CapabilityDefinition("demo.count", CountInput, handler))
    runner = CapabilityRunner(registry)
    context = TenantContext("tenant-a", principal_id="user-1")
    initializer = RuntimeCoreService(
        ScriptedDecisionProvider([]), runner, clock=lambda: NOW
    )
    repository = RuntimeRepository()
    decision = _invoke(run_id="run-idempotent", target="demo.count")
    pending = AgentStep(
        step_id="step-idempotent",
        runtime_run_id="run-idempotent",
        tenant_id="tenant-a",
        step_index=1,
        idempotency_key=decision.idempotency_key,
        input_state_version=1,
        decision=decision,
        status=AgentStepStatus.RUNNING,
        started_at=NOW,
    )

    with Session(engine) as first_session:
        initializer.initialize_run(
            first_session,
            context,
            "Count once",
            runtime_run_id="run-idempotent",
        )
        with first_session.begin():
            repository.create_agent_step(first_session, context, pending)
            first_result = runner.invoke(context, decision)
            completed = AgentStep(
                **{
                    **pending.model_dump(),
                    "output_state_version": 2,
                    "capability_result": first_result,
                    "status": AgentStepStatus.SUCCEEDED,
                    "finished_at": NOW,
                    "duration_ms": first_result.duration_ms,
                }
            )
            repository.finalize_agent_step(first_session, context, completed)

    with Session(engine) as new_session:
        persisted = repository.get_agent_step_by_idempotency(
            new_session,
            context,
            "run-idempotent",
            decision.idempotency_key,
        )
        assert persisted is not None
        persisted_result = CapabilityResult.model_validate(persisted.result_json)
        repeated = runner.invoke(context, decision, existing_result=persisted_result)
        same_step = repository.create_agent_step(new_session, context, pending)

    assert repeated == first_result
    assert same_step.step_id == "step-idempotent"
    assert calls == 1

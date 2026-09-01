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
    AgentStepStatus,
    CapabilityResult,
    CapabilityResultStatus,
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


def _invoke(run_id="run-1", target=DEMO_CAPABILITY_NAME, step=1, tenant="tenant-a"):
    return ActionDecision(
        action_id=f"action-{step}",
        runtime_run_id=run_id,
        tenant_id=tenant,
        action_kind=ActionKind.INVOKE_CAPABILITY,
        target=target,
        arguments={"value": f"hello-{step}"},
        idempotency_key=f"{run_id}-step-{step}",
    )


def _finish(run_id="run-1", step=2, tenant="tenant-a"):
    return ActionDecision(
        action_id=f"action-{step}",
        runtime_run_id=run_id,
        tenant_id=tenant,
        action_kind=ActionKind.FINISH,
        completion_requested=True,
        idempotency_key=f"{run_id}-step-{step}",
    )


def _service(decisions, *, registry=None, runner=None, max_steps=2):
    selected_registry = registry or CapabilityRegistry()
    if registry is None:
        register_demo_capability(selected_registry)
    return RuntimeCoreService(
        ScriptedDecisionProvider(decisions),
        runner or CapabilityRunner(selected_registry),
        max_steps=max_steps,
        clock=lambda: NOW,
    )


def test_step_one_persists_capability_result_and_running_state_v2(engine):
    context = TenantContext("tenant-a", principal_id="user-1")
    service = _service([_invoke(), _finish()])
    with Session(engine) as session:
        run = service.execute(session, context, "Echo a value", runtime_run_id="run-1")
    assert run.status is RunStatus.COMPLETED

    repository = RuntimeRepository()
    with Session(engine) as session:
        states = repository.list_state_snapshots(session, context, "run-1")
        steps = repository.list_agent_steps(session, context, "run-1")
        assert StateSnapshot.model_validate(states[1].state_json).status is RunStatus.RUNNING
        assert states[1].state_json["capability_results"][0]["output"] == {
            "echo": "hello-1"
        }
        assert steps[0].status == AgentStepStatus.SUCCEEDED.value
        assert steps[0].input_state_version == 1
        assert steps[0].output_state_version == 2
        assert steps[0].tenant_id == "tenant-a"
        assert steps[0].result_json["tenant_id"] == "tenant-a"
        assert [row.sequence for row in repository.list_trace_events(session, context, "run-1")] == list(
            range(1, 7)
        )
        assert [row.sequence for row in repository.list_audit_events(session, context, "run-1")] == [1, 2, 3]


def test_step_two_finish_persists_state_v3_and_completed_run(engine):
    context = TenantContext("tenant-a", principal_id="user-1")
    service = _service([_invoke(), _finish()])
    with Session(engine) as session:
        run = service.execute(session, context, "Echo a value", runtime_run_id="run-1")

    assert run.status is RunStatus.COMPLETED
    assert run.finished_at == NOW
    assert run.termination_reason == "finish"

    repository = RuntimeRepository()
    with Session(engine) as session:
        states = repository.list_state_snapshots(session, context, "run-1")
        steps = repository.list_agent_steps(session, context, "run-1")
        assert [row.version for row in states] == [1, 2, 3]
        assert StateSnapshot.model_validate(states[2].state_json).status is RunStatus.COMPLETED
        assert [row.step_index for row in steps] == [1, 2]
        assert steps[1].action_kind == ActionKind.FINISH.value
        assert steps[1].status == AgentStepStatus.SUCCEEDED.value
        assert steps[1].input_state_version == 2
        assert steps[1].output_state_version == 3


class RawDecisionProvider:
    def __init__(self, value):
        self.value = value

    def decide(self, _state, _step_index):
        return self.value


def test_malformed_or_unsupported_decision_fails_with_rejected_step(engine):
    context = TenantContext("tenant-a")
    registry = CapabilityRegistry()
    service = RuntimeCoreService(
        RawDecisionProvider(
            {
                "action_id": "bad-action",
                "runtime_run_id": "run-bad",
                "tenant_id": "tenant-a",
                "action_kind": "call-tool",
                "idempotency_key": "run-bad-step-1",
            }
        ),
        CapabilityRunner(registry),
        clock=lambda: NOW,
    )
    with Session(engine) as session:
        run = service.execute(session, context, "Reject tool", runtime_run_id="run-bad")

    assert run.status is RunStatus.FAILED
    assert run.termination_reason == "invalid_action_decision"
    with Session(engine) as session:
        steps = RuntimeRepository().list_agent_steps(session, context, "run-bad")
        assert len(steps) == 1
        assert steps[0].status == AgentStepStatus.REJECTED.value
        assert steps[0].decision_json["action_kind"] == "call-tool"


def test_unknown_capability_and_capability_error_fail_closed(engine):
    context = TenantContext("tenant-a")
    empty_registry = CapabilityRegistry()
    unknown_service = _service(
        [_invoke(run_id="run-unknown", target="missing.capability")],
        registry=empty_registry,
    )
    with Session(engine) as session:
        unknown = unknown_service.execute(
            session, context, "Unknown", runtime_run_id="run-unknown"
        )
    assert unknown.status is RunStatus.FAILED
    assert unknown.termination_reason == "unknown_capability"

    class InputModel(BaseModel):
        value: str

    failing_registry = CapabilityRegistry()

    def fail(_context, _arguments):
        raise RuntimeError("demo failure")

    failing_registry.register(CapabilityDefinition("demo.fail", InputModel, fail))
    failure_service = _service(
        [_invoke(run_id="run-error", target="demo.fail")],
        registry=failing_registry,
    )
    with Session(engine) as session:
        failed = failure_service.execute(
            session, context, "Fail", runtime_run_id="run-error"
        )
    assert failed.status is RunStatus.FAILED
    assert failed.termination_reason == "capability_execution_failed"


def test_mismatched_capability_result_tenant_is_rejected(engine):
    context = TenantContext("tenant-a")

    class MismatchedRunner:
        def invoke(self, _context, decision, existing_result=None):
            assert existing_result is None
            return CapabilityResult(
                capability_name=decision.target,
                runtime_run_id=decision.runtime_run_id,
                tenant_id="tenant-b",
                execution_id="bad-execution",
                idempotency_key=decision.idempotency_key,
                status=CapabilityResultStatus.SUCCEEDED,
                output={},
            )

    service = _service([_invoke(run_id="run-mismatch")], runner=MismatchedRunner())
    with Session(engine) as session:
        run = service.execute(
            session, context, "Reject mismatch", runtime_run_id="run-mismatch"
        )
    assert run.status is RunStatus.FAILED
    assert run.termination_reason == "capability_result_tenant_mismatch"


def test_max_steps_exhaustion_stops_without_an_extra_agent_step(engine):
    context = TenantContext("tenant-a")
    service = _service(
        [_invoke(run_id="run-max", step=1), _invoke(run_id="run-max", step=2)],
        max_steps=2,
    )
    with Session(engine) as session:
        run = service.execute(session, context, "Never finish", runtime_run_id="run-max")
    assert run.status is RunStatus.FAILED
    assert run.termination_reason == "max_steps_exhausted"

    with Session(engine) as session:
        repository = RuntimeRepository()
        assert len(repository.list_agent_steps(session, context, "run-max")) == 2
        assert repository.list_state_snapshots(session, context, "run-max")[-1].status == "failed"
        assert repository.list_trace_events(session, context, "run-max")[-1].event_type == "error"
        assert repository.list_audit_events(session, context, "run-max")[-1].operation == "run_failed"


def test_max_steps_must_be_positive():
    with pytest.raises(ValueError, match="max_steps must be positive"):
        _service([], max_steps=0)

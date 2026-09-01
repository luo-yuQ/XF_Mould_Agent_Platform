from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from runtime import (
    InvalidRunTransition,
    RunStateMachine,
    TenantBoundaryError,
    TenantContext,
    ensure_same_tenant,
    require_tenant_context,
)
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


def _invoke_decision(**overrides):
    payload = {
        "action_id": "action-1",
        "runtime_run_id": "runtime-run-1",
        "tenant_id": "tenant-a",
        "action_kind": ActionKind.INVOKE_CAPABILITY,
        "target": "demo.echo",
        "arguments": {"value": "hello"},
        "idempotency_key": "runtime-run-1-step-1",
    }
    payload.update(overrides)
    return ActionDecision(**payload)


def _capability_result(**overrides):
    payload = {
        "capability_name": "demo.echo",
        "runtime_run_id": "runtime-run-1",
        "tenant_id": "tenant-a",
        "execution_id": "execution-1",
        "idempotency_key": "runtime-run-1-step-1",
        "status": CapabilityResultStatus.SUCCEEDED,
        "output": {"echo": "hello"},
    }
    payload.update(overrides)
    return CapabilityResult(**payload)


def test_runtime_contracts_import_with_core_module_boundaries():
    import runtime.capabilities
    import runtime.loop
    import runtime.runs
    import runtime.state

    assert runtime.capabilities.__doc__
    assert runtime.loop.__doc__


def test_run_contract_requires_tenant_and_exposes_stable_runtime_identity():
    run = Run(
        runtime_run_id="runtime-run-1",
        tenant_id="tenant-a",
        goal="Inspect the current Runtime contract",
        created_at=NOW,
        updated_at=NOW,
    )

    assert run.runtime_run_id == "runtime-run-1"
    assert run.tenant_id == "tenant-a"
    assert run.schema_version == "runtime-core.v1"
    assert run.status is RunStatus.QUEUED

    with pytest.raises(ValidationError):
        Run(
            runtime_run_id="runtime-run-2",
            tenant_id="",
            goal="Missing tenant must fail",
            created_at=NOW,
            updated_at=NOW,
        )


def test_action_decision_accepts_only_core_actions_and_valid_shapes():
    invoke = _invoke_decision()
    finish = ActionDecision(
        action_id="action-2",
        runtime_run_id="runtime-run-1",
        tenant_id="tenant-a",
        action_kind=ActionKind.FINISH,
        completion_requested=True,
        idempotency_key="runtime-run-1-step-2",
    )

    assert invoke.action_kind is ActionKind.INVOKE_CAPABILITY
    assert finish.action_kind is ActionKind.FINISH

    with pytest.raises(ValidationError):
        _invoke_decision(action_kind="call-tool")
    with pytest.raises(ValidationError):
        _invoke_decision(target="")
    with pytest.raises(ValidationError):
        _invoke_decision(completion_requested=True)
    with pytest.raises(ValidationError):
        ActionDecision(
            action_id="action-2",
            runtime_run_id="runtime-run-1",
            tenant_id="tenant-a",
            action_kind=ActionKind.FINISH,
            completion_requested=False,
            idempotency_key="runtime-run-1-step-2",
        )


def test_capability_result_requires_structured_failure():
    result = _capability_result()
    assert result.output == {"echo": "hello"}

    with pytest.raises(ValidationError):
        _capability_result(status=CapabilityResultStatus.FAILED)
    with pytest.raises(ValidationError):
        _capability_result(error_code="unexpected", error_message="bad")


def test_agent_step_rejects_cross_run_or_cross_tenant_nested_records():
    decision = _invoke_decision()
    result = _capability_result()
    step = AgentStep(
        step_id="step-1",
        runtime_run_id="runtime-run-1",
        tenant_id="tenant-a",
        step_index=1,
        idempotency_key="runtime-run-1-step-1",
        input_state_version=1,
        output_state_version=2,
        decision=decision,
        capability_result=result,
        status=AgentStepStatus.SUCCEEDED,
        started_at=NOW,
        finished_at=NOW,
    )
    assert step.capability_result is not None

    with pytest.raises(ValidationError):
        AgentStep(**{**step.model_dump(), "decision": _invoke_decision(tenant_id="tenant-b")})
    with pytest.raises(ValidationError):
        AgentStep(
            **{
                **step.model_dump(),
                "capability_result": _capability_result(runtime_run_id="other-run"),
            }
        )


def test_state_rejects_cross_tenant_capability_result():
    with pytest.raises(ValidationError):
        StateSnapshot(
            snapshot_id="snapshot-2",
            runtime_run_id="runtime-run-1",
            tenant_id="tenant-a",
            version=2,
            goal="Run demo",
            capability_results=[_capability_result(tenant_id="tenant-b")],
            status=RunStatus.RUNNING,
            updated_at=NOW,
        )


def test_trace_and_audit_are_separate_tenant_bound_contracts():
    trace = TraceEvent(
        event_id="event-1",
        runtime_run_id="runtime-run-1",
        tenant_id="tenant-a",
        sequence=1,
        event_type=TraceEventKind.LIFECYCLE,
        occurred_at=NOW,
    )
    audit = AuditEvent(
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
    )
    assert trace.event_id != audit.audit_id
    assert trace.tenant_id == audit.tenant_id

    with pytest.raises(ValidationError):
        AuditEvent(**{**audit.model_dump(), "tenant_id": ""})


def test_all_persisted_runtime_contracts_require_tenant_id():
    for model in (Run, StateSnapshot, AgentStep, TraceEvent, AuditEvent):
        assert model.model_fields["tenant_id"].is_required(), model.__name__


def test_tenant_context_rejects_missing_and_cross_tenant_access():
    context = TenantContext(tenant_id=" tenant-a ", principal_id="user-1")

    assert context.tenant_id == "tenant-a"
    require_tenant_context(context)
    ensure_same_tenant(context, "tenant-a")

    with pytest.raises(TenantBoundaryError):
        require_tenant_context(None)
    with pytest.raises(TenantBoundaryError):
        ensure_same_tenant(context, "tenant-b")
    with pytest.raises(TenantBoundaryError):
        TenantContext(tenant_id="")
    with pytest.raises(TenantBoundaryError):
        TenantContext(tenant_id="tenant-a", principal_id=123)


def test_run_state_machine_allows_core_path_and_rejects_terminal_overwrite():
    assert RunStateMachine.transition(RunStatus.QUEUED, RunStatus.RUNNING) is RunStatus.RUNNING
    assert RunStateMachine.transition(RunStatus.RUNNING, RunStatus.COMPLETED) is RunStatus.COMPLETED
    assert RunStateMachine.transition(RunStatus.COMPLETED, RunStatus.COMPLETED) is RunStatus.COMPLETED

    with pytest.raises(InvalidRunTransition):
        RunStateMachine.transition(RunStatus.COMPLETED, RunStatus.RUNNING)
    with pytest.raises(InvalidRunTransition):
        RunStateMachine.transition(RunStatus.QUEUED, RunStatus.COMPLETED)

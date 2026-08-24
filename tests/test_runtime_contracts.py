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
    ActionResult,
    ActionResultStatus,
    Checkpoint,
    EvidenceReference,
    EvidenceSet,
    FileVersion,
    FileVersionStatus,
    IngestionJob,
    IngestionJobStatus,
    Run,
    RunStatus,
    StateSnapshot,
    ToolResult,
    TraceEvent,
    TraceEventKind,
)


NOW = datetime.now(timezone.utc)


def test_runtime_contracts_import_with_all_module_boundaries():
    import runtime.capabilities
    import runtime.context
    import runtime.events
    import runtime.knowledge
    import runtime.loop
    import runtime.runs
    import runtime.state
    import runtime.tools
    import runtime.workers

    assert runtime.capabilities.__doc__
    assert runtime.workers.__doc__


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
    assert run.schema_version == "runtime.v1"
    assert run.status is RunStatus.QUEUED

    with pytest.raises(ValidationError):
        Run(
            runtime_run_id="runtime-run-2",
            tenant_id="",
            goal="Missing tenant must fail",
            created_at=NOW,
            updated_at=NOW,
        )


def test_action_decision_and_result_are_versioned_and_normalized():
    decision = ActionDecision(
        action_id="action-1",
        runtime_run_id="runtime-run-1",
        tenant_id="tenant-a",
        action_kind=ActionKind.FINISH,
        decision_summary="The requested inspection is complete.",
        completion_requested=True,
        idempotency_key="runtime-run-1-action-1",
    )
    result = ActionResult(
        action_id=decision.action_id,
        runtime_run_id=decision.runtime_run_id,
        tenant_id=decision.tenant_id,
        action_kind=decision.action_kind,
        status=ActionResultStatus.SUCCEEDED,
        output={"completed": True},
        execution_id="execution-1",
        duration_ms=12,
    )

    assert decision.schema_version == "runtime.v1"
    assert result.status is ActionResultStatus.SUCCEEDED
    assert result.output == {"completed": True}

    with pytest.raises(ValidationError):
        ActionDecision(
            action_id="action-2",
            runtime_run_id="runtime-run-1",
            tenant_id="tenant-a",
            action_kind="unknown-action",
            idempotency_key="runtime-run-1-action-2",
        )


def test_all_runtime_records_require_tenant_id():
    runtime_models = (
        Run,
        ActionDecision,
        ActionResult,
        EvidenceReference,
        EvidenceSet,
        ToolResult,
        StateSnapshot,
        TraceEvent,
        Checkpoint,
        FileVersion,
        IngestionJob,
    )

    for model in runtime_models:
        assert model.model_fields["tenant_id"].is_required(), model.__name__


def test_state_and_trace_contracts_keep_runtime_identity_and_order():
    state = StateSnapshot(
        snapshot_id="snapshot-1",
        runtime_run_id="runtime-run-1",
        tenant_id="tenant-a",
        version=1,
        goal="Inspect the Runtime contract",
        status=RunStatus.RUNNING,
        updated_at=NOW,
    )
    event = TraceEvent(
        event_id="event-1",
        runtime_run_id=state.runtime_run_id,
        tenant_id=state.tenant_id,
        sequence=1,
        event_type=TraceEventKind.LIFECYCLE,
        payload={"status": RunStatus.RUNNING.value},
        occurred_at=NOW,
    )

    assert state.version == 1
    assert event.sequence == 1
    assert event.runtime_run_id == state.runtime_run_id


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


def test_run_state_machine_allows_expected_paths_and_rejects_terminal_overwrite():
    assert RunStateMachine.transition(RunStatus.QUEUED, RunStatus.RUNNING) is RunStatus.RUNNING
    assert RunStateMachine.transition(RunStatus.RUNNING, RunStatus.COMPLETED) is RunStatus.COMPLETED
    assert RunStateMachine.transition(RunStatus.COMPLETED, RunStatus.COMPLETED) is RunStatus.COMPLETED
    assert RunStateMachine.is_terminal(RunStatus.CANCELLED)

    with pytest.raises(InvalidRunTransition):
        RunStateMachine.transition(RunStatus.COMPLETED, RunStatus.RUNNING)
    with pytest.raises(InvalidRunTransition):
        RunStateMachine.transition(RunStatus.QUEUED, RunStatus.COMPLETED)

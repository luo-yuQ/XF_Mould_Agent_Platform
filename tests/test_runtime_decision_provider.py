from datetime import datetime, timezone

from runtime.loop import ScriptedDecisionProvider
from schemas.runtime import (
    ActionDecision,
    ActionKind,
    CapabilityResult,
    CapabilityResultStatus,
    RunStatus,
    StateSnapshot,
)


NOW = datetime.now(timezone.utc)


def test_scripted_provider_emits_invoke_then_finish_and_observes_state_update():
    invoke = ActionDecision(
        action_id="action-1",
        runtime_run_id="run-1",
        tenant_id="tenant-a",
        action_kind=ActionKind.INVOKE_CAPABILITY,
        target="demo.echo",
        arguments={"value": "hello"},
        idempotency_key="run-1-step-1",
    )
    finish = ActionDecision(
        action_id="action-2",
        runtime_run_id="run-1",
        tenant_id="tenant-a",
        action_kind=ActionKind.FINISH,
        completion_requested=True,
        idempotency_key="run-1-step-2",
    )
    provider = ScriptedDecisionProvider([invoke, finish])
    state_v1 = StateSnapshot(
        snapshot_id="snapshot-1",
        runtime_run_id="run-1",
        tenant_id="tenant-a",
        version=1,
        goal="Echo a value",
        status=RunStatus.QUEUED,
        updated_at=NOW,
    )

    assert provider.decide(state_v1, 1).action_kind is ActionKind.INVOKE_CAPABILITY

    result = CapabilityResult(
        capability_name="demo.echo",
        runtime_run_id="run-1",
        tenant_id="tenant-a",
        execution_id="execution-1",
        idempotency_key="run-1-step-1",
        status=CapabilityResultStatus.SUCCEEDED,
        output={"echo": "hello"},
    )
    state_v2 = StateSnapshot(
        snapshot_id="snapshot-2",
        runtime_run_id="run-1",
        tenant_id="tenant-a",
        version=2,
        goal="Echo a value",
        capability_results=[result],
        status=RunStatus.RUNNING,
        latest_step_id="step-1",
        updated_at=NOW,
    )

    assert provider.decide(state_v2, 2).action_kind is ActionKind.FINISH
    assert provider.observed_step_indexes == [1, 2]
    assert provider.observed_states[1].capability_results[0].output == {"echo": "hello"}

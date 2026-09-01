from runtime.capabilities import (
    DEMO_CAPABILITY_NAME,
    CapabilityRegistry,
    CapabilityRunner,
    register_demo_capability,
)
from runtime.tenant_context import TenantContext
from schemas.runtime import ActionDecision, ActionKind, CapabilityResultStatus


def test_demo_capability_returns_deterministic_tenant_bound_result():
    registry = CapabilityRegistry()
    register_demo_capability(registry)
    result = CapabilityRunner(registry).invoke(
        TenantContext("tenant-a"),
        ActionDecision(
            action_id="action-1",
            runtime_run_id="run-1",
            tenant_id="tenant-a",
            action_kind=ActionKind.INVOKE_CAPABILITY,
            target=DEMO_CAPABILITY_NAME,
            arguments={"value": "hello"},
            idempotency_key="run-1-step-1",
        ),
    )

    assert result.capability_name == DEMO_CAPABILITY_NAME
    assert result.tenant_id == "tenant-a"
    assert result.status is CapabilityResultStatus.SUCCEEDED
    assert result.output == {"echo": "hello"}

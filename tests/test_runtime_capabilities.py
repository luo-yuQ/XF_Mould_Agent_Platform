import pytest
from pydantic import BaseModel, Field

from runtime.capabilities import CapabilityDefinition, CapabilityRegistry, CapabilityRunner
from runtime.tenant_context import TenantBoundaryError, TenantContext
from schemas.runtime import ActionDecision, ActionKind, CapabilityResultStatus


class ValueInput(BaseModel):
    value: str = Field(min_length=1)


def _decision(**overrides):
    payload = {
        "action_id": "action-1",
        "runtime_run_id": "run-1",
        "tenant_id": "tenant-a",
        "action_kind": ActionKind.INVOKE_CAPABILITY,
        "target": "test.count",
        "arguments": {"value": "hello"},
        "idempotency_key": "run-1-step-1",
    }
    payload.update(overrides)
    return ActionDecision(**payload)


def test_runner_validates_and_normalizes_capability_result():
    calls = []

    def handler(context, arguments):
        calls.append((context.tenant_id, arguments))
        return {"echo": arguments["value"]}

    registry = CapabilityRegistry()
    registry.register(CapabilityDefinition("test.count", ValueInput, handler))
    result = CapabilityRunner(registry).invoke(TenantContext("tenant-a"), _decision())

    assert result.status is CapabilityResultStatus.SUCCEEDED
    assert result.output == {"echo": "hello"}
    assert calls == [("tenant-a", {"value": "hello"})]


def test_unknown_capability_and_invalid_arguments_fail_closed():
    registry = CapabilityRegistry()
    runner = CapabilityRunner(registry)
    unknown = runner.invoke(
        TenantContext("tenant-a"), _decision(target="missing.capability")
    )
    assert unknown.status is CapabilityResultStatus.FAILED
    assert unknown.error_code == "unknown_capability"

    registry.register(CapabilityDefinition("test.count", ValueInput, lambda *_: {}))
    invalid = runner.invoke(
        TenantContext("tenant-a"), _decision(arguments={"value": ""})
    )
    assert invalid.status is CapabilityResultStatus.FAILED
    assert invalid.error_code == "invalid_capability_arguments"


def test_existing_completed_result_is_reused_without_invocation():
    call_count = 0

    def handler(_context, arguments):
        nonlocal call_count
        call_count += 1
        return arguments

    registry = CapabilityRegistry()
    registry.register(CapabilityDefinition("test.count", ValueInput, handler))
    runner = CapabilityRunner(registry)
    decision = _decision()
    first = runner.invoke(TenantContext("tenant-a"), decision)
    second = runner.invoke(TenantContext("tenant-a"), decision, existing_result=first)

    assert second == first
    assert call_count == 1


def test_runner_rejects_cross_tenant_before_dispatch():
    called = False

    def handler(_context, _arguments):
        nonlocal called
        called = True
        return {}

    registry = CapabilityRegistry()
    registry.register(CapabilityDefinition("test.count", ValueInput, handler))

    with pytest.raises(TenantBoundaryError):
        CapabilityRunner(registry).invoke(TenantContext("tenant-b"), _decision())
    assert called is False

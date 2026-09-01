"""Capability registry and normalized synchronous runner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from runtime.tenant_context import TenantContext, ensure_same_tenant, require_tenant_context
from schemas.runtime import (
    ActionDecision,
    ActionKind,
    CapabilityResult,
    CapabilityResultStatus,
)


CapabilityOutput = dict[str, Any] | list[Any] | str | None
CapabilityHandler = Callable[[TenantContext, dict[str, Any]], CapabilityOutput]


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """One registered capability contract and its local handler."""

    name: str
    input_schema: type[BaseModel]
    handler: CapabilityHandler

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("capability name is required")


class CapabilityRegistry:
    """In-process registry for explicitly allowed Core capabilities."""

    def __init__(self) -> None:
        self._definitions: dict[str, CapabilityDefinition] = {}

    def register(self, definition: CapabilityDefinition) -> None:
        if definition.name in self._definitions:
            raise ValueError(f"capability already registered: {definition.name}")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> CapabilityDefinition | None:
        return self._definitions.get(name)


class CapabilityRunner:
    """Validates and invokes one local capability, normalizing every result."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    @staticmethod
    def _failed(
        decision: ActionDecision,
        error_code: str,
        error_message: str,
        duration_ms: int = 0,
    ) -> CapabilityResult:
        return CapabilityResult(
            capability_name=decision.target,
            runtime_run_id=decision.runtime_run_id,
            tenant_id=decision.tenant_id,
            execution_id=f"execution-{uuid4()}",
            idempotency_key=decision.idempotency_key,
            status=CapabilityResultStatus.FAILED,
            error_code=error_code,
            error_message=error_message[:1000],
            duration_ms=duration_ms,
        )

    def invoke(
        self,
        context: TenantContext,
        decision: ActionDecision,
        existing_result: CapabilityResult | None = None,
    ) -> CapabilityResult:
        context = require_tenant_context(context)
        ensure_same_tenant(context, decision.tenant_id)
        if decision.action_kind is not ActionKind.INVOKE_CAPABILITY:
            raise ValueError("CapabilityRunner accepts only invoke-capability")

        if existing_result is not None:
            ensure_same_tenant(context, existing_result.tenant_id)
            if (
                existing_result.runtime_run_id != decision.runtime_run_id
                or existing_result.capability_name != decision.target
                or existing_result.idempotency_key != decision.idempotency_key
            ):
                raise ValueError("persisted CapabilityResult does not match decision")
            return existing_result

        definition = self.registry.get(decision.target)
        if definition is None:
            return self._failed(
                decision,
                "unknown_capability",
                f"capability is not registered: {decision.target}",
            )

        try:
            validated = definition.input_schema.model_validate(decision.arguments)
        except ValidationError as exc:
            return self._failed(decision, "invalid_capability_arguments", str(exc))

        started = perf_counter()
        try:
            output = definition.handler(context, validated.model_dump(mode="python"))
        except Exception as exc:  # capability failures are normalized at this boundary
            duration_ms = max(0, int((perf_counter() - started) * 1000))
            return self._failed(decision, "capability_execution_failed", str(exc), duration_ms)

        duration_ms = max(0, int((perf_counter() - started) * 1000))
        return CapabilityResult(
            capability_name=decision.target,
            runtime_run_id=decision.runtime_run_id,
            tenant_id=decision.tenant_id,
            execution_id=f"execution-{uuid4()}",
            idempotency_key=decision.idempotency_key,
            status=CapabilityResultStatus.SUCCEEDED,
            output=output,
            duration_ms=duration_ms,
        )

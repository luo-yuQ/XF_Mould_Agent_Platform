"""Versioned contracts for the synchronous Agent Runtime Core."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


TenantId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
OpaqueId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
GoalText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class RuntimeModel(BaseModel):
    """Shared strict configuration for persisted Runtime contracts."""

    model_config = ConfigDict(extra="forbid")


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ActionKind(str, Enum):
    INVOKE_CAPABILITY = "invoke-capability"
    FINISH = "finish"


class CapabilityResultStatus(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AgentStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"


class TraceEventKind(str, Enum):
    LIFECYCLE = "lifecycle"
    ACTION_DECISION = "action_decision"
    CAPABILITY_RESULT = "capability_result"
    STATE_UPDATED = "state_updated"
    ERROR = "error"


class AuditOperation(str, Enum):
    RUN_CREATED = "run_created"
    CAPABILITY_INVOKED = "capability_invoked"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class AuditOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED = "rejected"


class Run(RuntimeModel):
    """Durable identity and lifecycle state of one Core execution."""

    schema_version: str = "runtime-core.v1"
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    goal: GoalText
    status: RunStatus = RunStatus.QUEUED
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    termination_reason: ShortText | None = None


class ActionDecision(RuntimeModel):
    """Validated request for the next and only Core action kinds."""

    schema_version: str = "runtime-core.v1"
    action_id: OpaqueId
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    action_kind: ActionKind
    target: ShortText = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    decision_summary: ShortText = ""
    expected_outcome: ShortText = ""
    completion_requested: bool = False
    idempotency_key: OpaqueId

    @model_validator(mode="after")
    def validate_action_shape(self) -> ActionDecision:
        if self.action_kind is ActionKind.INVOKE_CAPABILITY:
            if not self.target:
                raise ValueError("invoke-capability requires a target")
            if self.completion_requested:
                raise ValueError("invoke-capability cannot request completion")
        elif self.action_kind is ActionKind.FINISH:
            if self.target:
                raise ValueError("finish cannot specify a target")
            if self.arguments:
                raise ValueError("finish cannot specify arguments")
            if not self.completion_requested:
                raise ValueError("finish must request completion")
        return self


class CapabilityResult(RuntimeModel):
    """Normalized result returned by the Core Capability Runner."""

    schema_version: str = "runtime-core.v1"
    capability_name: OpaqueId
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    execution_id: OpaqueId
    idempotency_key: OpaqueId
    status: CapabilityResultStatus
    output: dict[str, Any] | list[Any] | str | None = None
    error_code: ShortText | None = None
    error_message: ShortText | None = None
    duration_ms: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_result_shape(self) -> CapabilityResult:
        if self.status is CapabilityResultStatus.SUCCEEDED:
            if self.error_code is not None or self.error_message is not None:
                raise ValueError("successful capability result cannot contain an error")
        elif self.error_code is None:
            raise ValueError("failed capability result requires error_code")
        return self


class StateSnapshot(RuntimeModel):
    """Immutable canonical State at a durable Core boundary."""

    schema_version: str = "runtime-core.v1"
    snapshot_id: OpaqueId
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    version: int = Field(ge=1)
    goal: GoalText
    capability_results: list[CapabilityResult] = Field(default_factory=list)
    status: RunStatus
    latest_step_id: OpaqueId | None = None
    termination_reason: ShortText | None = None
    updated_at: datetime

    @model_validator(mode="after")
    def validate_nested_results(self) -> StateSnapshot:
        for result in self.capability_results:
            if result.runtime_run_id != self.runtime_run_id:
                raise ValueError("capability result belongs to another Run")
            if result.tenant_id != self.tenant_id:
                raise ValueError("capability result belongs to another tenant")
        return self


class AgentStep(RuntimeModel):
    """One ordered decision and result iteration in a Runtime Run."""

    schema_version: str = "runtime-core.v1"
    step_id: OpaqueId
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    step_index: int = Field(ge=1)
    idempotency_key: OpaqueId
    input_state_version: int = Field(ge=1)
    output_state_version: int | None = Field(default=None, ge=1)
    decision: ActionDecision
    capability_result: CapabilityResult | None = None
    status: AgentStepStatus = AgentStepStatus.PENDING
    error_code: ShortText | None = None
    error_message: ShortText | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_step_identity(self) -> AgentStep:
        if self.decision.runtime_run_id != self.runtime_run_id:
            raise ValueError("decision belongs to another Run")
        if self.decision.tenant_id != self.tenant_id:
            raise ValueError("decision belongs to another tenant")
        if self.decision.idempotency_key != self.idempotency_key:
            raise ValueError("decision idempotency key does not match AgentStep")
        if self.capability_result is not None:
            result = self.capability_result
            if result.runtime_run_id != self.runtime_run_id:
                raise ValueError("capability result belongs to another Run")
            if result.tenant_id != self.tenant_id:
                raise ValueError("capability result belongs to another tenant")
            if result.idempotency_key != self.idempotency_key:
                raise ValueError("capability result idempotency key does not match AgentStep")
        if self.decision.action_kind is ActionKind.FINISH and self.capability_result is not None:
            raise ValueError("finish AgentStep cannot contain a CapabilityResult")
        if (
            self.decision.action_kind is ActionKind.INVOKE_CAPABILITY
            and self.status is AgentStepStatus.SUCCEEDED
            and self.capability_result is None
        ):
            raise ValueError("successful capability AgentStep requires a CapabilityResult")
        return self


class TraceEvent(RuntimeModel):
    """Append-only operational event for diagnosis and Run observation."""

    schema_version: str = "runtime-core.v1"
    event_id: OpaqueId
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    sequence: int = Field(ge=1)
    event_type: TraceEventKind
    step_id: OpaqueId | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class AuditEvent(RuntimeModel):
    """Append-only attributable Runtime operation without hidden reasoning."""

    schema_version: str = "runtime-core.v1"
    audit_id: OpaqueId
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    sequence: int = Field(ge=1)
    actor_id: OpaqueId
    operation: AuditOperation
    target_type: OpaqueId
    target_id: OpaqueId
    outcome: AuditOutcome
    step_id: OpaqueId | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime

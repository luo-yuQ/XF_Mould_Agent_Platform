"""Versioned contracts for the domain-neutral Agent Runtime.

These models describe the Runtime boundary only. They intentionally do not
reuse business-artifact run identifiers or the existing LangGraph state.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


TenantId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
OpaqueId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=128),
]
ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=1000),
]
GoalText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]


class RuntimeModel(BaseModel):
    """Shared Pydantic configuration for Runtime contracts."""

    model_config = ConfigDict(extra="forbid")


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_USER = "waiting_for_user"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ActionKind(str, Enum):
    RESPOND = "respond"
    ASK_USER = "ask-user"
    RETRIEVE_EVIDENCE = "retrieve-evidence"
    INVOKE_CAPABILITY = "invoke-capability"
    CALL_TOOL = "call-tool"
    WAIT_APPROVAL = "wait-approval"
    FINISH = "finish"


class ActionResultStatus(str, Enum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"


class TraceEventKind(str, Enum):
    LIFECYCLE = "lifecycle"
    ACTION_DECISION = "action_decision"
    ACTION_RESULT = "action_result"
    CHECKPOINT = "checkpoint"
    ERROR = "error"
    USER_INTERACTION = "user_interaction"


class FileVersionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class IngestionJobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Run(RuntimeModel):
    """The externally visible identity and lifecycle state of one Runtime Run."""

    schema_version: str = "runtime.v1"
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    goal: GoalText
    input_refs: list[OpaqueId] = Field(default_factory=list)
    session_id: OpaqueId | None = None
    status: RunStatus = RunStatus.QUEUED
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    termination_reason: ShortText | None = None


class ActionDecision(RuntimeModel):
    """A validated, bounded request for the next Runtime action."""

    schema_version: str = "runtime.v1"
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


class ActionResult(RuntimeModel):
    """Normalized outcome of a Runtime action."""

    schema_version: str = "runtime.v1"
    action_id: OpaqueId
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    action_kind: ActionKind
    target: ShortText = ""
    status: ActionResultStatus
    output: dict[str, Any] | list[Any] | str | None = None
    error_code: ShortText | None = None
    error_message: ShortText | None = None
    execution_id: OpaqueId | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class EvidenceReference(RuntimeModel):
    """Traceable source reference attached to retrieved evidence."""

    evidence_id: OpaqueId
    tenant_id: TenantId
    source_id: OpaqueId
    document_id: OpaqueId | None = None
    document_version_id: OpaqueId | None = None
    location: ShortText = ""


class EvidenceSet(RuntimeModel):
    """Evidence returned by Knowledge services, not an opaque text blob."""

    schema_version: str = "runtime.v1"
    query: GoalText
    tenant_id: TenantId
    items: list[EvidenceReference] = Field(default_factory=list)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResult(RuntimeModel):
    """Normalized result shape reserved for the later ToolExecutor boundary."""

    schema_version: str = "runtime.v1"
    tool_name: OpaqueId
    tenant_id: TenantId
    execution_id: OpaqueId
    success: bool
    output: dict[str, Any] | list[Any] | str | None = None
    error_code: ShortText | None = None
    error_message: ShortText | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    side_effects: dict[str, Any] = Field(default_factory=dict)


class StateSnapshot(RuntimeModel):
    """Canonical current-Run state; prompt Context is derived later."""

    schema_version: str = "runtime.v1"
    snapshot_id: OpaqueId
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    version: int = Field(ge=1)
    goal: GoalText
    constraints: list[ShortText] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    action_results: list[ActionResult] = Field(default_factory=list)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    status: RunStatus
    latest_action_id: OpaqueId | None = None
    termination_reason: ShortText | None = None
    updated_at: datetime


class TraceEvent(RuntimeModel):
    """Append-only observable Runtime event."""

    schema_version: str = "runtime.v1"
    event_id: OpaqueId
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    sequence: int = Field(ge=1)
    event_type: TraceEventKind
    action_id: OpaqueId | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class Checkpoint(RuntimeModel):
    """Resume boundary for an action execution."""

    schema_version: str = "runtime.v1"
    checkpoint_id: OpaqueId
    runtime_run_id: OpaqueId
    tenant_id: TenantId
    state_version: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    last_action_id: OpaqueId | None = None
    resume_token: OpaqueId
    created_at: datetime


class FileVersion(RuntimeModel):
    """Metadata contract for a future tenant-scoped knowledge file version."""

    schema_version: str = "runtime.v1"
    file_id: OpaqueId
    file_version_id: OpaqueId
    tenant_id: TenantId
    filename: ShortText
    media_type: ShortText
    size_bytes: int = Field(ge=0)
    status: FileVersionStatus
    storage_key: OpaqueId


class IngestionJob(RuntimeModel):
    """Metadata contract for a future asynchronous knowledge ingestion job."""

    schema_version: str = "runtime.v1"
    ingestion_job_id: OpaqueId
    file_id: OpaqueId
    file_version_id: OpaqueId
    tenant_id: TenantId
    status: IngestionJobStatus
    error_code: ShortText | None = None
    error_message: ShortText | None = None
    progress_percent: int = Field(default=0, ge=0, le=100)

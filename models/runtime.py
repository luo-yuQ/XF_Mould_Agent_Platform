"""SQLAlchemy persistence models for the synchronous Agent Runtime Core."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from models.base import Base
from time_utils import utc_now


_RUN_STATUS_CHECK = "status IN ('queued', 'running', 'completed', 'failed')"


class RuntimeRun(Base):
    """Durable identity and lifecycle record for one Core execution."""

    __tablename__ = "runtime_runs"
    __table_args__ = (CheckConstraint(_RUN_STATUS_CHECK, name="ck_runtime_runs_status"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    runtime_run_id = Column(String(128), nullable=False, unique=True, index=True)
    tenant_id = Column(String(128), nullable=False, index=True)
    goal = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="queued")
    termination_reason = Column(String(1000), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)


Index("ix_runtime_runs_tenant_created", RuntimeRun.tenant_id, RuntimeRun.created_at)
Index("ix_runtime_runs_tenant_status", RuntimeRun.tenant_id, RuntimeRun.status)


class RuntimeStateSnapshot(Base):
    """Immutable version of canonical State for one Runtime Run."""

    __tablename__ = "runtime_state_snapshots"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_runtime_state_snapshots_version"),
        CheckConstraint(_RUN_STATUS_CHECK, name="ck_runtime_state_snapshots_status"),
        UniqueConstraint(
            "runtime_run_id", "version", name="uq_runtime_state_snapshots_run_version"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(String(128), nullable=False, unique=True, index=True)
    runtime_run_id = Column(
        String(128),
        ForeignKey("runtime_runs.runtime_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(String(128), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False)
    state_json = Column(JSON, nullable=False)
    termination_reason = Column(String(1000), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)


Index(
    "ix_runtime_state_snapshots_tenant_run_version",
    RuntimeStateSnapshot.tenant_id,
    RuntimeStateSnapshot.runtime_run_id,
    RuntimeStateSnapshot.version,
)


class RuntimeAgentStep(Base):
    """One ordered and idempotent Agent decision/result iteration."""

    __tablename__ = "runtime_agent_steps"
    __table_args__ = (
        CheckConstraint("step_index >= 1", name="ck_runtime_agent_steps_step_index"),
        CheckConstraint(
            "input_state_version >= 1",
            name="ck_runtime_agent_steps_input_state_version",
        ),
        CheckConstraint(
            "output_state_version IS NULL OR output_state_version >= 1",
            name="ck_runtime_agent_steps_output_state_version",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'rejected', 'failed')",
            name="ck_runtime_agent_steps_status",
        ),
        UniqueConstraint(
            "runtime_run_id", "step_index", name="uq_runtime_agent_steps_run_index"
        ),
        UniqueConstraint(
            "runtime_run_id",
            "idempotency_key",
            name="uq_runtime_agent_steps_run_idempotency",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    step_id = Column(String(128), nullable=False, unique=True, index=True)
    runtime_run_id = Column(
        String(128),
        ForeignKey("runtime_runs.runtime_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(String(128), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    idempotency_key = Column(String(128), nullable=False)
    input_state_version = Column(Integer, nullable=False)
    output_state_version = Column(Integer, nullable=True)
    action_kind = Column(String(64), nullable=False)
    target = Column(String(1000), nullable=False, default="")
    decision_json = Column(JSON, nullable=False)
    result_json = Column(JSON, nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    error_code = Column(String(1000), nullable=True)
    error_message = Column(String(1000), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )


Index(
    "ix_runtime_agent_steps_tenant_run_index",
    RuntimeAgentStep.tenant_id,
    RuntimeAgentStep.runtime_run_id,
    RuntimeAgentStep.step_index,
)


class RuntimeTraceEvent(Base):
    """Append-only operational event for one Runtime Run."""

    __tablename__ = "runtime_trace_events"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="ck_runtime_trace_events_sequence"),
        UniqueConstraint(
            "runtime_run_id", "sequence", name="uq_runtime_trace_events_run_sequence"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(128), nullable=False, unique=True, index=True)
    runtime_run_id = Column(
        String(128),
        ForeignKey("runtime_runs.runtime_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(String(128), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String(64), nullable=False)
    step_id = Column(String(128), nullable=True, index=True)
    payload_json = Column(JSON, nullable=False, default=dict)
    occurred_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)


Index(
    "ix_runtime_trace_events_tenant_run_sequence",
    RuntimeTraceEvent.tenant_id,
    RuntimeTraceEvent.runtime_run_id,
    RuntimeTraceEvent.sequence,
)


class RuntimeAuditEvent(Base):
    """Append-only attributable operation record, separate from Trace."""

    __tablename__ = "runtime_audit_events"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="ck_runtime_audit_events_sequence"),
        CheckConstraint(
            "outcome IN ('succeeded', 'failed', 'rejected')",
            name="ck_runtime_audit_events_outcome",
        ),
        UniqueConstraint(
            "runtime_run_id", "sequence", name="uq_runtime_audit_events_run_sequence"
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    audit_id = Column(String(128), nullable=False, unique=True, index=True)
    runtime_run_id = Column(
        String(128),
        ForeignKey("runtime_runs.runtime_run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(String(128), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    actor_id = Column(String(128), nullable=False, index=True)
    operation = Column(String(64), nullable=False)
    target_type = Column(String(128), nullable=False)
    target_id = Column(String(128), nullable=False)
    outcome = Column(String(32), nullable=False)
    step_id = Column(String(128), nullable=True, index=True)
    metadata_json = Column(JSON, nullable=False, default=dict)
    occurred_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)


Index(
    "ix_runtime_audit_events_tenant_run_sequence",
    RuntimeAuditEvent.tenant_id,
    RuntimeAuditEvent.runtime_run_id,
    RuntimeAuditEvent.sequence,
)

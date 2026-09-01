"""create synchronous Agent Runtime Core tables

Revision ID: 011
Revises: 010
Create Date: 2026-08-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_RUN_STATUS_CHECK = "status IN ('queued', 'running', 'completed', 'failed')"


def upgrade() -> None:
    op.create_table(
        "runtime_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("runtime_run_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="queued", nullable=False),
        sa.Column("termination_reason", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_RUN_STATUS_CHECK, name="ck_runtime_runs_status"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("runtime_run_id"),
    )
    op.create_index("ix_runtime_runs_runtime_run_id", "runtime_runs", ["runtime_run_id"])
    op.create_index("ix_runtime_runs_tenant_id", "runtime_runs", ["tenant_id"])
    op.create_index("ix_runtime_runs_created_at", "runtime_runs", ["created_at"])
    op.create_index("ix_runtime_runs_tenant_created", "runtime_runs", ["tenant_id", "created_at"])
    op.create_index("ix_runtime_runs_tenant_status", "runtime_runs", ["tenant_id", "status"])

    op.create_table(
        "runtime_state_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("snapshot_id", sa.String(length=128), nullable=False),
        sa.Column("runtime_run_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("state_json", sa.JSON(), nullable=False),
        sa.Column("termination_reason", sa.String(length=1000), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint("version >= 1", name="ck_runtime_state_snapshots_version"),
        sa.CheckConstraint(_RUN_STATUS_CHECK, name="ck_runtime_state_snapshots_status"),
        sa.ForeignKeyConstraint(["runtime_run_id"], ["runtime_runs.runtime_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id"),
        sa.UniqueConstraint("runtime_run_id", "version", name="uq_runtime_state_snapshots_run_version"),
    )
    op.create_index("ix_runtime_state_snapshots_snapshot_id", "runtime_state_snapshots", ["snapshot_id"])
    op.create_index("ix_runtime_state_snapshots_runtime_run_id", "runtime_state_snapshots", ["runtime_run_id"])
    op.create_index("ix_runtime_state_snapshots_tenant_id", "runtime_state_snapshots", ["tenant_id"])
    op.create_index("ix_runtime_state_snapshots_created_at", "runtime_state_snapshots", ["created_at"])
    op.create_index(
        "ix_runtime_state_snapshots_tenant_run_version",
        "runtime_state_snapshots",
        ["tenant_id", "runtime_run_id", "version"],
    )

    op.create_table(
        "runtime_agent_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("step_id", sa.String(length=128), nullable=False),
        sa.Column("runtime_run_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("input_state_version", sa.Integer(), nullable=False),
        sa.Column("output_state_version", sa.Integer(), nullable=True),
        sa.Column("action_kind", sa.String(length=64), nullable=False),
        sa.Column("target", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("decision_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("error_code", sa.String(length=1000), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint("step_index >= 1", name="ck_runtime_agent_steps_step_index"),
        sa.CheckConstraint("input_state_version >= 1", name="ck_runtime_agent_steps_input_state_version"),
        sa.CheckConstraint(
            "output_state_version IS NULL OR output_state_version >= 1",
            name="ck_runtime_agent_steps_output_state_version",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'rejected', 'failed')",
            name="ck_runtime_agent_steps_status",
        ),
        sa.ForeignKeyConstraint(["runtime_run_id"], ["runtime_runs.runtime_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("step_id"),
        sa.UniqueConstraint("runtime_run_id", "step_index", name="uq_runtime_agent_steps_run_index"),
        sa.UniqueConstraint(
            "runtime_run_id", "idempotency_key", name="uq_runtime_agent_steps_run_idempotency"
        ),
    )
    op.create_index("ix_runtime_agent_steps_step_id", "runtime_agent_steps", ["step_id"])
    op.create_index("ix_runtime_agent_steps_runtime_run_id", "runtime_agent_steps", ["runtime_run_id"])
    op.create_index("ix_runtime_agent_steps_tenant_id", "runtime_agent_steps", ["tenant_id"])
    op.create_index("ix_runtime_agent_steps_created_at", "runtime_agent_steps", ["created_at"])
    op.create_index(
        "ix_runtime_agent_steps_tenant_run_index",
        "runtime_agent_steps",
        ["tenant_id", "runtime_run_id", "step_index"],
    )

    op.create_table(
        "runtime_trace_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("runtime_run_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("step_id", sa.String(length=128), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_runtime_trace_events_sequence"),
        sa.ForeignKeyConstraint(["runtime_run_id"], ["runtime_runs.runtime_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
        sa.UniqueConstraint("runtime_run_id", "sequence", name="uq_runtime_trace_events_run_sequence"),
    )
    op.create_index("ix_runtime_trace_events_event_id", "runtime_trace_events", ["event_id"])
    op.create_index("ix_runtime_trace_events_runtime_run_id", "runtime_trace_events", ["runtime_run_id"])
    op.create_index("ix_runtime_trace_events_tenant_id", "runtime_trace_events", ["tenant_id"])
    op.create_index("ix_runtime_trace_events_step_id", "runtime_trace_events", ["step_id"])
    op.create_index("ix_runtime_trace_events_occurred_at", "runtime_trace_events", ["occurred_at"])
    op.create_index(
        "ix_runtime_trace_events_tenant_run_sequence",
        "runtime_trace_events",
        ["tenant_id", "runtime_run_id", "sequence"],
    )

    op.create_table(
        "runtime_audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audit_id", sa.String(length=128), nullable=False),
        sa.Column("runtime_run_id", sa.String(length=128), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=128), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("step_id", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_runtime_audit_events_sequence"),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'failed', 'rejected')", name="ck_runtime_audit_events_outcome"
        ),
        sa.ForeignKeyConstraint(["runtime_run_id"], ["runtime_runs.runtime_run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_id"),
        sa.UniqueConstraint("runtime_run_id", "sequence", name="uq_runtime_audit_events_run_sequence"),
    )
    op.create_index("ix_runtime_audit_events_audit_id", "runtime_audit_events", ["audit_id"])
    op.create_index("ix_runtime_audit_events_runtime_run_id", "runtime_audit_events", ["runtime_run_id"])
    op.create_index("ix_runtime_audit_events_tenant_id", "runtime_audit_events", ["tenant_id"])
    op.create_index("ix_runtime_audit_events_actor_id", "runtime_audit_events", ["actor_id"])
    op.create_index("ix_runtime_audit_events_step_id", "runtime_audit_events", ["step_id"])
    op.create_index("ix_runtime_audit_events_occurred_at", "runtime_audit_events", ["occurred_at"])
    op.create_index(
        "ix_runtime_audit_events_tenant_run_sequence",
        "runtime_audit_events",
        ["tenant_id", "runtime_run_id", "sequence"],
    )


def downgrade() -> None:
    for index_name in (
        "ix_runtime_audit_events_tenant_run_sequence",
        "ix_runtime_audit_events_occurred_at",
        "ix_runtime_audit_events_step_id",
        "ix_runtime_audit_events_actor_id",
        "ix_runtime_audit_events_tenant_id",
        "ix_runtime_audit_events_runtime_run_id",
        "ix_runtime_audit_events_audit_id",
    ):
        op.drop_index(index_name, table_name="runtime_audit_events")
    op.drop_table("runtime_audit_events")

    for index_name in (
        "ix_runtime_trace_events_tenant_run_sequence",
        "ix_runtime_trace_events_occurred_at",
        "ix_runtime_trace_events_step_id",
        "ix_runtime_trace_events_tenant_id",
        "ix_runtime_trace_events_runtime_run_id",
        "ix_runtime_trace_events_event_id",
    ):
        op.drop_index(index_name, table_name="runtime_trace_events")
    op.drop_table("runtime_trace_events")

    for index_name in (
        "ix_runtime_agent_steps_tenant_run_index",
        "ix_runtime_agent_steps_created_at",
        "ix_runtime_agent_steps_tenant_id",
        "ix_runtime_agent_steps_runtime_run_id",
        "ix_runtime_agent_steps_step_id",
    ):
        op.drop_index(index_name, table_name="runtime_agent_steps")
    op.drop_table("runtime_agent_steps")

    for index_name in (
        "ix_runtime_state_snapshots_tenant_run_version",
        "ix_runtime_state_snapshots_created_at",
        "ix_runtime_state_snapshots_tenant_id",
        "ix_runtime_state_snapshots_runtime_run_id",
        "ix_runtime_state_snapshots_snapshot_id",
    ):
        op.drop_index(index_name, table_name="runtime_state_snapshots")
    op.drop_table("runtime_state_snapshots")

    for index_name in (
        "ix_runtime_runs_tenant_status",
        "ix_runtime_runs_tenant_created",
        "ix_runtime_runs_created_at",
        "ix_runtime_runs_tenant_id",
        "ix_runtime_runs_runtime_run_id",
    ):
        op.drop_index(index_name, table_name="runtime_runs")
    op.drop_table("runtime_runs")

"""create collaboration runs and steps tables

Revision ID: 010
Revises: 009
Create Date: 2026-06-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collaboration_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("user_request", sa.Text(), nullable=False),
        sa.Column("customer_context_json", sa.JSON(), nullable=True),
        sa.Column("execution_plan_json", sa.JSON(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("final_report", sa.Text(), nullable=True),
        sa.Column("review_result_json", sa.JSON(), nullable=True),
        sa.Column("citations_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("model_info_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_collaboration_runs_status",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_collaboration_runs_created_at",
        "collaboration_runs",
        ["created_at"],
    )
    op.create_index(
        "ix_collaboration_runs_run_id",
        "collaboration_runs",
        ["run_id"],
        unique=True,
    )
    op.create_index(
        "ix_collaboration_runs_session_id",
        "collaboration_runs",
        ["session_id"],
    )
    op.create_index(
        "ix_collaboration_runs_status_created",
        "collaboration_runs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_collaboration_runs_user_created",
        "collaboration_runs",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_collaboration_runs_user_id",
        "collaboration_runs",
        ["user_id"],
    )

    op.create_table(
        "collaboration_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("step_name", sa.String(length=100), nullable=False),
        sa.Column("agent", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("input_json", sa.JSON(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("model_info_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'skipped')",
            name="ck_collaboration_steps_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["collaboration_runs.run_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "step_id",
            name="uq_collaboration_steps_run_step",
        ),
    )
    op.create_index(
        "ix_collaboration_steps_created_at",
        "collaboration_steps",
        ["created_at"],
    )
    op.create_index(
        "ix_collaboration_steps_run_created",
        "collaboration_steps",
        ["run_id", "created_at"],
    )
    op.create_index(
        "ix_collaboration_steps_run_id",
        "collaboration_steps",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_collaboration_steps_run_id",
        table_name="collaboration_steps",
    )
    op.drop_index(
        "ix_collaboration_steps_run_created",
        table_name="collaboration_steps",
    )
    op.drop_index(
        "ix_collaboration_steps_created_at",
        table_name="collaboration_steps",
    )
    op.drop_table("collaboration_steps")

    op.drop_index(
        "ix_collaboration_runs_user_id",
        table_name="collaboration_runs",
    )
    op.drop_index(
        "ix_collaboration_runs_user_created",
        table_name="collaboration_runs",
    )
    op.drop_index(
        "ix_collaboration_runs_status_created",
        table_name="collaboration_runs",
    )
    op.drop_index(
        "ix_collaboration_runs_session_id",
        table_name="collaboration_runs",
    )
    op.drop_index(
        "ix_collaboration_runs_run_id",
        table_name="collaboration_runs",
    )
    op.drop_index(
        "ix_collaboration_runs_created_at",
        table_name="collaboration_runs",
    )
    op.drop_table("collaboration_runs")

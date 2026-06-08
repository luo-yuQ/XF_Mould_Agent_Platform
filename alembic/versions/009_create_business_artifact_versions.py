"""create business_artifact_versions table

Revision ID: 009
Revises: 008
Create Date: 2026-06-08

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "business_artifact_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("artifact_id", sa.Integer(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", sa.String(length=36), nullable=True),
        sa.Column("artifact_type", sa.String(length=20), nullable=False),
        sa.Column("operation_type", sa.String(length=20), nullable=False),
        sa.Column("revision_instruction", sa.Text(), nullable=True),
        sa.Column("input_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("final_markdown", sa.Text(), nullable=False),
        sa.Column("references_json", sa.JSON(), nullable=True),
        sa.Column("diff_summary_json", sa.JSON(), nullable=True),
        sa.Column("verify_result_json", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "artifact_type IN ('fmea', 'audit', 'report')",
            name="ck_artifact_versions_artifact_type",
        ),
        sa.CheckConstraint(
            "operation_type IN ('create', 'revise', 'repair')",
            name="ck_artifact_versions_operation_type",
        ),
        sa.CheckConstraint(
            "version_no >= 1",
            name="ck_artifact_versions_version_no",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_version_id"],
            ["business_artifact_versions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "artifact_type",
            "artifact_id",
            "version_no",
            name="uq_artifact_versions_type_artifact_version",
        ),
    )
    op.create_index(
        "ix_artifact_versions_created_by",
        "business_artifact_versions",
        ["created_by"],
    )
    op.create_index(
        "ix_artifact_versions_created_at",
        "business_artifact_versions",
        ["created_at"],
    )
    op.create_index(
        "ix_artifact_versions_parent_version_id",
        "business_artifact_versions",
        ["parent_version_id"],
    )
    op.create_index(
        "ix_artifact_versions_type_artifact",
        "business_artifact_versions",
        ["artifact_type", "artifact_id"],
    )
    op.create_index(
        "ix_artifact_versions_type_artifact_created",
        "business_artifact_versions",
        ["artifact_type", "artifact_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_artifact_versions_type_artifact_created",
        table_name="business_artifact_versions",
    )
    op.drop_index(
        "ix_artifact_versions_type_artifact",
        table_name="business_artifact_versions",
    )
    op.drop_index(
        "ix_artifact_versions_parent_version_id",
        table_name="business_artifact_versions",
    )
    op.drop_index(
        "ix_artifact_versions_created_at",
        table_name="business_artifact_versions",
    )
    op.drop_index(
        "ix_artifact_versions_created_by",
        table_name="business_artifact_versions",
    )
    op.drop_table("business_artifact_versions")

"""use timezone-aware UTC timestamps

Revision ID: 008
Revises: 007
Create Date: 2026-06-07

"""
from typing import Sequence, Union

from alembic import op


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TIMESTAMP_COLUMNS = {
    "users": ("created_at", "updated_at"),
    "chat_sessions": ("created_at", "updated_at"),
    "chat_messages": ("created_at",),
    "chat_session_summaries": ("updated_at",),
    "fmea_runs": ("created_at", "updated_at"),
    "audit_runs": ("created_at", "updated_at"),
    "report_runs": ("created_at", "updated_at"),
}


def upgrade() -> None:
    for table_name, columns in TIMESTAMP_COLUMNS.items():
        for column_name in columns:
            op.execute(
                f'ALTER TABLE "{table_name}" '
                f'ALTER COLUMN "{column_name}" TYPE TIMESTAMP WITH TIME ZONE '
                f'USING "{column_name}" AT TIME ZONE \'UTC\''
            )


def downgrade() -> None:
    for table_name, columns in TIMESTAMP_COLUMNS.items():
        for column_name in columns:
            op.execute(
                f'ALTER TABLE "{table_name}" '
                f'ALTER COLUMN "{column_name}" TYPE TIMESTAMP WITHOUT TIME ZONE '
                f'USING "{column_name}" AT TIME ZONE \'UTC\''
            )

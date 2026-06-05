"""create report_runs table

Revision ID: 006
Revises: 005
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'report_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('report_type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('fmea_run_id', sa.Integer(), nullable=True),
        sa.Column('audit_run_id', sa.Integer(), nullable=True),
        sa.Column('quality_case_id', sa.String(length=64), nullable=True),
        sa.Column('extra_background', sa.Text(), nullable=True),
        sa.Column('source_snapshot_json', sa.JSON(), nullable=True),
        sa.Column('final_markdown', sa.Text(), nullable=False),
        sa.Column('verify_result_json', sa.JSON(), nullable=True),
        sa.Column('references_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['audit_run_id'], ['audit_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['fmea_run_id'], ['fmea_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_report_runs_user_id', 'report_runs', ['user_id'])
    op.create_index('ix_report_runs_fmea_run_id', 'report_runs', ['fmea_run_id'])
    op.create_index('ix_report_runs_audit_run_id', 'report_runs', ['audit_run_id'])
    op.create_index('ix_report_runs_quality_case_id', 'report_runs', ['quality_case_id'])
    op.create_index('ix_report_runs_created_at', 'report_runs', ['created_at'])
    op.create_index('ix_report_runs_updated_at', 'report_runs', ['updated_at'])
    op.create_index('ix_report_runs_user_created', 'report_runs', ['user_id', 'created_at'])
    op.create_index('ix_report_runs_type_created', 'report_runs', ['report_type', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_report_runs_type_created', table_name='report_runs')
    op.drop_index('ix_report_runs_user_created', table_name='report_runs')
    op.drop_index('ix_report_runs_updated_at', table_name='report_runs')
    op.drop_index('ix_report_runs_created_at', table_name='report_runs')
    op.drop_index('ix_report_runs_quality_case_id', table_name='report_runs')
    op.drop_index('ix_report_runs_audit_run_id', table_name='report_runs')
    op.drop_index('ix_report_runs_fmea_run_id', table_name='report_runs')
    op.drop_index('ix_report_runs_user_id', table_name='report_runs')
    op.drop_table('report_runs')

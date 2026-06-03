"""create fmea_runs table

Revision ID: 004
Revises: 003
Create Date: 2026-06-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fmea_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('product', sa.String(length=200), nullable=False),
        sa.Column('process', sa.String(length=100), nullable=False),
        sa.Column('failure_phenomenon', sa.String(length=200), nullable=False),
        sa.Column('input_json', sa.JSON(), nullable=False),
        sa.Column('retrieval_queries_json', sa.JSON(), nullable=True),
        sa.Column('retrieved_refs_json', sa.JSON(), nullable=True),
        sa.Column('output_json', sa.JSON(), nullable=False),
        sa.Column('output_markdown', sa.Text(), nullable=False),
        sa.Column('verify_result_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fmea_runs_user_id', 'fmea_runs', ['user_id'])
    op.create_index('ix_fmea_runs_session_id', 'fmea_runs', ['session_id'])
    op.create_index('ix_fmea_runs_created_at', 'fmea_runs', ['created_at'])
    op.create_index('ix_fmea_runs_user_created', 'fmea_runs', ['user_id', 'created_at'])
    op.create_index('ix_fmea_runs_session_created', 'fmea_runs', ['session_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_fmea_runs_session_created', table_name='fmea_runs')
    op.drop_index('ix_fmea_runs_user_created', table_name='fmea_runs')
    op.drop_index('ix_fmea_runs_created_at', table_name='fmea_runs')
    op.drop_index('ix_fmea_runs_session_id', table_name='fmea_runs')
    op.drop_index('ix_fmea_runs_user_id', table_name='fmea_runs')
    op.drop_table('fmea_runs')


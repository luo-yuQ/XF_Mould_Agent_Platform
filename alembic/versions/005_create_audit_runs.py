"""create audit_runs table

Revision ID: 005
Revises: 004
Create Date: 2026-06-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(length=64), nullable=False),
        sa.Column('audit_type', sa.String(length=50), nullable=False),
        sa.Column('content_text', sa.Text(), nullable=False),
        sa.Column('focus', sa.Text(), nullable=True),
        sa.Column('background', sa.Text(), nullable=True),
        sa.Column('retrieval_queries_json', sa.JSON(), nullable=True),
        sa.Column('retrieved_refs_json', sa.JSON(), nullable=True),
        sa.Column('findings_json', sa.JSON(), nullable=False),
        sa.Column('final_markdown', sa.Text(), nullable=False),
        sa.Column('verify_result_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_audit_runs_user_id', 'audit_runs', ['user_id'])
    op.create_index('ix_audit_runs_session_id', 'audit_runs', ['session_id'])
    op.create_index('ix_audit_runs_created_at', 'audit_runs', ['created_at'])
    op.create_index('ix_audit_runs_user_created', 'audit_runs', ['user_id', 'created_at'])
    op.create_index('ix_audit_runs_session_created', 'audit_runs', ['session_id', 'created_at'])


def downgrade() -> None:
    op.drop_index('ix_audit_runs_session_created', table_name='audit_runs')
    op.drop_index('ix_audit_runs_user_created', table_name='audit_runs')
    op.drop_index('ix_audit_runs_created_at', table_name='audit_runs')
    op.drop_index('ix_audit_runs_session_id', table_name='audit_runs')
    op.drop_index('ix_audit_runs_user_id', table_name='audit_runs')
    op.drop_table('audit_runs')

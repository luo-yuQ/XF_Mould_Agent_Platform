"""add business artifact metadata fields

Revision ID: 007
Revises: 006
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('fmea_runs', sa.Column('title', sa.String(length=200), nullable=True))
    op.add_column('fmea_runs', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('fmea_runs', sa.Column('keywords_json', sa.JSON(), nullable=True))
    op.add_column('fmea_runs', sa.Column('artifact_type', sa.String(length=50), nullable=True))
    op.add_column('fmea_runs', sa.Column('references_json', sa.JSON(), nullable=True))
    op.add_column('fmea_runs', sa.Column('quality_case_id', sa.String(length=64), nullable=True))
    op.add_column('fmea_runs', sa.Column('updated_at', sa.DateTime(), nullable=True))

    op.add_column('audit_runs', sa.Column('title', sa.String(length=200), nullable=True))
    op.add_column('audit_runs', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('audit_runs', sa.Column('keywords_json', sa.JSON(), nullable=True))
    op.add_column('audit_runs', sa.Column('artifact_type', sa.String(length=50), nullable=True))
    op.add_column('audit_runs', sa.Column('references_json', sa.JSON(), nullable=True))
    op.add_column('audit_runs', sa.Column('quality_case_id', sa.String(length=64), nullable=True))
    op.add_column('audit_runs', sa.Column('updated_at', sa.DateTime(), nullable=True))

    op.add_column('report_runs', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('report_runs', sa.Column('keywords_json', sa.JSON(), nullable=True))
    op.add_column('report_runs', sa.Column('artifact_type', sa.String(length=50), nullable=True))
    op.add_column('report_runs', sa.Column('source_match_result_json', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('report_runs', 'source_match_result_json')
    op.drop_column('report_runs', 'artifact_type')
    op.drop_column('report_runs', 'keywords_json')
    op.drop_column('report_runs', 'summary')

    op.drop_column('audit_runs', 'updated_at')
    op.drop_column('audit_runs', 'quality_case_id')
    op.drop_column('audit_runs', 'references_json')
    op.drop_column('audit_runs', 'artifact_type')
    op.drop_column('audit_runs', 'keywords_json')
    op.drop_column('audit_runs', 'summary')
    op.drop_column('audit_runs', 'title')

    op.drop_column('fmea_runs', 'updated_at')
    op.drop_column('fmea_runs', 'quality_case_id')
    op.drop_column('fmea_runs', 'references_json')
    op.drop_column('fmea_runs', 'artifact_type')
    op.drop_column('fmea_runs', 'keywords_json')
    op.drop_column('fmea_runs', 'summary')
    op.drop_column('fmea_runs', 'title')

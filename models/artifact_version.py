"""统一业务产物版本记录模型。"""
from __future__ import annotations

import uuid

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


class BusinessArtifactVersion(Base):
    """FMEA、Audit、Report 共用的不可变版本记录。"""

    __tablename__ = "business_artifact_versions"
    __table_args__ = (
        CheckConstraint("version_no >= 1", name="ck_artifact_versions_version_no"),
        CheckConstraint(
            "artifact_type IN ('fmea', 'audit', 'report')",
            name="ck_artifact_versions_artifact_type",
        ),
        CheckConstraint(
            "operation_type IN ('create', 'revise', 'repair')",
            name="ck_artifact_versions_operation_type",
        ),
        UniqueConstraint(
            "artifact_type",
            "artifact_id",
            "version_no",
            name="uq_artifact_versions_type_artifact_version",
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    artifact_id = Column(Integer, nullable=False)
    version_no = Column(Integer, nullable=False)
    parent_version_id = Column(
        String(36),
        ForeignKey("business_artifact_versions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    artifact_type = Column(String(20), nullable=False)
    operation_type = Column(String(20), nullable=False)
    revision_instruction = Column(Text, nullable=True)
    input_snapshot_json = Column(JSON, nullable=True)
    output_json = Column(JSON, nullable=False)
    final_markdown = Column(Text, nullable=False)
    references_json = Column(JSON, nullable=True)
    diff_summary_json = Column(JSON, nullable=True)
    verify_result_json = Column(JSON, nullable=True)
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)


Index(
    "ix_artifact_versions_type_artifact_created",
    BusinessArtifactVersion.artifact_type,
    BusinessArtifactVersion.artifact_id,
    BusinessArtifactVersion.created_at,
)
Index(
    "ix_artifact_versions_type_artifact",
    BusinessArtifactVersion.artifact_type,
    BusinessArtifactVersion.artifact_id,
)

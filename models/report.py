"""
报告生成运行记录模型。

仅保存报告生成结果和来源快照，不参与 Milvus 入库、向量化或业务产物检索。
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text

from models.base import Base
from time_utils import utc_now


class ReportRun(Base):
    """报告生成运行记录表。"""

    __tablename__ = "report_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    report_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    summary = Column(Text, nullable=True)
    keywords_json = Column(JSON, nullable=True)
    artifact_type = Column(String(50), nullable=True)
    fmea_run_id = Column(
        Integer,
        ForeignKey("fmea_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    audit_run_id = Column(
        Integer,
        ForeignKey("audit_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    quality_case_id = Column(String(64), nullable=True, index=True)
    extra_background = Column(Text, nullable=True)
    source_snapshot_json = Column(JSON, nullable=True)
    source_match_result_json = Column(JSON, nullable=True)
    final_markdown = Column(Text, nullable=False)
    verify_result_json = Column(JSON, nullable=True)
    references_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, index=True)


Index("ix_report_runs_user_created", ReportRun.user_id, ReportRun.created_at)
Index("ix_report_runs_type_created", ReportRun.report_type, ReportRun.created_at)

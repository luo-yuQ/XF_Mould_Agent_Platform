"""
审核检查运行记录模型。

仅记录审核检查运行结果，不参与向量化、Milvus 写入或历史案例召回。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text

from models.base import Base


class AuditRun(Base):
    """审核检查运行记录表"""

    __tablename__ = "audit_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(
        String(64),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    audit_type = Column(String(50), nullable=False)
    content_text = Column(Text, nullable=False)
    focus = Column(Text, nullable=True)
    background = Column(Text, nullable=True)
    retrieval_queries_json = Column(JSON, nullable=True)
    retrieved_refs_json = Column(JSON, nullable=True)
    findings_json = Column(JSON, nullable=False)
    final_markdown = Column(Text, nullable=False)
    verify_result_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


Index("ix_audit_runs_user_created", AuditRun.user_id, AuditRun.created_at)
Index("ix_audit_runs_session_created", AuditRun.session_id, AuditRun.created_at)

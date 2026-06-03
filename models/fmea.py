"""
FMEA 生成运行记录模型。

仅记录 PFMEA/FMEA 生成结果，不参与向量化、Milvus 写入或历史案例召回。
"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text

from models.base import Base


class FMEARun(Base):
    """FMEA 生成运行记录表"""

    __tablename__ = "fmea_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id = Column(
        String(64),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product = Column(String(200), nullable=False)
    process = Column(String(100), nullable=False)
    failure_phenomenon = Column(String(200), nullable=False)
    input_json = Column(JSON, nullable=False)
    retrieval_queries_json = Column(JSON, nullable=True)
    retrieved_refs_json = Column(JSON, nullable=True)
    output_json = Column(JSON, nullable=False)
    output_markdown = Column(Text, nullable=False)
    verify_result_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


Index("ix_fmea_runs_user_created", FMEARun.user_id, FMEARun.created_at)
Index("ix_fmea_runs_session_created", FMEARun.session_id, FMEARun.created_at)


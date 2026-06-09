"""销售协作任务及步骤的持久化模型。"""

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
from sqlalchemy.orm import relationship

from models.base import Base
from time_utils import utc_now


class CollaborationRun(Base):
    """一次销售协作任务的整体运行记录。"""

    __tablename__ = "collaboration_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
            name="ck_collaboration_runs_status",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, unique=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id = Column(
        String(64),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_request = Column(Text, nullable=False)
    customer_context_json = Column(JSON, nullable=True)
    execution_plan_json = Column(JSON, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    final_report = Column(Text, nullable=True)
    review_result_json = Column(JSON, nullable=True)
    citations_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    model_info_json = Column(JSON, nullable=True)
    metrics_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    steps = relationship(
        "CollaborationStep",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="CollaborationStep.id",
        passive_deletes=True,
    )


class CollaborationStep(Base):
    """销售协作任务中单个智能体步骤的执行记录。"""

    __tablename__ = "collaboration_steps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'skipped')",
            name="ck_collaboration_steps_status",
        ),
        UniqueConstraint(
            "run_id",
            "step_id",
            name="uq_collaboration_steps_run_step",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(
        String(64),
        ForeignKey("collaboration_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id = Column(String(64), nullable=False)
    step_name = Column(String(100), nullable=False)
    agent = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    input_json = Column(JSON, nullable=True)
    output_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    model_info_json = Column(JSON, nullable=True)
    metrics_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    run = relationship("CollaborationRun", back_populates="steps")


Index(
    "ix_collaboration_runs_user_created",
    CollaborationRun.user_id,
    CollaborationRun.created_at,
)
Index(
    "ix_collaboration_runs_status_created",
    CollaborationRun.status,
    CollaborationRun.created_at,
)
Index(
    "ix_collaboration_steps_run_created",
    CollaborationStep.run_id,
    CollaborationStep.created_at,
)

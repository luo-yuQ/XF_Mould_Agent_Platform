"""销售协作 run 和 step 的数据库持久化。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models.collaboration import CollaborationRun, CollaborationStep

logger = logging.getLogger("uvicorn.error")


def create_collaboration_run(
    db: Session,
    *,
    run_id: str,
    user_id: int,
    session_id: str | None,
    user_request: str,
    customer_context: dict[str, Any],
) -> CollaborationRun:
    """先保存 running run，保证后续 graph 异常仍有任务记录。"""
    run = CollaborationRun(
        run_id=run_id,
        user_id=user_id,
        session_id=session_id,
        user_request=user_request,
        customer_context_json=customer_context,
        status="running",
    )
    db.add(run)
    logger.info(
        "sales_collaboration.persist_run.started run_id=%s user_id=%s status=%s",
        run_id,
        user_id,
        run.status,
    )
    try:
        db.commit()
        db.refresh(run)
    except Exception:
        logger.exception(
            "sales_collaboration.persist_run.failed run_id=%s user_id=%s",
            run_id,
            user_id,
        )
        raise
    logger.info(
        "sales_collaboration.persist_run.completed run_id=%s user_id=%s status=%s",
        run_id,
        user_id,
        run.status,
    )
    return run


def finalize_collaboration_run(
    db: Session,
    *,
    run: CollaborationRun,
    final_state: dict[str, Any],
) -> CollaborationRun:
    """保存 graph 最终状态和全部步骤。"""
    run.status = final_state.get("status") or "failed"
    run.execution_plan_json = final_state.get("execution_plan") or []
    run.final_report = final_state.get("final_report") or None
    run.review_result_json = final_state.get("review_result") or {}
    run.citations_json = final_state.get("citations") or []
    run.error = final_state.get("error")
    run.metrics_json = final_state.get("metrics")

    logger.info(
        "sales_collaboration.persist_run.started run_id=%s status=%s",
        run.run_id,
        run.status,
    )
    step_records = final_state.get("collaboration_steps")
    if step_records is None:
        step_records = final_state.get("steps", [])
    replace_collaboration_steps(db, run=run, steps=step_records or [])

    try:
        db.commit()
        db.refresh(run)
    except Exception:
        logger.exception(
            "sales_collaboration.persist_run.failed run_id=%s status=%s",
            run.run_id,
            run.status,
        )
        raise
    logger.info(
        "sales_collaboration.persist_run.completed run_id=%s status=%s",
        run.run_id,
        run.status,
    )
    return run


def fail_collaboration_run(
    db: Session,
    *,
    run: CollaborationRun,
    error: str,
    final_state: dict[str, Any] | None = None,
) -> CollaborationRun:
    """将异常运行稳定保存为 failed，并保留已有步骤。"""
    state = dict(final_state or {})
    state["status"] = "failed"
    state["error"] = error
    return finalize_collaboration_run(db, run=run, final_state=state)


def replace_collaboration_steps(
    db: Session,
    *,
    run: CollaborationRun,
    steps: list[dict[str, Any]],
) -> None:
    """按 graph 顺序替换该 run 的步骤记录。"""
    db.query(CollaborationStep).filter(
        CollaborationStep.run_id == run.run_id
    ).delete(synchronize_session=False)

    for index, step in enumerate(steps):
        step_id = str(step.get("step_id") or f"step-{index + 1}")
        agent = str(step.get("agent") or "system")
        step_status = str(step.get("status") or "pending")
        logger.info(
            "sales_collaboration.persist_step.started run_id=%s step_id=%s agent=%s",
            run.run_id,
            step_id,
            agent,
        )
        db.add(
            CollaborationStep(
                run_id=run.run_id,
                step_id=step_id,
                step_name=str(step.get("step_name") or step_id),
                agent=agent,
                status=step_status,
                input_json=step.get("input_json", step.get("input")),
                output_json=step.get("output_json", step.get("output")),
                error=step.get("error"),
                started_at=_datetime_or_none(step.get("started_at")),
                finished_at=_datetime_or_none(step.get("finished_at")),
                duration_ms=step.get("duration_ms"),
                model_info_json=step.get("model_info_json"),
                metrics_json=step.get("metrics_json"),
            )
        )
        logger.info(
            "sales_collaboration.persist_step.completed run_id=%s step_id=%s "
            "agent=%s status=%s",
            run.run_id,
            step_id,
            agent,
            step_status,
        )


def get_owned_collaboration_run(
    db: Session,
    *,
    run_id: str,
    user_id: int,
) -> CollaborationRun | None:
    """只返回当前用户拥有的 run。"""
    return (
        db.query(CollaborationRun)
        .filter(
            CollaborationRun.run_id == run_id,
            CollaborationRun.user_id == user_id,
        )
        .first()
    )


def list_collaboration_steps(
    db: Session,
    *,
    run_id: str,
) -> list[CollaborationStep]:
    """按插入顺序返回步骤。"""
    return (
        db.query(CollaborationStep)
        .filter(CollaborationStep.run_id == run_id)
        .order_by(CollaborationStep.id)
        .all()
    )


def _datetime_or_none(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None

"""销售协作串行 LangGraph 骨架。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.sales_planner import run_sales_planner
from agents.sales_proposal_writer import REPORT_HEADINGS, run_sales_proposal_writer
from agents.sales_quality_specialist import run_sales_quality_specialist
from agents.sales_rd_specialist import run_sales_rd_specialist
from agents.sales_reviewer import run_sales_reviewer
from schemas.sales_collaboration import (
    PlannerOutput,
    ProposalWriterOutput,
    ReviewerOutput,
    SpecialistOutput,
)
from state import SalesCollaborationState

logger = logging.getLogger("uvicorn.error")


SALES_COLLABORATION_NODE_ORDER = (
    "request_intake",
    "planner",
    "rd_specialist",
    "quality_specialist",
    "reviewer",
    "proposal_writer",
    "final_verifier",
    "persist_run",
)

STEP_DEFINITIONS = {
    "request_intake": ("需求受理", "intake"),
    "planner": ("协作规划", "planner"),
    "rd_specialist": ("研发分析", "rd"),
    "quality_specialist": ("质量分析", "quality"),
    "reviewer": ("结果审核", "reviewer"),
    "proposal_writer": ("方案编写", "writer"),
    "final_verifier": ("最终校验", "verifier"),
    "persist_run": ("运行持久化", "system"),
}


class SalesCollaborationGraphState(SalesCollaborationState, total=False):
    """Phase C graph 扩展状态，步骤记录后续可映射到 CollaborationStep。"""

    collaboration_steps: list[dict[str, Any]]
    proposal_summary: str


SpecialistRunner = Callable[..., SpecialistOutput | dict[str, Any]]
PlannerRunner = Callable[..., PlannerOutput | dict[str, Any]]
ReviewerRunner = Callable[..., ReviewerOutput | dict[str, Any]]
WriterRunner = Callable[..., ProposalWriterOutput | dict[str, Any]]


def _initial_steps() -> list[dict[str, Any]]:
    return [
        {
            "step_id": step_id,
            "step_name": STEP_DEFINITIONS[step_id][0],
            "agent": STEP_DEFINITIONS[step_id][1],
            "status": "pending",
            "input": None,
            "output": None,
            "error": None,
        }
        for step_id in SALES_COLLABORATION_NODE_ORDER
    ]


def _update_step(
    state: SalesCollaborationGraphState,
    step_id: str,
    *,
    status: str,
    input_data: Any = None,
    output_data: Any = None,
    error: str | None = None,
) -> list[dict[str, Any]]:
    steps = [dict(step) for step in state.get("collaboration_steps", _initial_steps())]
    for step in steps:
        if step["step_id"] == step_id:
            step.update(
                {
                    "status": status,
                    "input": input_data,
                    "output": output_data,
                    "error": error,
                }
            )
            break
    return steps


def _skip_failed_step(
    state: SalesCollaborationGraphState,
    step_id: str,
) -> dict[str, Any] | None:
    if state.get("status") != "failed":
        return None
    return {
        "collaboration_steps": _update_step(
            state,
            step_id,
            status="skipped",
            error="Skipped because an earlier collaboration step failed.",
        )
    }


def request_intake_node(state: SalesCollaborationGraphState) -> dict[str, Any]:
    """校验输入并初始化协作运行状态。"""
    user_request = str(state.get("user_request") or "").strip()
    base_output = {
        "customer_context": dict(state.get("customer_context") or {}),
        "execution_plan": [],
        "rd_analysis": {},
        "quality_analysis": {},
        "optional_artifacts": [],
        "review_result": {},
        "final_report": "",
        "citations": [],
    }
    input_data = {
        "user_request": state.get("user_request"),
        "user_id": state.get("user_id"),
        "session_id": state.get("session_id"),
    }

    if not user_request:
        error = "user_request must not be empty."
        failed_state = {**state, **base_output, "status": "failed", "error": error}
        return {
            **base_output,
            "status": "failed",
            "error": error,
            "collaboration_steps": _update_step(
                failed_state,
                "request_intake",
                status="failed",
                input_data=input_data,
                error=error,
            ),
        }

    output_data = {
        "customer_context": base_output["customer_context"],
        "status": "running",
    }
    running_state = {**state, **base_output, **output_data, "error": None}
    return {
        **base_output,
        **output_data,
        "error": None,
        "collaboration_steps": _update_step(
            running_state,
            "request_intake",
            status="completed",
            input_data=input_data,
            output_data=output_data,
        ),
    }


def planner_node(
    state: SalesCollaborationGraphState,
    planner: PlannerRunner = run_sales_planner,
) -> dict[str, Any]:
    """调用销售协作 Planner，并记录可选工作流占位。"""
    skipped = _skip_failed_step(state, "planner")
    if skipped:
        return skipped

    input_data = {
        "user_request": state.get("user_request", ""),
        "customer_context": state.get("customer_context", {}),
        "session_id": state.get("session_id"),
    }
    try:
        planner_output = PlannerOutput.model_validate(planner(**input_data))
    except Exception as exc:
        logger.exception(
            "sales_collaboration.step.failed run_id=%s step=%s agent=%s",
            state.get("request_id"),
            "planner",
            "planner",
        )
        error = f"Planner failed: {exc}"
        return {
            "status": "failed",
            "error": error,
            "collaboration_steps": _update_step(
                state,
                "planner",
                status="failed",
                input_data=input_data,
                error=error,
            ),
        }

    full_output = planner_output.model_dump()
    execution_plan = [task.model_dump() for task in planner_output.tasks]
    optional_artifacts = [
        {
            "task_id": task.task_id,
            "artifact_type": task.agent,
            "status": "not_invoked",
            "reason": "当前销售协作图不会自动调用专业工作流。",
        }
        for task in planner_output.tasks
        if task.agent in {"fmea", "audit"}
    ]
    return {
        "execution_plan": execution_plan,
        "optional_artifacts": optional_artifacts,
        "collaboration_steps": _update_step(
            state,
            "planner",
            status="completed",
            input_data=input_data,
            output_data=full_output,
        ),
    }


def rd_specialist_node(
    state: SalesCollaborationGraphState,
    specialist: SpecialistRunner = run_sales_rd_specialist,
) -> dict[str, Any]:
    """调用销售协作 R&D Specialist 包装层。"""
    skipped = _skip_failed_step(state, "rd_specialist")
    if skipped:
        return skipped

    task = find_execution_task(state, "rd_analysis")
    input_data = {
        "user_request": state.get("user_request", ""),
        "customer_context": state.get("customer_context", {}),
        "execution_plan": state.get("execution_plan", []),
        "task": task,
    }
    try:
        output = SpecialistOutput.model_validate(specialist(**input_data)).model_dump()
    except Exception as exc:
        logger.exception(
            "sales_collaboration.step.failed run_id=%s step=%s agent=%s",
            state.get("request_id"),
            "rd_specialist",
            "rd",
        )
        error = f"R&D specialist failed: {exc}"
        return {
            "status": "failed",
            "error": error,
            "collaboration_steps": _update_step(
                state,
                "rd_specialist",
                status="failed",
                input_data=input_data,
                error=error,
            ),
        }

    return {
        "rd_analysis": output,
        "citations": [*state.get("citations", []), *output["citations"]],
        "collaboration_steps": _update_step(
            state,
            "rd_specialist",
            status="completed",
            input_data=input_data,
            output_data=output,
        ),
    }


def quality_specialist_node(
    state: SalesCollaborationGraphState,
    specialist: SpecialistRunner = run_sales_quality_specialist,
) -> dict[str, Any]:
    """调用销售协作 Quality Specialist 包装层。"""
    skipped = _skip_failed_step(state, "quality_specialist")
    if skipped:
        return skipped

    task = find_execution_task(state, "quality_analysis")
    input_data = {
        "user_request": state.get("user_request", ""),
        "customer_context": state.get("customer_context", {}),
        "execution_plan": state.get("execution_plan", []),
        "task": task,
    }
    try:
        output = SpecialistOutput.model_validate(specialist(**input_data)).model_dump()
    except Exception as exc:
        logger.exception(
            "sales_collaboration.step.failed run_id=%s step=%s agent=%s",
            state.get("request_id"),
            "quality_specialist",
            "quality",
        )
        error = f"Quality specialist failed: {exc}"
        return {
            "status": "failed",
            "error": error,
            "collaboration_steps": _update_step(
                state,
                "quality_specialist",
                status="failed",
                input_data=input_data,
                error=error,
            ),
        }

    return {
        "quality_analysis": output,
        "citations": [*state.get("citations", []), *output["citations"]],
        "collaboration_steps": _update_step(
            state,
            "quality_specialist",
            status="completed",
            input_data=input_data,
            output_data=output,
        ),
    }


def find_execution_task(
    state: SalesCollaborationGraphState,
    task_id: str,
) -> dict[str, Any]:
    """读取 Planner 为当前节点生成的任务信息。"""
    task = next(
        (
            dict(task)
            for task in state.get("execution_plan", [])
            if task.get("task_id") == task_id
        ),
        None,
    )
    if task:
        return task
    expected_agent = {
        "rd_analysis": "rd",
        "quality_analysis": "quality",
    }.get(task_id)
    return next(
        (
            dict(item)
            for item in state.get("execution_plan", [])
            if item.get("agent") == expected_agent
        ),
        {},
    )


def reviewer_node(
    state: SalesCollaborationGraphState,
    reviewer: ReviewerRunner = run_sales_reviewer,
) -> dict[str, Any]:
    """调用规则优先的销售协作 Reviewer。"""
    skipped = _skip_failed_step(state, "reviewer")
    if skipped:
        return skipped

    input_data = {
        "user_request": state.get("user_request", ""),
        "execution_plan": state.get("execution_plan", []),
        "rd_analysis": state.get("rd_analysis", {}),
        "quality_analysis": state.get("quality_analysis", {}),
    }
    try:
        output = ReviewerOutput.model_validate(reviewer(**input_data)).model_dump()
    except Exception as exc:
        logger.exception(
            "sales_collaboration.step.failed run_id=%s step=%s agent=%s",
            state.get("request_id"),
            "reviewer",
            "reviewer",
        )
        error = f"Reviewer failed: {exc}"
        return {
            "status": "failed",
            "error": error,
            "collaboration_steps": _update_step(
                state,
                "reviewer",
                status="failed",
                input_data=input_data,
                error=error,
            ),
        }

    return {
        "review_result": output,
        "collaboration_steps": _update_step(
            state,
            "reviewer",
            status="completed",
            input_data=input_data,
            output_data=output,
        ),
    }


def proposal_writer_node(
    state: SalesCollaborationGraphState,
    writer: WriterRunner = run_sales_proposal_writer,
) -> dict[str, Any]:
    """调用受证据约束的销售协作 Proposal Writer。"""
    skipped = _skip_failed_step(state, "proposal_writer")
    if skipped:
        return skipped

    input_data = {
        "user_request": state.get("user_request", ""),
        "execution_plan": state.get("execution_plan", []),
        "rd_analysis": state.get("rd_analysis", {}),
        "quality_analysis": state.get("quality_analysis", {}),
        "review_result": state.get("review_result", {}),
    }
    try:
        output = ProposalWriterOutput.model_validate(writer(**input_data))
    except Exception as exc:
        logger.exception(
            "sales_collaboration.step.failed run_id=%s step=%s agent=%s",
            state.get("request_id"),
            "proposal_writer",
            "writer",
        )
        error = f"Proposal writer failed: {exc}"
        return {
            "status": "failed",
            "error": error,
            "collaboration_steps": _update_step(
                state,
                "proposal_writer",
                status="failed",
                input_data=input_data,
                error=error,
            ),
        }

    output_data = output.model_dump()
    return {
        "final_report": output.final_report,
        "proposal_summary": output.summary,
        "citations": [citation.model_dump() for citation in output.citations],
        "collaboration_steps": _update_step(
            state,
            "proposal_writer",
            status="completed",
            input_data=input_data,
            output_data=output_data,
        ),
    }


def final_verifier_node(state: SalesCollaborationGraphState) -> dict[str, Any]:
    """执行最终结果的最小结构校验。"""
    skipped = _skip_failed_step(state, "final_verifier")
    if skipped:
        return skipped

    missing = [
        field
        for field in ("final_report", "rd_analysis", "quality_analysis", "review_result")
        if not state.get(field)
    ]
    missing_headings = [
        heading
        for heading in REPORT_HEADINGS
        if heading not in str(state.get("final_report") or "")
    ]
    if missing_headings:
        missing.append("report_headings")
    if missing:
        error = (
            "Final verification failed; missing required state or sections: "
            + ", ".join(missing)
            + "."
        )
        return {
            "status": "failed",
            "error": error,
            "collaboration_steps": _update_step(
                state,
                "final_verifier",
                status="failed",
                input_data={
                    "required_fields": missing,
                    "missing_headings": missing_headings,
                },
                error=error,
            ),
        }

    return {
        "collaboration_steps": _update_step(
            state,
            "final_verifier",
            status="completed",
            input_data={
                "final_report": state.get("final_report"),
                "rd_analysis": state.get("rd_analysis"),
                "quality_analysis": state.get("quality_analysis"),
                "review_result": state.get("review_result"),
            },
            output_data={"passed": True},
        )
    }


def persist_collaboration_run(state: SalesCollaborationGraphState) -> None:
    """持久化扩展点；API 模式由 repository 在 graph 返回后统一提交。"""
    return None


def persist_run_node(state: SalesCollaborationGraphState) -> dict[str, Any]:
    """调用持久化扩展点，并在成功流程上标记运行完成。"""
    if state.get("status") == "failed":
        return {
            "collaboration_steps": _update_step(
                state,
                "persist_run",
                status="skipped",
                error="Run was not persisted because collaboration failed.",
            )
        }

    try:
        persist_collaboration_run(state)
    except Exception as exc:
        logger.exception(
            "sales_collaboration.step.failed run_id=%s step=%s agent=%s",
            state.get("request_id"),
            "persist_run",
            "system",
        )
        error = f"Failed to persist collaboration run: {exc}"
        return {
            "status": "failed",
            "error": error,
            "collaboration_steps": _update_step(
                state,
                "persist_run",
                status="failed",
                input_data={"status": state.get("status")},
                error=error,
            ),
        }

    return {
        "status": "completed",
        "error": None,
        "collaboration_steps": _update_step(
            state,
            "persist_run",
            status="completed",
            input_data={"status": state.get("status")},
            output_data={
                "persistence_requested": True,
                "mode": "api_repository",
            },
        ),
    }


def _with_sales_logging(
    step: str,
    agent: str,
    node: Callable[[SalesCollaborationGraphState], dict[str, Any]],
):
    def wrapped(state: SalesCollaborationGraphState) -> dict[str, Any]:
        run_id = state.get("request_id")
        logger.info(
            "sales_collaboration.step.started run_id=%s step=%s agent=%s",
            run_id,
            step,
            agent,
        )
        try:
            result = node(state)
        except Exception:
            logger.exception(
                "sales_collaboration.step.failed run_id=%s step=%s agent=%s",
                run_id,
                step,
                agent,
            )
            raise

        step_record = next(
            (
                item
                for item in result.get("collaboration_steps", [])
                if item.get("step_id") == step
            ),
            {},
        )
        reviewer_output = result.get("review_result", {})
        step_output = step_record.get("output")
        if not isinstance(step_output, dict):
            step_output = {}
        logger.info(
            "sales_collaboration.step.completed run_id=%s step=%s agent=%s "
            "status=%s plan_step_count=%s passed=%s "
            "unsupported_claims_count=%s conflicts_count=%s",
            run_id,
            step,
            agent,
            step_record.get("status") or result.get("status") or "completed",
            len(result.get("execution_plan", [])) if step == "planner" else None,
            (
                reviewer_output.get("passed")
                if step == "reviewer"
                else (
                    step_output.get("passed")
                    if step == "final_verifier"
                    else None
                )
            ),
            (
                len(reviewer_output.get("unsupported_claims", []))
                if step == "reviewer"
                else None
            ),
            (
                len(reviewer_output.get("conflicts", []))
                if step == "reviewer"
                else None
            ),
        )
        return result

    return wrapped


def build_sales_collaboration_graph(
    *,
    planner: PlannerRunner = run_sales_planner,
    rd_specialist: SpecialistRunner = run_sales_rd_specialist,
    quality_specialist: SpecialistRunner = run_sales_quality_specialist,
    reviewer: ReviewerRunner = run_sales_reviewer,
    writer: WriterRunner = run_sales_proposal_writer,
):
    """构建固定顺序的销售协作串行图。"""
    workflow = StateGraph(SalesCollaborationGraphState)
    nodes = {
        "request_intake": _with_sales_logging(
            "request_intake",
            "intake",
            request_intake_node,
        ),
        "planner": _with_sales_logging(
            "planner",
            "planner",
            lambda state: planner_node(state, planner),
        ),
        "rd_specialist": _with_sales_logging(
            "rd_specialist",
            "rd",
            lambda state: rd_specialist_node(state, rd_specialist),
        ),
        "quality_specialist": _with_sales_logging(
            "quality_specialist",
            "quality",
            lambda state: quality_specialist_node(
                state,
                quality_specialist,
            ),
        ),
        "reviewer": _with_sales_logging(
            "reviewer",
            "reviewer",
            lambda state: reviewer_node(state, reviewer),
        ),
        "proposal_writer": _with_sales_logging(
            "proposal_writer",
            "writer",
            lambda state: proposal_writer_node(state, writer),
        ),
        "final_verifier": _with_sales_logging(
            "final_verifier",
            "verifier",
            final_verifier_node,
        ),
        "persist_run": _with_sales_logging(
            "persist_run",
            "system",
            persist_run_node,
        ),
    }
    for node_name in SALES_COLLABORATION_NODE_ORDER:
        workflow.add_node(node_name, nodes[node_name])

    workflow.add_edge(START, SALES_COLLABORATION_NODE_ORDER[0])
    for current_node, next_node in zip(
        SALES_COLLABORATION_NODE_ORDER,
        SALES_COLLABORATION_NODE_ORDER[1:],
    ):
        workflow.add_edge(current_node, next_node)
    workflow.add_edge(SALES_COLLABORATION_NODE_ORDER[-1], END)
    return workflow.compile()

"""
Report Workflow MVP LangGraph 工作流。

独立于现有 qa / fmea / audit graph，不接 Supervisor，不通过 session_id
自动关联 FMEA / Audit 产物。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from agents.report_agent import (
    build_report_context,
    ensure_source_match_warning,
    generate_report_markdown,
    load_report_skill,
    load_report_sources,
    render_report_result,
    repair_report_once,
    verify_report,
)
from agents.artifact_metadata import build_report_metadata
from agents.report_source_matcher import check_report_source_match
from schemas.report import ReportInput
from state import AgentState
from time_utils import utc_now

logger = logging.getLogger("uvicorn.error")


def _report_input_payload(state: AgentState) -> dict[str, Any]:
    """从状态中读取报告输入，并补齐 MVP 默认报告类型。"""
    raw = state.get("report_input_raw") or state.get("report_input") or {}
    if isinstance(raw, ReportInput):
        data = raw.model_dump()
    elif isinstance(raw, dict):
        data = dict(raw)
    else:
        data = {}
    data.setdefault("report_type", "quality_issue_report")
    return data


def _report_input_from_state(state: AgentState) -> ReportInput:
    """将状态中的 report_input 转为 ReportInput。"""
    raw = state.get("report_input") or _report_input_payload(state)
    if isinstance(raw, ReportInput):
        return raw
    if isinstance(raw, dict):
        raw = {**raw, "report_type": raw.get("report_type") or "quality_issue_report"}
    return ReportInput.model_validate(raw)


def _json_ready(value: Any) -> Any:
    """将来源快照转换为 JSON 字段可保存的数据。"""
    if hasattr(value, "model_dump"):
        return _json_ready(value.model_dump())
    if isinstance(value, dict):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _coerce_int(value: Any) -> int | None:
    """将可选 ID 转为 int。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _dedupe_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 chunk_uid 或文本去重。"""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for chunk in chunks:
        uid = str(chunk.get("chunk_uid") or chunk.get("text") or "")
        if uid and uid in seen:
            continue
        if uid:
            seen.add(uid)
        unique.append(chunk)
    return unique


def _citation_map(chunks: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """构造 RAG 引用映射。"""
    result: dict[int, dict[str, Any]] = {}
    for index, chunk in enumerate(chunks, 1):
        result[index] = {
            "source": chunk.get("doc_source", ""),
            "chapter": chunk.get("doc_chapter", ""),
            "section_title": chunk.get("doc_section", ""),
            "heading_path": chunk.get("heading_path", ""),
            "chunk_type": chunk.get("chunk_type", "text"),
            "table_id": chunk.get("table_id", ""),
            "row_range": chunk.get("row_range", ""),
            "chunk_uid": chunk.get("chunk_uid", ""),
            "parent_chunk_uid": chunk.get("parent_chunk_uid", ""),
        }
    return result


def _source_text_for_query(source: dict[str, Any], max_len: int = 900) -> str:
    """从 FMEA / Audit 来源提取检索 query 的文本。"""
    if source.get("status") != "found":
        return ""
    parts: list[str] = []
    for key in (
        "product",
        "process",
        "failure_phenomenon",
        "audit_type",
        "focus",
        "background",
        "content_text",
    ):
        value = source.get(key)
        if value:
            parts.append(str(value))

    output_json = source.get("output_json") or {}
    if isinstance(output_json, dict):
        for row in output_json.get("rows", [])[:3]:
            if isinstance(row, dict):
                parts.extend(
                    str(row.get(key) or "")
                    for key in ("failure_mode", "effect", "cause", "recommended_action")
                )

    findings_json = source.get("findings_json") or {}
    if isinstance(findings_json, dict):
        for finding in findings_json.get("findings", [])[:3]:
            if isinstance(finding, dict):
                parts.extend(
                    str(finding.get(key) or "")
                    for key in ("issue", "category", "risk_explanation", "recommendation")
                )

    text = " ".join(part.strip() for part in parts if part and str(part).strip())
    return text[:max_len]


def _build_report_rag_queries(report_context_seed: dict[str, Any]) -> list[str]:
    """基于标题、用户背景、FMEA/Audit 摘要生成少量 RAG 查询词。"""
    report_input = report_context_seed.get("report_input", {})
    title = str(report_context_seed.get("title") or report_input.get("title") or "").strip()
    extra_background = str(report_context_seed.get("extra_background") or "").strip()
    fmea_text = _source_text_for_query(report_context_seed.get("fmea_source", {}))
    audit_text = _source_text_for_query(report_context_seed.get("audit_source", {}))

    queries = [
        " ".join(part for part in [title, extra_background, "质量问题 分析 整改 需人工确认"] if part),
        " ".join(part for part in [fmea_text, "FMEA 风险判断 改进措施 标准依据"] if part),
        " ".join(part for part in [audit_text, "VDA6.4 审核发现 整改闭环 标准依据"] if part),
    ]

    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        normalized = " ".join(query.split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized[:500])
    return unique[:3]


async def report_intake_node(state: AgentState) -> AgentState:
    """校验并规范化报告输入。"""
    try:
        report_input = ReportInput.model_validate(_report_input_payload(state))
    except Exception as exc:
        logger.exception(
            "report.input_check.failed user_id=%s",
            state.get("report_user_id"),
        )
        return {
            **state,
            "sender": "report_intake",
            "report_error": f"报告输入不合法：{exc}",
            "report_markdown": f"报告输入不合法，需人工确认：{exc}",
            "task_completed": True,
        }

    return {
        **state,
        "sender": "report_intake",
        "report_input": report_input.model_dump(),
        "report_repair_attempted": False,
        "task_completed": False,
    }


async def report_load_sources_node(state: AgentState) -> AgentState:
    """按明确 run_id 加载 FMEA / Audit 来源，不使用 session_id 自动查找。"""
    report_input = _report_input_from_state(state)
    user_id = state.get("report_user_id")

    if user_id is None and (report_input.fmea_run_id or report_input.audit_run_id):
        sources = {
            "fmea_source": {
                "status": "not_found",
                "source_type": "fmea",
                "run_id": report_input.fmea_run_id,
                "message": "缺少 user_id，无法校验 FMEA 来源归属，需人工确认。",
            },
            "audit_source": {
                "status": "not_found",
                "source_type": "audit",
                "run_id": report_input.audit_run_id,
                "message": "缺少 user_id，无法校验 Audit 来源归属，需人工确认。",
            },
        }
    else:
        sources = load_report_sources(
            user_id=int(user_id or 0),
            fmea_run_id=report_input.fmea_run_id,
            audit_run_id=report_input.audit_run_id,
            db=state.get("report_db_session"),
        )

    return {
        **state,
        "sender": "report_load_sources",
        "report_sources": sources,
        "report_fmea_source": sources.get("fmea_source", {}),
        "report_audit_source": sources.get("audit_source", {}),
        "task_completed": False,
    }


async def report_source_match_node(state: AgentState) -> AgentState:
    """Run a non-blocking rule check for the user-selected FMEA and Audit sources."""
    report_input = _report_input_from_state(state)
    match_result = check_report_source_match(
        fmea_run=state.get("report_fmea_source"),
        audit_run=state.get("report_audit_source"),
        extra_background=report_input.extra_background,
    )
    return {
        **state,
        "sender": "report_source_match",
        "report_source_match_result": match_result,
        "task_completed": False,
    }


async def report_optional_rag_retrieve_node(state: AgentState) -> AgentState:
    """可选 RAG 检索，只补充参考依据，不替代 FMEA / Audit 结果。"""
    include_rag = state.get("report_include_rag", True)
    if not include_rag:
        return {
            **state,
            "sender": "report_optional_rag_retrieve",
            "report_rag_queries": [],
            "report_rag_refs": [],
            "task_completed": False,
        }

    report_input = _report_input_from_state(state)
    seed = {
        "report_input": report_input.model_dump(),
        "title": report_input.title or "质量问题分析报告",
        "extra_background": report_input.extra_background or "",
        "fmea_source": state.get("report_fmea_source", {}),
        "audit_source": state.get("report_audit_source", {}),
    }
    queries = _build_report_rag_queries(seed)
    if not queries:
        return {
            **state,
            "sender": "report_optional_rag_retrieve",
            "report_rag_queries": [],
            "report_rag_refs": [],
            "task_completed": False,
        }

    from config import MILVUS_COLLECTION_FMEA, MILVUS_COLLECTION_QUALITY
    from tools.rag import retrieve_structured

    loop = asyncio.get_event_loop()
    all_chunks: list[dict[str, Any]] = []
    for query in queries:
        for collection_name in (MILVUS_COLLECTION_QUALITY, MILVUS_COLLECTION_FMEA):
            chunks = await loop.run_in_executor(
                None,
                retrieve_structured,
                query,
                collection_name,
            )
            all_chunks.extend(chunks)

    rag_refs = _dedupe_chunks(all_chunks)
    return {
        **state,
        "sender": "report_optional_rag_retrieve",
        "report_rag_queries": queries,
        "report_rag_refs": rag_refs,
        "rag_chunks": rag_refs,
        "citation_map": _citation_map(rag_refs),
        "citation_ids": list(range(1, len(rag_refs) + 1)),
        "rag_is_relevant": bool(rag_refs),
        "task_completed": False,
    }


async def report_context_builder_node(state: AgentState) -> AgentState:
    """构建报告上下文和来源快照。"""
    report_context = build_report_context(
        report_input=_report_input_from_state(state),
        fmea_source=state.get("report_fmea_source", {}),
        audit_source=state.get("report_audit_source", {}),
        optional_rag_refs=state.get("report_rag_refs", []),
        source_match_result=state.get("report_source_match_result", {}),
    )
    return {
        **state,
        "sender": "report_context_builder",
        "report_context": report_context,
        "report_source_snapshot": report_context.get("source_snapshot", {}),
        "task_completed": False,
    }


async def report_writer_node(state: AgentState) -> AgentState:
    """调用报告 Agent 生成 Markdown。"""
    report_context = state.get("report_context", {})
    markdown = await generate_report_markdown(
        report_context=report_context,
        skill_text=load_report_skill(),
    )
    markdown = ensure_source_match_warning(
        markdown,
        state.get("report_source_match_result"),
    )
    return {
        **state,
        "sender": "report_writer",
        "report_markdown": markdown,
        "task_completed": False,
    }


async def report_verify_node(state: AgentState) -> AgentState:
    """校验报告章节、来源和结论一致性。"""
    verify_result = verify_report(
        state.get("report_markdown", ""),
        state.get("report_source_snapshot", {}),
    )
    return {
        **state,
        "sender": "report_verify",
        "report_verify_result": verify_result,
        "task_completed": False,
    }


async def report_repair_once_node(state: AgentState) -> AgentState:
    """verifier 不通过时最多修复一次。"""
    markdown = await repair_report_once(
        report_context=state.get("report_context", {}),
        final_markdown=state.get("report_markdown", ""),
        verify_result=state.get("report_verify_result", {}),
        skill_text=load_report_skill(),
    )
    markdown = ensure_source_match_warning(
        markdown,
        state.get("report_source_match_result"),
    )
    return {
        **state,
        "sender": "report_repair_once",
        "report_markdown": markdown,
        "report_repair_attempted": True,
        "task_completed": False,
    }


async def save_report_run_node(state: AgentState) -> AgentState:
    """保存 report_runs；未提供 DB/user 上下文时跳过。"""
    db = state.get("report_db_session")
    user_id = state.get("report_user_id")
    report_input = _report_input_from_state(state)
    report_context = state.get("report_context", {})
    verify_result = state.get("report_verify_result", {})
    references = report_context.get("references", [])
    source_snapshot = state.get("report_source_snapshot", {})
    source_match_result = (
        state.get("report_source_match_result")
        or check_report_source_match(None, None)
    )

    result = render_report_result(
        final_markdown=state.get("report_markdown", ""),
        verify_result=verify_result,
        references=references,
        source_snapshot=source_snapshot,
    )
    result["source_match_result"] = source_match_result

    if not db or not user_id:
        return {
            **state,
            "sender": "save_report_run",
            "report_result": result,
            "task_completed": False,
        }

    from models.report import ReportRun

    try:
        metadata = build_report_metadata(
            report_input=report_input,
            final_markdown=state.get("report_markdown", ""),
            source_snapshot=source_snapshot,
        )
    except Exception:
        logger.exception(
            "report.metadata.failed user_id=%s",
            user_id,
        )
        metadata = {
            "summary": "",
            "keywords_json": [],
            "artifact_type": "report_run",
        }
    now = utc_now()
    run = ReportRun(
        user_id=user_id,
        report_type=report_input.report_type,
        title=report_input.title or report_context.get("title") or "质量问题分析报告",
        summary=metadata.get("summary") or "",
        keywords_json=metadata.get("keywords_json") or [],
        artifact_type="report_run",
        fmea_run_id=_coerce_int(report_input.fmea_run_id),
        audit_run_id=_coerce_int(report_input.audit_run_id),
        quality_case_id=report_input.quality_case_id,
        extra_background=report_input.extra_background,
        source_snapshot_json=_json_ready(source_snapshot),
        source_match_result_json=_json_ready(source_match_result),
        final_markdown=state.get("report_markdown", ""),
        verify_result_json=_json_ready(verify_result),
        references_json=_json_ready(references),
        created_at=now,
        updated_at=now,
    )

    try:
        db.add(run)
        db.commit()
        db.refresh(run)
    except Exception as exc:
        logger.exception(
            "report.persist.failed user_id=%s fmea_run_id=%s audit_run_id=%s",
            user_id,
            report_input.fmea_run_id,
            report_input.audit_run_id,
        )
        db.rollback()
        return {
            **state,
            "sender": "save_report_run",
            "report_result": result,
            "report_error": f"保存报告运行记录失败：{exc}",
            "task_completed": False,
        }

    return {
        **state,
        "sender": "save_report_run",
        "report_result": result,
        "report_run_id": str(run.id),
        "task_completed": False,
    }


def _with_report_logging(
    step: str,
    node: Callable[[AgentState], Awaitable[AgentState]],
):
    async def wrapped(state: AgentState) -> AgentState:
        user_id = state.get("report_user_id")
        raw_input = state.get("report_input_raw", {})
        if not isinstance(raw_input, dict):
            raw_input = {}
        logger.info(
            "report.step.started step=%s user_id=%s fmea_run_id=%s audit_run_id=%s",
            step,
            user_id,
            raw_input.get("fmea_run_id"),
            raw_input.get("audit_run_id"),
        )
        try:
            result = await node(state)
        except Exception:
            logger.exception(
                "report.step.failed step=%s user_id=%s fmea_run_id=%s "
                "audit_run_id=%s",
                step,
                user_id,
                raw_input.get("fmea_run_id"),
                raw_input.get("audit_run_id"),
            )
            raise

        match_result = result.get("report_source_match_result", {})
        logger.info(
            "report.step.completed step=%s user_id=%s retrieved_count=%s "
            "matched=%s manual_check_required=%s passed=%s report_run_id=%s",
            step,
            user_id,
            (
                len(result.get("report_rag_refs", []))
                if step == "optional_rag"
                else None
            ),
            match_result.get("matched") if step == "source_match_check" else None,
            (
                match_result.get("manual_check_required")
                if step == "source_match_check"
                else None
            ),
            (
                result.get("report_verify_result", {}).get("passed")
                if step == "verifier"
                else None
            ),
            result.get("report_run_id") if step == "persist" else None,
        )
        return result

    return wrapped


async def final_response_node(state: AgentState) -> AgentState:
    """包装最终响应消息。"""
    messages = list(state.get("messages", []))
    final_markdown = state.get("report_markdown") or state.get("report_error") or "报告生成失败，需人工确认。"
    if state.get("report_error") and state.get("report_markdown"):
        final_markdown = f"{state.get('report_markdown')}\n\n> {state.get('report_error')}"

    return {
        **state,
        "messages": messages + [AIMessage(content=final_markdown, name="report_agent")],
        "sender": "final_response",
        "task_completed": True,
    }


def _after_intake(state: AgentState) -> Literal["report_load_sources", "final_response"]:
    """输入不合法时直接输出错误响应。"""
    if state.get("task_completed"):
        return "final_response"
    return "report_load_sources"


def _after_verify(state: AgentState) -> Literal["report_repair_once", "save_report_run"]:
    """校验失败最多进入一次 repair。"""
    verify_result = state.get("report_verify_result", {})
    if verify_result.get("passed", False):
        return "save_report_run"
    if state.get("report_repair_attempted", False):
        return "save_report_run"
    return "report_repair_once"


def build_report_graph():
    """构建独立 Report LangGraph 工作流。"""
    workflow = StateGraph(AgentState)

    workflow.add_node("report_intake", _with_report_logging("input_check", report_intake_node))
    workflow.add_node(
        "report_load_sources",
        _with_report_logging("source_loading", report_load_sources_node),
    )
    workflow.add_node(
        "report_source_match",
        _with_report_logging("source_match_check", report_source_match_node),
    )
    workflow.add_node(
        "report_optional_rag_retrieve",
        _with_report_logging("optional_rag", report_optional_rag_retrieve_node),
    )
    workflow.add_node(
        "report_context_builder",
        _with_report_logging("context_build", report_context_builder_node),
    )
    workflow.add_node("report_writer", _with_report_logging("writer", report_writer_node))
    workflow.add_node("report_verify", _with_report_logging("verifier", report_verify_node))
    workflow.add_node(
        "report_repair_once",
        _with_report_logging("repair", report_repair_once_node),
    )
    workflow.add_node("save_report_run", _with_report_logging("persist", save_report_run_node))
    workflow.add_node(
        "final_response",
        _with_report_logging("final_response", final_response_node),
    )

    workflow.add_edge(START, "report_intake")
    workflow.add_conditional_edges(
        "report_intake",
        _after_intake,
        {
            "report_load_sources": "report_load_sources",
            "final_response": "final_response",
        },
    )
    workflow.add_edge("report_load_sources", "report_source_match")
    workflow.add_edge("report_source_match", "report_optional_rag_retrieve")
    workflow.add_edge("report_optional_rag_retrieve", "report_context_builder")
    workflow.add_edge("report_context_builder", "report_writer")
    workflow.add_edge("report_writer", "report_verify")
    workflow.add_conditional_edges(
        "report_verify",
        _after_verify,
        {
            "report_repair_once": "report_repair_once",
            "save_report_run": "save_report_run",
        },
    )
    workflow.add_edge("report_repair_once", "report_verify")
    workflow.add_edge("save_report_run", "final_response")
    workflow.add_edge("final_response", END)

    return workflow.compile()

"""
Audit Check LangGraph 工作流。

该图是独立入口，不修改现有 qa/rag/writer 主图行为，也不修改 FMEA graph。
流程：
audit_intake -> audit_retrieval_planner -> audit_rag_retrieve -> audit_check
-> audit_verify -> audit_repair_once(可选，最多一次) -> audit_writer -> save_audit_run
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from agents.audit_agent import (
    _coerce_findings,
    _extract_json,
    _get_llm,
    generate_audit_findings,
    load_audit_skill,
    normalize_audit_input,
    render_audit_markdown,
)
from schemas.audit import AuditInput
from state import AgentState
from tools.audit_retrieval import build_audit_queries
from verifiers.audit_verifier import verify_audit_output


FIELD_LABELS = {
    "audit_type": ("audit_type", "审核类型", "类型"),
    "content": ("content", "待审核文本", "内容", "审核内容"),
    "focus": ("focus", "审核重点", "重点"),
    "background": ("background", "背景", "补充背景", "补充信息"),
}


def _last_user_text(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return str(msg.content).strip()
        if hasattr(msg, "content") and "user" in (getattr(msg, "name", "") or ""):
            return str(msg.content).strip()
    return ""


def _extract_labeled_payload(text: str) -> dict[str, str]:
    payload: dict[str, str] = {}
    if not text:
        return payload

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        for field, labels in FIELD_LABELS.items():
            label_pattern = "|".join(re.escape(label) for label in labels)
            match = re.match(rf"^(?:{label_pattern})\s*[:：]\s*(.+)$", line, re.I)
            if match:
                payload[field] = match.group(1).strip()

    if "content" not in payload and text:
        payload["content"] = text
    payload.setdefault("audit_type", "general")
    return payload


def _state_payload(state: AgentState) -> dict[str, Any]:
    raw = state.get("audit_input_raw") or state.get("audit_input") or {}
    if isinstance(raw, dict) and raw:
        return raw
    return _extract_labeled_payload(_last_user_text(list(state.get("messages", []))))


def _audit_input_from_state(state: AgentState) -> AuditInput:
    raw = state.get("audit_input") or {}
    if isinstance(raw, AuditInput):
        return raw
    return AuditInput.model_validate(raw)


def _findings_to_dicts(findings: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for finding in findings:
        if hasattr(finding, "model_dump"):
            result.append(finding.model_dump())
        elif isinstance(finding, dict):
            result.append(finding)
    return result


def _dedupe_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for chunk in chunks:
        uid = chunk.get("chunk_uid") or chunk.get("text", "")
        if uid and uid in seen:
            continue
        if uid:
            seen.add(uid)
        unique.append(chunk)
    return unique


def _citation_map(chunks: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
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


def _missing_fields_message(missing_fields: list[str]) -> str:
    if "content" in missing_fields:
        return (
            "审核检查还缺少待审核文本 content。\n\n"
            "请粘贴需要审核的质量问题描述、PFMEA 内容或审核记录后再提交。"
        )
    if "audit_type" in missing_fields:
        return (
            "审核类型 audit_type 不合法。\n\n"
            "请使用 quality_issue、pfmea、audit_record 或 general。"
        )
    return "审核检查输入不完整，请补充必要信息。"


def _collections_for_query(query: str) -> list[str]:
    from config import MILVUS_COLLECTION_FMEA, MILVUS_COLLECTION_QUALITY

    upper_query = query.upper()
    has_fmea = "FMEA" in upper_query or "PFMEA" in upper_query
    has_quality = "VDA" in upper_query or "质量" in query or "审核" in query
    if has_fmea and not has_quality:
        return [MILVUS_COLLECTION_FMEA]
    if has_quality and not has_fmea:
        return [MILVUS_COLLECTION_QUALITY]
    return [MILVUS_COLLECTION_QUALITY, MILVUS_COLLECTION_FMEA]


async def audit_intake_node(state: AgentState) -> AgentState:
    """规范化 Audit 输入；content 为空则直接返回补充提示。"""
    messages = list(state.get("messages", []))
    audit_input, missing_fields = normalize_audit_input(_state_payload(state))
    if missing_fields:
        answer = _missing_fields_message(missing_fields)
        return {
            **state,
            "messages": messages + [AIMessage(content=answer, name="audit_agent")],
            "sender": "audit_intake",
            "audit_missing_fields": missing_fields,
            "task_completed": True,
        }

    return {
        **state,
        "messages": messages,
        "sender": "audit_intake",
        "audit_input": audit_input.model_dump() if audit_input else {},
        "audit_missing_fields": [],
        "audit_repair_attempted": False,
        "task_completed": False,
    }


async def audit_retrieval_planner_node(state: AgentState) -> AgentState:
    """基于 AuditInput 生成 RAG 检索 query。"""
    audit_input = _audit_input_from_state(state)
    queries = build_audit_queries(audit_input)
    return {
        **state,
        "sender": "audit_retrieval_planner",
        "audit_retrieval_queries": queries,
        "task_completed": False,
    }


async def audit_rag_retrieve_node(state: AgentState) -> AgentState:
    """复用现有 RAG 检索函数检索 VDA6.4 / FMEA 知识库。"""
    from tools.rag import chunks_to_text, retrieve_structured

    queries = state.get("audit_retrieval_queries", [])
    loop = asyncio.get_event_loop()
    all_chunks: list[dict[str, Any]] = []

    for query in queries:
        for collection_name in _collections_for_query(str(query)):
            chunks = await loop.run_in_executor(
                None,
                retrieve_structured,
                query,
                collection_name,
            )
            all_chunks.extend(chunks)

    rag_chunks = _dedupe_chunks(all_chunks)
    return {
        **state,
        "sender": "audit_rag_retrieve",
        "rag_chunks": rag_chunks,
        "rag_result": chunks_to_text(rag_chunks),
        "citation_map": _citation_map(rag_chunks),
        "citation_ids": list(range(1, len(rag_chunks) + 1)),
        "rag_is_relevant": bool(rag_chunks),
        "task_completed": False,
    }


async def audit_check_node(state: AgentState) -> AgentState:
    """调用审核检查 Agent 生成结构化 findings。"""
    audit_input = _audit_input_from_state(state)
    findings = await generate_audit_findings(
        audit_input=audit_input,
        retrieved_docs=state.get("rag_chunks", []),
        skill_text=load_audit_skill(),
    )
    return {
        **state,
        "sender": "audit_check",
        "audit_findings": _findings_to_dicts(findings),
        "task_completed": False,
    }


async def audit_verify_node(state: AgentState) -> AgentState:
    """校验审核 findings，决定是否需要一次修复。"""
    verification = verify_audit_output(
        {
            "findings": state.get("audit_findings", []),
        },
        retrieved_docs=state.get("rag_chunks", []),
    )
    return {
        **state,
        "sender": "audit_verify",
        "audit_verification": verification,
        "task_completed": False,
    }


async def audit_repair_once_node(state: AgentState) -> AgentState:
    """根据 verifier 修复提示最多修复一次 findings。"""
    audit_input = _audit_input_from_state(state)
    verification = state.get("audit_verification", {})
    repair_instruction = verification.get("repair_instruction", "")
    issues = verification.get("issues", [])
    findings = state.get("audit_findings", [])
    docs = state.get("rag_chunks", [])

    prompt = f"""请修复下面的审核检查 JSON findings。

【审核输入】
{json.dumps(audit_input.model_dump(), ensure_ascii=False)}

【校验问题】
{json.dumps(issues, ensure_ascii=False)}

【修复要求】
{repair_instruction}

【retrieved_docs】
{json.dumps(docs, ensure_ascii=False)}

【待修复 findings】
{json.dumps(findings, ensure_ascii=False)}

只输出 JSON 对象，格式为 {{"findings": [...]}}，不要输出 Markdown。"""

    response = await _get_llm().ainvoke([HumanMessage(content=prompt)])
    content = response.content if hasattr(response, "content") else str(response)
    repaired_findings = _coerce_findings(_extract_json(str(content)))

    return {
        **state,
        "sender": "audit_repair_once",
        "audit_findings": _findings_to_dicts(repaired_findings),
        "audit_repair_attempted": True,
        "task_completed": False,
    }


async def audit_writer_node(state: AgentState) -> AgentState:
    """只渲染和包装审核 findings，不改写 findings 内容。"""
    messages = list(state.get("messages", []))
    audit_input = _audit_input_from_state(state)
    findings = _coerce_findings(state.get("audit_findings", []))
    markdown = render_audit_markdown(audit_input, findings)

    verification = state.get("audit_verification", {})
    if verification and not verification.get("passed", True):
        issues = verification.get("issues", [])
        warning = "\n\n## 校验提示\n\n"
        warning += "以下问题仍需人工确认：\n"
        warning += "\n".join(f"- {issue}" for issue in issues)
        markdown += warning

    return {
        **state,
        "messages": messages + [AIMessage(content=markdown, name="audit_agent")],
        "sender": "audit_writer",
        "audit_markdown": markdown,
        "task_completed": False,
    }


async def save_audit_run_node(state: AgentState) -> AgentState:
    """保存 audit run 记录；未提供 DB 上下文时跳过。"""
    db = state.get("audit_db_session")
    user_id = state.get("audit_user_id")
    session_id = state.get("audit_session_id")

    if not db or not user_id or not session_id:
        return {
            **state,
            "sender": "save_audit_run",
            "task_completed": True,
        }

    from models.audit import AuditRun

    audit_input = _audit_input_from_state(state)
    run = AuditRun(
        user_id=user_id,
        session_id=session_id,
        audit_type=audit_input.audit_type,
        content_text=audit_input.content,
        focus=audit_input.focus,
        background=audit_input.background,
        retrieval_queries_json=state.get("audit_retrieval_queries", []),
        retrieved_refs_json=state.get("citation_map", {}),
        findings_json={"findings": state.get("audit_findings", [])},
        final_markdown=state.get("audit_markdown", ""),
        verify_result_json=state.get("audit_verification", {}),
    )

    try:
        db.add(run)
        db.commit()
        db.refresh(run)
    except Exception as exc:
        db.rollback()
        return {
            **state,
            "sender": "save_audit_run",
            "audit_error": f"保存审核检查运行记录失败：{exc}",
            "task_completed": True,
        }

    return {
        **state,
        "sender": "save_audit_run",
        "audit_run_id": str(run.id),
        "task_completed": True,
    }


def _after_intake(state: AgentState) -> Literal["audit_retrieval_planner", "__end__"]:
    if state.get("task_completed"):
        return "__end__"
    return "audit_retrieval_planner"


def _after_verify(state: AgentState) -> Literal["audit_repair_once", "audit_writer"]:
    verification = state.get("audit_verification", {})
    if verification.get("passed", False):
        return "audit_writer"
    if state.get("audit_repair_attempted", False):
        return "audit_writer"
    return "audit_repair_once"


def build_audit_graph():
    """构建独立 Audit Check LangGraph 工作流。"""
    workflow = StateGraph(AgentState)

    workflow.add_node("audit_intake", audit_intake_node)
    workflow.add_node("audit_retrieval_planner", audit_retrieval_planner_node)
    workflow.add_node("audit_rag_retrieve", audit_rag_retrieve_node)
    workflow.add_node("audit_check", audit_check_node)
    workflow.add_node("audit_verify", audit_verify_node)
    workflow.add_node("audit_repair_once", audit_repair_once_node)
    workflow.add_node("audit_writer", audit_writer_node)
    workflow.add_node("save_audit_run", save_audit_run_node)

    workflow.add_edge(START, "audit_intake")
    workflow.add_conditional_edges(
        "audit_intake",
        _after_intake,
        {
            "audit_retrieval_planner": "audit_retrieval_planner",
            "__end__": END,
        },
    )
    workflow.add_edge("audit_retrieval_planner", "audit_rag_retrieve")
    workflow.add_edge("audit_rag_retrieve", "audit_check")
    workflow.add_edge("audit_check", "audit_verify")
    workflow.add_conditional_edges(
        "audit_verify",
        _after_verify,
        {
            "audit_repair_once": "audit_repair_once",
            "audit_writer": "audit_writer",
        },
    )
    workflow.add_edge("audit_repair_once", "audit_verify")
    workflow.add_edge("audit_writer", "save_audit_run")
    workflow.add_edge("save_audit_run", END)

    return workflow.compile()

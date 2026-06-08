"""
FMEA LangGraph 工作流。

该图是独立入口，不修改现有 qa/rag/writer 主图行为。
流程：
fmea_intake -> fmea_retrieval_planner -> fmea_rag_retrieve -> fmea_generate
-> fmea_verify -> fmea_repair_once(可选) -> fmea_writer -> save_fmea_run
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph

from agents.fmea_agent import (
    _coerce_rows,
    _extract_json,
    _get_llm,
    generate_fmea_rows,
    load_fmea_skill,
    normalize_fmea_input,
    render_fmea_markdown,
)
from agents.artifact_metadata import build_fmea_metadata
from schemas.fmea import FMEAInput
from state import AgentState
from time_utils import utc_now
from tools.fmea_retrieval import build_fmea_queries
from verifiers.fmea_verifier import verify_fmea_output


FIELD_LABELS = {
    "product": ("product", "产品", "对象", "分析对象"),
    "process": ("process", "工序", "过程", "目标工序"),
    "failure_phenomenon": ("failure_phenomenon", "问题现象", "失效现象", "现象"),
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
            match = re.match(rf"^(?:{label_pattern})\s*[:：=]\s*(.+)$", line, re.I)
            if match:
                payload[field] = match.group(1).strip()

    return payload


def _state_payload(state: AgentState) -> dict[str, Any]:
    raw = state.get("fmea_input_raw") or state.get("fmea_input") or {}
    if isinstance(raw, dict) and raw:
        return raw
    return _extract_labeled_payload(_last_user_text(list(state.get("messages", []))))


def _fmea_input_from_state(state: AgentState) -> FMEAInput:
    raw = state.get("fmea_input") or {}
    if isinstance(raw, FMEAInput):
        return raw
    return FMEAInput.model_validate(raw)


def _rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        if hasattr(row, "model_dump"):
            result.append(row.model_dump())
        elif isinstance(row, dict):
            result.append(row)
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
    labels = {
        "product": "分析对象/产品名称",
        "process": "目标工序",
        "failure_phenomenon": "问题现象/失效现象",
    }
    missing_text = "、".join(labels.get(field, field) for field in missing_fields)
    return (
        f"生成 PFMEA 还缺少必要信息：{missing_text}。\n\n"
        "请按下面格式补充：\n"
        "- 产品：\n"
        "- 工序：\n"
        "- 问题现象：\n"
        "- 背景：可选"
    )


async def fmea_intake_node(state: AgentState) -> AgentState:
    """规范化 FMEA 输入；缺字段则直接返回补充提示。"""
    messages = list(state.get("messages", []))
    fmea_input, missing_fields = normalize_fmea_input(_state_payload(state))
    if missing_fields:
        answer = _missing_fields_message(missing_fields)
        return {
            **state,
            "messages": messages + [AIMessage(content=answer, name="fmea_agent")],
            "sender": "fmea_intake",
            "fmea_missing_fields": missing_fields,
            "task_completed": True,
        }

    return {
        **state,
        "messages": messages,
        "sender": "fmea_intake",
        "fmea_input": fmea_input.model_dump() if fmea_input else {},
        "fmea_missing_fields": [],
        "fmea_repair_attempted": False,
        "task_completed": False,
    }


async def fmea_retrieval_planner_node(state: AgentState) -> AgentState:
    """基于 FMEAInput 生成 RAG 检索 query。"""
    fmea_input = _fmea_input_from_state(state)
    queries = build_fmea_queries(fmea_input)
    return {
        **state,
        "sender": "fmea_retrieval_planner",
        "fmea_retrieval_queries": queries,
        "task_completed": False,
    }


async def fmea_rag_retrieve_node(state: AgentState) -> AgentState:
    """复用现有 RAG 检索函数检索 FMEA 知识库。"""
    from config import MILVUS_COLLECTION_FMEA
    from tools.rag import chunks_to_text, retrieve_structured

    queries = state.get("fmea_retrieval_queries", [])
    loop = asyncio.get_event_loop()
    all_chunks: list[dict[str, Any]] = []

    for query in queries:
        chunks = await loop.run_in_executor(
            None,
            retrieve_structured,
            query,
            MILVUS_COLLECTION_FMEA,
        )
        all_chunks.extend(chunks)

    rag_chunks = _dedupe_chunks(all_chunks)
    return {
        **state,
        "sender": "fmea_rag_retrieve",
        "rag_chunks": rag_chunks,
        "rag_result": chunks_to_text(rag_chunks),
        "citation_map": _citation_map(rag_chunks),
        "citation_ids": list(range(1, len(rag_chunks) + 1)),
        "rag_is_relevant": bool(rag_chunks),
        "task_completed": False,
    }


async def fmea_generate_node(state: AgentState) -> AgentState:
    """调用 FMEA Agent 生成结构化 rows。"""
    fmea_input = _fmea_input_from_state(state)
    rows = await generate_fmea_rows(
        fmea_input=fmea_input,
        retrieved_docs=state.get("rag_chunks", []),
        skill_text=load_fmea_skill(),
    )
    return {
        **state,
        "sender": "fmea_generate",
        "fmea_rows": _rows_to_dicts(rows),
        "task_completed": False,
    }


async def fmea_verify_node(state: AgentState) -> AgentState:
    """校验 FMEA rows，决定是否需要一次修复。"""
    verification = verify_fmea_output(
        {
            "rows": state.get("fmea_rows", []),
            "retrieved_docs": state.get("rag_chunks", []),
        }
    )
    return {
        **state,
        "sender": "fmea_verify",
        "fmea_verification": verification,
        "task_completed": False,
    }


async def fmea_repair_once_node(state: AgentState) -> AgentState:
    """根据 verifier 的修复提示最多修复一次 rows。"""
    fmea_input = _fmea_input_from_state(state)
    verification = state.get("fmea_verification", {})
    repair_instruction = verification.get("repair_instruction", "")
    issues = verification.get("issues", [])
    rows = state.get("fmea_rows", [])
    docs = state.get("rag_chunks", [])

    prompt = f"""请修复下面的 PFMEA JSON rows。

【FMEA 输入】
{json.dumps(fmea_input.model_dump(), ensure_ascii=False)}

【校验问题】
{json.dumps(issues, ensure_ascii=False)}

【修复要求】
{repair_instruction}

【retrieved_docs】
{json.dumps(docs, ensure_ascii=False)}

【待修复 rows】
{json.dumps(rows, ensure_ascii=False)}

只输出 JSON 对象，格式为 {{"rows": [...]}}，不要输出 Markdown。"""

    response = await _get_llm().ainvoke([HumanMessage(content=prompt)])
    content = response.content if hasattr(response, "content") else str(response)
    repaired_rows = _coerce_rows(_extract_json(str(content)), fmea_input)

    return {
        **state,
        "sender": "fmea_repair_once",
        "fmea_rows": _rows_to_dicts(repaired_rows),
        "fmea_repair_attempted": True,
        "task_completed": False,
    }


async def fmea_writer_node(state: AgentState) -> AgentState:
    """只渲染和包装 FMEA rows，不改写内容。"""
    messages = list(state.get("messages", []))
    fmea_input = _fmea_input_from_state(state)
    rows = _coerce_rows(state.get("fmea_rows", []), fmea_input)
    markdown = render_fmea_markdown(fmea_input, rows)

    verification = state.get("fmea_verification", {})
    if verification and not verification.get("passed", True):
        issues = verification.get("issues", [])
        warning = "\n\n## 校验提示\n\n"
        warning += "以下问题仍需人工确认：\n"
        warning += "\n".join(f"- {issue}" for issue in issues)
        markdown += warning

    return {
        **state,
        "messages": messages + [AIMessage(content=markdown, name="fmea_agent")],
        "sender": "fmea_writer",
        "fmea_markdown": markdown,
        "task_completed": False,
    }


async def save_fmea_run_node(state: AgentState) -> AgentState:
    """保存 FMEA run 记录；未提供 DB 上下文时跳过。"""
    db = state.get("fmea_db_session")
    user_id = state.get("fmea_user_id")
    session_id = state.get("fmea_session_id")

    if not db or not user_id or not session_id:
        return {
            **state,
            "sender": "save_fmea_run",
            "task_completed": True,
        }

    from models.fmea import FMEARun

    fmea_input = _fmea_input_from_state(state)
    input_json = fmea_input.model_dump()
    output_json = {"rows": state.get("fmea_rows", [])}
    output_markdown = state.get("fmea_markdown", "")
    retrieved_refs_json = state.get("citation_map", {})
    try:
        metadata = build_fmea_metadata(
            input_data=input_json,
            output_json=output_json,
            output_markdown=output_markdown,
            retrieved_refs=retrieved_refs_json,
        )
    except Exception:
        metadata = {
            "title": "FMEA分析",
            "summary": "",
            "keywords_json": [],
            "artifact_type": "fmea_run",
            "references_json": [],
        }
    now = utc_now()
    raw_input = state.get("fmea_input_raw", {})
    quality_case_id = raw_input.get("quality_case_id") if isinstance(raw_input, dict) else None
    run = FMEARun(
        user_id=user_id,
        session_id=session_id,
        title=metadata.get("title") or "FMEA分析",
        summary=metadata.get("summary") or "",
        keywords_json=metadata.get("keywords_json") or [],
        artifact_type="fmea_run",
        references_json=metadata.get("references_json") or [],
        quality_case_id=quality_case_id,
        product=fmea_input.product,
        process=fmea_input.process,
        failure_phenomenon=fmea_input.failure_phenomenon,
        input_json=input_json,
        retrieval_queries_json=state.get("fmea_retrieval_queries", []),
        retrieved_refs_json=retrieved_refs_json,
        output_json=output_json,
        output_markdown=output_markdown,
        verify_result_json=state.get("fmea_verification", {}),
        created_at=now,
        updated_at=now,
    )

    try:
        db.add(run)
        if callable(getattr(db, "flush", None)) and callable(getattr(db, "query", None)):
            from services.artifact_revision_service import create_initial_fmea_version

            db.flush()
            initial_version = create_initial_fmea_version(db, run)
        else:
            initial_version = None
        db.commit()
        db.refresh(run)
    except Exception as exc:
        db.rollback()
        return {
            **state,
            "sender": "save_fmea_run",
            "fmea_error": f"保存 FMEA 运行记录失败：{exc}",
            "task_completed": True,
        }

    return {
        **state,
        "sender": "save_fmea_run",
        "fmea_run_id": str(run.id),
        "fmea_current_version_id": initial_version.id if initial_version else None,
        "fmea_current_version_no": initial_version.version_no if initial_version else None,
        "task_completed": True,
    }


def _after_intake(state: AgentState) -> Literal["fmea_retrieval_planner", "__end__"]:
    if state.get("task_completed"):
        return "__end__"
    return "fmea_retrieval_planner"


def _after_verify(state: AgentState) -> Literal["fmea_repair_once", "fmea_writer"]:
    verification = state.get("fmea_verification", {})
    if verification.get("passed", False):
        return "fmea_writer"
    if state.get("fmea_repair_attempted", False):
        return "fmea_writer"
    return "fmea_repair_once"


def build_fmea_graph():
    """构建独立 FMEA LangGraph 工作流。"""
    workflow = StateGraph(AgentState)

    workflow.add_node("fmea_intake", fmea_intake_node)
    workflow.add_node("fmea_retrieval_planner", fmea_retrieval_planner_node)
    workflow.add_node("fmea_rag_retrieve", fmea_rag_retrieve_node)
    workflow.add_node("fmea_generate", fmea_generate_node)
    workflow.add_node("fmea_verify", fmea_verify_node)
    workflow.add_node("fmea_repair_once", fmea_repair_once_node)
    workflow.add_node("fmea_writer", fmea_writer_node)
    workflow.add_node("save_fmea_run", save_fmea_run_node)

    workflow.add_edge(START, "fmea_intake")
    workflow.add_conditional_edges(
        "fmea_intake",
        _after_intake,
        {
            "fmea_retrieval_planner": "fmea_retrieval_planner",
            "__end__": END,
        },
    )
    workflow.add_edge("fmea_retrieval_planner", "fmea_rag_retrieve")
    workflow.add_edge("fmea_rag_retrieve", "fmea_generate")
    workflow.add_edge("fmea_generate", "fmea_verify")
    workflow.add_conditional_edges(
        "fmea_verify",
        _after_verify,
        {
            "fmea_repair_once": "fmea_repair_once",
            "fmea_writer": "fmea_writer",
        },
    )
    workflow.add_edge("fmea_repair_once", "fmea_verify")
    workflow.add_edge("fmea_writer", "save_fmea_run")
    workflow.add_edge("save_fmea_run", END)

    return workflow.compile()

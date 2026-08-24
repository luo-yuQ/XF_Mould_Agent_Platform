"""销售协作 Specialist 包装层的共享辅助逻辑。"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.structured_llm import invoke_structured_json
from config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_BASE_URL,
    LLM_MODEL,
    LLM_TEMPERATURE,
)
from schemas.sales_collaboration import Citation, SpecialistOutput


Retriever = Callable[[str, str], list[dict[str, Any]]]


def retrieve_sales_chunks(query: str, collection_name: str) -> list[dict[str, Any]]:
    """调用现有 RAG；懒导入避免 mock 测试加载 Milvus/Embedding 依赖。"""
    from tools.rag import retrieve_structured

    return retrieve_structured(query, collection_name)


def get_sales_specialist_llm():
    """按需创建 LLM，避免导入 graph 时初始化外部客户端。"""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=LLM_TEMPERATURE,
        api_key=DASHSCOPE_API_KEY,
        base_url=DASHSCOPE_BASE_URL,
        extra_body={"thinking": {"type": "disabled"}},
    )


def find_task(execution_plan: list[dict[str, Any]], task_id: str) -> dict[str, Any]:
    """从 Planner 任务列表中找到当前 Specialist 的任务。"""
    return next(
        (dict(task) for task in execution_plan if task.get("task_id") == task_id),
        {},
    )


def build_retrieval_query(
    user_request: str,
    customer_context: dict[str, Any],
    task: dict[str, Any],
) -> str:
    """把协作输入压缩为现有 RAG 可直接使用的检索文本。"""
    parts = [user_request.strip(), str(task.get("objective") or "").strip()]
    if customer_context:
        parts.append(json.dumps(customer_context, ensure_ascii=False, sort_keys=True))
    return "\n".join(part for part in parts if part)


def chunks_to_citations(
    chunks: list[dict[str, Any]],
    citation_prefix: str,
) -> tuple[dict[str, Citation], str]:
    """将现有 RAG chunk 映射为 Phase B Citation 和 prompt 材料。"""
    citation_map: dict[str, Citation] = {}
    prompt_blocks: list[str] = []

    for index, chunk in enumerate(chunks, 1):
        chunk_id = str(chunk.get("chunk_uid") or chunk.get("chunk_id") or "").strip()
        citation_id = chunk_id or f"{citation_prefix}-{index:03d}"
        source_name = str(chunk.get("doc_source") or "unknown_source")
        title = (
            chunk.get("heading_path")
            or chunk.get("doc_section")
            or chunk.get("title")
            or None
        )
        text = str(chunk.get("text") or "").strip()
        raw_page = chunk.get("page")
        try:
            page = int(raw_page) if raw_page is not None else None
        except (TypeError, ValueError):
            page = None

        citation = Citation(
            citation_id=citation_id,
            source_type=str(chunk.get("chunk_type") or "document"),
            source_name=source_name,
            title=str(title) if title else None,
            page=page,
            chunk_id=chunk_id or None,
            quote=text[:500] or None,
        )
        citation_map[citation_id] = citation
        prompt_blocks.append(
            f"[{citation_id}] source={source_name}; title={title or ''}\n{text}"
        )

    return citation_map, "\n\n".join(prompt_blocks)


def _extract_json(text: str) -> Any:
    """从 LLM 输出中提取 JSON，兼容 markdown 代码块和 Python dict 字符串。"""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if not match:
            raise
        raw = match.group(1)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # 兼容 Python dict 字符串（单引号），如 mock LLM 返回的 str(dict)
            return ast.literal_eval(raw)


def _coerce_specialist_data(data: Any) -> dict[str, Any]:
    """
    将 LLM 输出规范化为 SpecialistOutput 可接受的 dict。

    处理常见模型偏差：
    - 输出被包裹在 task 对象中（缺少顶层 summary/confidence）
    - missing_information 是字符串列表而非对象列表
    - claims/risks/recommendations 项缺少必要字段
    """
    if not isinstance(data, dict):
        return {"summary": str(data), "confidence": "low"}

    # 如果顶层缺少 summary，可能是模型把输出嵌套在 task 对象中
    if "summary" not in data and "claims" not in data:
        # 尝试从嵌套中提取
        for key in ("output", "result", "data", "analysis"):
            if key in data and isinstance(data[key], dict):
                return _coerce_specialist_data(data[key])
        # 无法提取，构造最小可用结构
        return {
            "summary": json.dumps(data, ensure_ascii=False)[:500],
            "confidence": "low",
        }

    # 规范化 missing_information：字符串 → 对象
    raw_missing = data.get("missing_information", [])
    if isinstance(raw_missing, list):
        normalized = []
        for item in raw_missing:
            if isinstance(item, str):
                normalized.append({
                    "item_id": f"missing-{len(normalized)+1}",
                    "question": item,
                    "reason": "LLM 输出格式偏差，已自动规范化",
                    "required_for": None,
                })
            elif isinstance(item, dict):
                normalized.append(item)
        data["missing_information"] = normalized

    # 规范化 claims/risks/recommendations：字符串 → 对象，dict 补齐缺失字段
    for field, id_field, text_key in (
        ("claims", "claim_id", "text"),
        ("risks", "risk_id", "description"),
        ("recommendations", "recommendation_id", "text"),
    ):
        raw_items = data.get(field, [])
        if isinstance(raw_items, list):
            normalized = []
            for item in raw_items:
                if isinstance(item, str):
                    entry: dict[str, Any] = {
                        id_field: f"{id_field.replace('_id', '')}-{len(normalized)+1}",
                        text_key: item,
                        "citations": [],
                        "requires_manual_check": True,
                    }
                    if field == "claims":
                        entry["confidence"] = "low"
                    normalized.append(entry)
                elif isinstance(item, dict):
                    # 补齐 LLM 常漏的必填字段
                    if id_field not in item:
                        item[id_field] = f"{id_field.replace('_id', '')}-{len(normalized)+1}"
                    if text_key not in item:
                        # 尝试从常见别名中提取
                        for fallback in ("text", "description", "summary", "content"):
                            if fallback in item and item[fallback]:
                                item[text_key] = item[fallback]
                                break
                        else:
                            item[text_key] = json.dumps(item, ensure_ascii=False)[:300]
                    if field == "risks" and "category" not in item:
                        item["category"] = item.get("type", "general")
                    normalized.append(item)
            data[field] = normalized

    # 规范化 citations：字符串 citation_id → Citation 对象
    raw_citations = data.get("citations", [])
    if isinstance(raw_citations, list):
        normalized_citations = []
        for item in raw_citations:
            if isinstance(item, str):
                normalized_citations.append({
                    "citation_id": item,
                    "source_type": "document",
                    "source_name": "unknown_source",
                })
            elif isinstance(item, dict):
                normalized_citations.append(item)
        data["citations"] = normalized_citations

    # 确保 confidence 存在
    if "confidence" not in data:
        data["confidence"] = "low"

    # 确保列表字段存在
    for field in ("claims", "risks", "recommendations", "citations"):
        if field not in data:
            data[field] = []

    return data


def invoke_structured_specialist(
    *,
    system_prompt: str,
    user_request: str,
    customer_context: dict[str, Any],
    execution_plan: list[dict[str, Any]],
    task: dict[str, Any],
    chunks: list[dict[str, Any]],
    citation_prefix: str,
    no_source_question: str,
    llm: Any = None,
) -> SpecialistOutput:
    """调用结构化 LLM，并将所有引用约束到真实检索 chunks。"""
    citation_map, source_text = chunks_to_citations(chunks, citation_prefix)
    prompt = f"""请完成当前销售协作 Specialist 任务。

用户请求：
{user_request}

客户上下文：
{json.dumps(customer_context, ensure_ascii=False, sort_keys=True)}

完整执行计划：
{json.dumps(execution_plan, ensure_ascii=False)}

当前任务：
{json.dumps(task, ensure_ascii=False)}

检索材料：
{source_text or "无检索材料"}

输出必须是符合 SpecialistOutput 的 JSON 对象。
引用只能使用检索材料方括号中的 citation_id；不得编造引用。
没有检索材料时 citations 必须为空，confidence 不得为 high，并在 missing_information 中说明信息缺口。
"""
    model = llm or get_sales_specialist_llm()
    system_msg = SystemMessage(
        content=(
            f"{system_prompt}\n\n"
            "你必须只返回合法的 JSON 对象，不要输出 Markdown 或 ```json 代码块。"
            "整个响应必须是一个符合 SpecialistOutput schema 的 JSON 对象，"
            "JSON 必须是全部响应内容。"
        )
    )
    human_msg = HumanMessage(content=prompt)

    # 优先使用 json_mode（DashScope 兼容），失败后回退到原始 LLM + 手动解析
    try:
        raw_output = invoke_structured_json(
            model,
            SpecialistOutput,
            [system_msg, human_msg],
        )
        output = SpecialistOutput.model_validate(raw_output)
    except Exception:
        # 回退：原始 LLM 调用 + JSON 提取 + 数据规范化 + Pydantic 校验
        response = model.invoke([system_msg, human_msg])
        content = response.content if hasattr(response, "content") else str(response)
        data = _coerce_specialist_data(_extract_json(str(content)))
        output = SpecialistOutput.model_validate(data)

    return normalize_specialist_output(
        output,
        citation_map=citation_map,
        no_source_question=no_source_question,
    )


def normalize_specialist_output(
    output: SpecialistOutput,
    *,
    citation_map: dict[str, Citation],
    no_source_question: str,
) -> SpecialistOutput:
    """移除虚构引用，并确保无材料输出明确降级。"""
    data = output.model_dump()
    used_ids: list[str] = []

    def normalize_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized = []
        for citation in citations:
            citation_id = str(citation.get("citation_id") or "")
            if citation_id in citation_map and citation_id not in used_ids:
                used_ids.append(citation_id)
            if citation_id in citation_map:
                normalized.append(citation_map[citation_id].model_dump())
        return normalized

    for field in ("claims", "risks", "recommendations"):
        for item in data[field]:
            item["citations"] = normalize_citations(item.get("citations", []))
    normalize_citations(data.get("citations", []))
    data["citations"] = [
        citation_map[citation_id].model_dump() for citation_id in used_ids
    ]

    if not citation_map:
        data["citations"] = []
        for field in ("claims", "risks", "recommendations"):
            for item in data[field]:
                item["citations"] = []
        if data["confidence"] == "high":
            data["confidence"] = "medium"
        if not data["missing_information"]:
            data["missing_information"] = [
                {
                    "item_id": "missing-source-context",
                    "question": no_source_question,
                    "reason": "本次检索未返回可用于支撑结论的知识库材料。",
                    "required_for": "提高分析置信度并形成可追溯结论",
                }
            ]

    return SpecialistOutput.model_validate(data)

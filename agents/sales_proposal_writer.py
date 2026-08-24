"""销售协作 Proposal Writer：受证据约束的结构化方案生成。"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from agents.sales_specialist_common import get_sales_specialist_llm
from agents.structured_llm import invoke_structured_json
from schemas.sales_collaboration import Citation, ProposalWriterOutput


WRITER_PROMPT = """你是销售协作 Proposal Writer。
你只能选择和排序输入中已经存在的 claim、risk、recommendation ID。
不得新增事实、公司能力承诺、历史案例结论或引用。
输出必须符合给定的结构化选择 schema。

你必须只返回合法的 JSON 对象，不要输出 Markdown 或 ```json 代码块。
整个响应必须是一个符合结构化选择 schema 的 JSON 对象。
JSON 必须是全部响应内容。
"""

REPORT_HEADINGS = (
    "# 售前协作方案",
    "## 1. 客户需求理解",
    "## 2. 技术与工艺风险",
    "## 3. 质量保障分析",
    "## 4. 信息缺口与人工确认项",
    "## 5. 初步建议",
    "## 6. 引用依据",
)


class ProposalContentSelection(BaseModel):
    """LLM 只能选择已有内容 ID，不能生成业务事实。"""

    rd_claim_ids: list[str] = Field(default_factory=list)
    rd_risk_ids: list[str] = Field(default_factory=list)
    rd_recommendation_ids: list[str] = Field(default_factory=list)
    quality_claim_ids: list[str] = Field(default_factory=list)
    quality_risk_ids: list[str] = Field(default_factory=list)
    quality_recommendation_ids: list[str] = Field(default_factory=list)


def run_sales_proposal_writer(
    *,
    user_request: str,
    execution_plan: list[dict[str, Any]],
    rd_analysis: dict[str, Any],
    quality_analysis: dict[str, Any],
    review_result: dict[str, Any],
    llm: Any = None,
) -> ProposalWriterOutput:
    """用 LLM 选择已有证据，再以确定性模板渲染最终报告。"""
    indexes = {
        "rd_claim_ids": _index(rd_analysis.get("claims", []), "claim_id"),
        "rd_risk_ids": _index(rd_analysis.get("risks", []), "risk_id"),
        "rd_recommendation_ids": _index(
            rd_analysis.get("recommendations", []),
            "recommendation_id",
        ),
        "quality_claim_ids": _index(quality_analysis.get("claims", []), "claim_id"),
        "quality_risk_ids": _index(quality_analysis.get("risks", []), "risk_id"),
        "quality_recommendation_ids": _index(
            quality_analysis.get("recommendations", []),
            "recommendation_id",
        ),
    }
    selection = _default_selection(indexes)
    try:
        model = llm or get_sales_specialist_llm()
        user_content = json.dumps(
            {
                "user_request": user_request,
                "execution_plan": execution_plan,
                "available_ids": {
                    key: list(value) for key, value in indexes.items()
                },
                "review_result": review_result,
            },
            ensure_ascii=False,
        )
        messages = [
            SystemMessage(content=WRITER_PROMPT),
            HumanMessage(content=user_content),
        ]
        try:
            raw_selection = invoke_structured_json(
                model,
                ProposalContentSelection,
                messages,
            )
        except Exception:
            # 回退：原始 LLM 调用 + JSON 提取
            response = model.invoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            cleaned = re.sub(r"^```(?:json)?\s*", "", str(content).strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            raw_str = match.group(1) if match else cleaned
            try:
                raw_selection = json.loads(raw_str)
            except json.JSONDecodeError:
                raw_selection = ast.literal_eval(raw_str)

        selection = _normalize_selection(
            ProposalContentSelection.model_validate(raw_selection),
            indexes,
        )
    except Exception:
        pass

    citations = _collect_citations(rd_analysis, quality_analysis)
    final_report = _render_report(
        user_request=user_request,
        rd_analysis=rd_analysis,
        quality_analysis=quality_analysis,
        review_result=review_result,
        indexes=indexes,
        selection=selection,
        citations=citations,
    )
    summary = _build_summary(rd_analysis, quality_analysis, review_result)
    return ProposalWriterOutput(
        final_report=final_report,
        summary=summary,
        citations=citations,
    )


def _render_report(
    *,
    user_request: str,
    rd_analysis: dict[str, Any],
    quality_analysis: dict[str, Any],
    review_result: dict[str, Any],
    indexes: dict[str, dict[str, dict[str, Any]]],
    selection: ProposalContentSelection,
    citations: list[Citation],
) -> str:
    customer_request = _safe_customer_request(user_request, review_result)
    rd_items = _selected_texts(
        indexes["rd_claim_ids"],
        selection.rd_claim_ids,
        "text",
    ) + _selected_texts(
        indexes["rd_risk_ids"],
        selection.rd_risk_ids,
        "description",
    )
    quality_items = _selected_texts(
        indexes["quality_claim_ids"],
        selection.quality_claim_ids,
        "text",
    ) + _selected_texts(
        indexes["quality_risk_ids"],
        selection.quality_risk_ids,
        "description",
    )
    recommendations = _selected_texts(
        indexes["rd_recommendation_ids"],
        selection.rd_recommendation_ids,
        "text",
    ) + _selected_texts(
        indexes["quality_recommendation_ids"],
        selection.quality_recommendation_ids,
        "text",
    )
    missing = [
        str(item.get("question") or "")
        for item in [
            *rd_analysis.get("missing_information", []),
            *quality_analysis.get("missing_information", []),
        ]
        if item.get("question")
    ]
    review_items = [
        *[
            f"冲突：{item}" for item in review_result.get("conflicts", [])
        ],
        *[
            f"无依据声明：{item}"
            for item in review_result.get("unsupported_claims", [])
        ],
        *[
            f"人工确认：{item}"
            for item in review_result.get("manual_check_items", [])
        ],
        *[
            f"缺失章节：{item}"
            for item in review_result.get("missing_sections", [])
        ],
        *[
            f"修复要求：{item}"
            for item in review_result.get("repair_instructions", [])
        ],
    ]
    citation_lines = [
        (
            f"- [{citation.citation_id}] {citation.source_name}"
            + (f" - {citation.title}" if citation.title else "")
        )
        for citation in citations
    ]
    return f"""# 售前协作方案

## 1. 客户需求理解

{customer_request}

## 2. 技术与工艺风险

{_bullets([str(rd_analysis.get("summary") or ""), *rd_items])}

## 3. 质量保障分析

{_bullets([str(quality_analysis.get("summary") or ""), *quality_items])}

## 4. 信息缺口与人工确认项

{_bullets([*missing, *review_items])}

## 5. 初步建议

{_bullets(recommendations)}

## 6. 引用依据

{chr(10).join(citation_lines) or "- 暂无可追溯引用"}
"""


def _default_selection(
    indexes: dict[str, dict[str, dict[str, Any]]],
) -> ProposalContentSelection:
    return ProposalContentSelection(
        **{key: list(items) for key, items in indexes.items()}
    )


def _normalize_selection(
    selection: ProposalContentSelection,
    indexes: dict[str, dict[str, dict[str, Any]]],
) -> ProposalContentSelection:
    data = selection.model_dump()
    for key, allowed in indexes.items():
        data[key] = [item_id for item_id in data[key] if item_id in allowed]
    if not any(data.values()):
        return _default_selection(indexes)
    return ProposalContentSelection.model_validate(data)


def _index(items: list[dict[str, Any]], id_field: str) -> dict[str, dict[str, Any]]:
    return {
        str(item[id_field]): item
        for item in items
        if item.get(id_field)
    }


def _selected_texts(
    index: dict[str, dict[str, Any]],
    selected_ids: list[str],
    text_field: str,
) -> list[str]:
    return [
        str(index[item_id].get(text_field) or "")
        for item_id in selected_ids
        if item_id in index and index[item_id].get(text_field)
    ]


def _collect_citations(
    rd_analysis: dict[str, Any],
    quality_analysis: dict[str, Any],
) -> list[Citation]:
    citations: dict[str, Citation] = {}
    for analysis in (rd_analysis, quality_analysis):
        raw_citations = list(analysis.get("citations", []))
        for field in ("claims", "risks", "recommendations"):
            for item in analysis.get(field, []):
                raw_citations.extend(item.get("citations", []))
        for raw in raw_citations:
            citation = Citation.model_validate(raw)
            citations.setdefault(citation.citation_id, citation)
    return list(citations.values())


def _build_summary(
    rd_analysis: dict[str, Any],
    quality_analysis: dict[str, Any],
    review_result: dict[str, Any],
) -> str:
    review_status = "审核通过" if review_result.get("passed") else "存在待修复项"
    return "；".join(
        value
        for value in (
            str(rd_analysis.get("summary") or "").strip(),
            str(quality_analysis.get("summary") or "").strip(),
            review_status,
        )
        if value
    )


def _safe_customer_request(
    user_request: str,
    review_result: dict[str, Any],
) -> str:
    has_overcommitment = any(
        "过度承诺风险" in str(item)
        for item in review_result.get("conflicts", [])
    )
    if not has_overcommitment:
        return user_request.strip()
    return (
        "客户提出绝对质量承诺诉求。该诉求需由质量部门、合同责任人和"
        "授权审批人确认，当前售前方案不作零缺陷或绝对结果保证。"
    )


def _bullets(values: list[str]) -> str:
    normalized = list(dict.fromkeys(value.strip() for value in values if value.strip()))
    return "\n".join(f"- {value}" for value in normalized) or "- 暂无"

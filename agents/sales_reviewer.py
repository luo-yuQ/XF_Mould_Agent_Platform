"""销售协作 Reviewer：确定性规则检查与可选 LLM 增强。"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.sales_specialist_common import get_sales_specialist_llm
from agents.structured_llm import invoke_structured_json
from schemas.sales_collaboration import ReviewerOutput


RD_QUALITY_BOUNDARY_TERMS = (
    "公司质量体系",
    "质量体系完善",
    "通过vda",
    "通过 vda",
    "通过iso",
    "通过 iso",
    "认证资质",
    "公司审核能力",
    "公司质量保证能力",
)
QUALITY_TECHNICAL_BOUNDARY_TERMS = (
    "模具结构采用",
    "材料选择为",
    "成型参数设定",
    "冲压间隙设定",
    "拉延筋设计",
    "工艺参数确定",
)
OVERCOMMITMENT_TERMS = (
    "一定可以保证",
    "保证零缺陷",
    "零缺陷量产",
    "绝对保证",
    "100%保证",
    "百分之百保证",
)

REVIEWER_PROMPT = """你是销售协作 Reviewer。
只能基于输入识别冲突、无依据声明、缺失章节和人工确认项。
不得补充业务事实。输出必须符合 ReviewerOutput。

你必须只返回合法的 JSON 对象，不要输出 Markdown 或 ```json 代码块。
整个响应必须是一个符合 ReviewerOutput schema 的 JSON 对象。
JSON 必须是全部响应内容。
"""


def run_sales_reviewer(
    *,
    user_request: str,
    execution_plan: list[dict[str, Any]],
    rd_analysis: dict[str, Any],
    quality_analysis: dict[str, Any],
    llm: Any = None,
    use_llm: bool = False,
) -> ReviewerOutput:
    """先执行强制规则，再按需合并 LLM 审核结果。"""
    result = _rule_review(
        user_request=user_request,
        rd_analysis=rd_analysis,
        quality_analysis=quality_analysis,
    )
    if not use_llm:
        return result

    model = llm or get_sales_specialist_llm()
    prompt = json.dumps(
        {
            "user_request": user_request,
            "execution_plan": execution_plan,
            "rd_analysis": rd_analysis,
            "quality_analysis": quality_analysis,
            "rule_result": result.model_dump(),
        },
        ensure_ascii=False,
    )
    try:
        messages = [
            SystemMessage(content=REVIEWER_PROMPT),
            HumanMessage(content=prompt),
        ]
        try:
            raw = invoke_structured_json(model, ReviewerOutput, messages)
            llm_result = ReviewerOutput.model_validate(raw)
        except Exception:
            # 回退：原始 LLM 调用 + JSON 提取
            response = model.invoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            cleaned = re.sub(r"^```(?:json)?\s*", "", str(content).strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            raw_str = match.group(1) if match else cleaned
            try:
                data = json.loads(raw_str)
            except json.JSONDecodeError:
                data = ast.literal_eval(raw_str)
            llm_result = ReviewerOutput.model_validate(data)
    except Exception:
        return result
    return _merge_review_results(result, llm_result)


def _rule_review(
    *,
    user_request: str,
    rd_analysis: dict[str, Any],
    quality_analysis: dict[str, Any],
) -> ReviewerOutput:
    conflicts: list[str] = []
    unsupported: list[str] = []
    missing_sections: list[str] = []
    manual_checks: list[str] = []
    repairs: list[str] = []

    overcommitment_terms = [
        term for term in OVERCOMMITMENT_TERMS if term.lower() in user_request.lower()
    ]
    if overcommitment_terms:
        conflicts.append(
            "客户请求包含过度承诺风险：" + ", ".join(overcommitment_terms)
        )
        manual_checks.append("质量承诺需由质量部门、合同责任人和授权审批人确认。")
        repairs.append("将绝对质量承诺改写为验证目标、控制措施和待审批事项。")

    if not _has_section_content(rd_analysis):
        missing_sections.append("技术与工艺风险")
        repairs.append("补充 R&D Specialist 分析。")
    if not _has_section_content(quality_analysis):
        missing_sections.append("质量保障分析")
        repairs.append("补充 Quality Specialist 分析。")

    _check_role_boundary(
        analysis=rd_analysis,
        terms=RD_QUALITY_BOUNDARY_TERMS,
        label="R&D 越权声明公司质量能力",
        conflicts=conflicts,
    )
    _check_role_boundary(
        analysis=quality_analysis,
        terms=QUALITY_TECHNICAL_BOUNDARY_TERMS,
        label="Quality 越权编造技术工艺方案",
        conflicts=conflicts,
    )

    for role, analysis in (("R&D", rd_analysis), ("Quality", quality_analysis)):
        for field, text_field in (
            ("claims", "text"),
            ("risks", "description"),
            ("recommendations", "text"),
        ):
            for item in analysis.get(field, []) if analysis else []:
                text = str(item.get(text_field) or "").strip()
                if text and not item.get("citations"):
                    unsupported.append(
                        f"{role} {field}: {item.get('claim_id') or item.get('risk_id') or item.get('recommendation_id') or text}"
                    )
                if item.get("requires_manual_check") and text:
                    manual_checks.append(text)
        for item in analysis.get("missing_information", []) if analysis else []:
            question = str(item.get("question") or "").strip()
            if question:
                manual_checks.append(question)

    if unsupported:
        repairs.append("为无引用的强结论补充依据，或将其明确标记为待确认建议。")
    if conflicts:
        repairs.append("移除角色越权声明，并由对应专业角色重新确认。")

    conflicts = _dedupe(conflicts)
    unsupported = _dedupe(unsupported)
    missing_sections = _dedupe(missing_sections)
    manual_checks = _dedupe(manual_checks)
    repairs = _dedupe(repairs)
    return ReviewerOutput(
        passed=not conflicts and not unsupported and not missing_sections,
        conflicts=conflicts,
        unsupported_claims=unsupported,
        missing_sections=missing_sections,
        manual_check_items=manual_checks,
        repair_instructions=repairs,
    )


def _analysis_text(analysis: dict[str, Any]) -> str:
    values = [str(analysis.get("summary") or "")]
    for field, text_field in (
        ("claims", "text"),
        ("risks", "description"),
        ("recommendations", "text"),
    ):
        values.extend(
            str(item.get(text_field) or "") for item in analysis.get(field, [])
        )
    return "\n".join(values).lower()


def _has_section_content(analysis: dict[str, Any]) -> bool:
    return bool(
        analysis
        and (
            str(analysis.get("summary") or "").strip()
            or analysis.get("claims")
            or analysis.get("risks")
            or analysis.get("recommendations")
        )
    )


def _check_role_boundary(
    *,
    analysis: dict[str, Any],
    terms: tuple[str, ...],
    label: str,
    conflicts: list[str],
) -> None:
    text = _analysis_text(analysis)
    matched = [term for term in terms if term.lower() in text]
    if matched:
        conflicts.append(f"{label}: {', '.join(matched)}")


def _merge_review_results(
    rules: ReviewerOutput,
    llm_result: ReviewerOutput,
) -> ReviewerOutput:
    conflicts = _dedupe([*rules.conflicts, *llm_result.conflicts])
    unsupported = _dedupe(
        [*rules.unsupported_claims, *llm_result.unsupported_claims]
    )
    missing = _dedupe([*rules.missing_sections, *llm_result.missing_sections])
    return ReviewerOutput(
        passed=not conflicts and not unsupported and not missing and llm_result.passed,
        conflicts=conflicts,
        unsupported_claims=unsupported,
        missing_sections=missing,
        manual_check_items=_dedupe(
            [*rules.manual_check_items, *llm_result.manual_check_items]
        ),
        repair_instructions=_dedupe(
            [*rules.repair_instructions, *llm_result.repair_instructions]
        ),
    )


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))

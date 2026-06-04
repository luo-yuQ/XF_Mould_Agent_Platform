"""
审核检查输出校验器。

只负责检查 audit findings 是否满足 MVP 规则，并生成一次性修复提示。
不在这里做循环修复，也不接入现有 RAG / 前端 / Memory 流程。
"""
from __future__ import annotations

import re
from typing import Any


REQUIRED_FINDING_FIELDS = (
    "issue",
    "category",
    "risk_level",
    "risk_explanation",
    "evidence_from_input",
    "basis",
    "recommendation",
    "manual_check_required",
)

VALID_RISK_LEVELS = {"低", "中", "高", "需人工确认"}

EMPTY_RECOMMENDATIONS = (
    "加强管理",
    "提高意识",
    "加强培训",
    "完善流程",
    "持续改进",
    "加强管控",
)

STANDARD_CLAIM_PATTERN = re.compile(
    r"(?:根据|依据|参照)?第\s*([A-Za-z0-9一二三四五六七八九十百千万点.\-_/]+)\s*(?:条|章|节|款|项|页)"
    r"|(?:某标准明确要求|标准明确要求)"
)


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {}


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _get_findings(payload: dict[str, Any]) -> list[Any]:
    findings = payload.get("findings")
    if findings is None and isinstance(payload.get("output"), dict):
        findings = payload["output"].get("findings")
    return findings if isinstance(findings, list) else []


def _docs_text(retrieved_docs: list[dict[str, Any]] | None) -> str:
    if not retrieved_docs:
        return ""

    parts: list[str] = []
    for doc in retrieved_docs:
        if not isinstance(doc, dict):
            continue
        for field in (
            "text",
            "content",
            "doc_source",
            "source",
            "doc_chapter",
            "chapter",
            "doc_section",
            "section_title",
            "heading_path",
        ):
            text = _as_text(doc.get(field))
            if text:
                parts.append(text)
    return " ".join(parts)


def _row_label(finding: dict[str, Any], index: int) -> str:
    issue = _as_text(finding.get("issue"))
    if issue:
        return f"第 {index} 条 finding（{issue[:30]}）"
    return f"第 {index} 条 finding"


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[A-Za-z0-9]+", text.lower()))
    tokens.update(re.findall(r"[\u4e00-\u9fff]{2,}", text))
    return tokens


def _recommendation_is_specific(issue: str, recommendation: str) -> bool:
    if not recommendation:
        return False

    compact = re.sub(r"\s+", "", recommendation)
    if compact in EMPTY_RECOMMENDATIONS:
        return False

    if len(compact) <= 8 and any(word in compact for word in EMPTY_RECOMMENDATIONS):
        return False

    action_words = (
        "补充",
        "明确",
        "验证",
        "记录",
        "闭环",
        "责任人",
        "期限",
        "原因",
        "措施",
        "控制",
        "探测",
        "预防",
        "纠正",
        "整改",
        "证据",
        "更新",
        "确认",
    )
    if any(word in recommendation for word in action_words):
        return True

    issue_tokens = _tokenize(issue)
    rec_tokens = _tokenize(recommendation)
    return bool(issue_tokens and rec_tokens and issue_tokens & rec_tokens)


def _unsupported_standard_claims(finding_text: str, docs_text: str) -> list[str]:
    claims: list[str] = []
    for match in STANDARD_CLAIM_PATTERN.finditer(finding_text):
        claim = match.group(0)
        key = next((group for group in match.groups() if group), "")
        if not docs_text or (claim not in docs_text and (not key or key not in docs_text)):
            claims.append(claim)
    return claims


def _finding_text(finding: dict[str, Any]) -> str:
    return " ".join(_as_text(value) for value in finding.values())


def _build_repair_instruction(issues: list[str]) -> str:
    if not issues:
        return ""
    return (
        "请只修复审核检查 JSON findings，不要输出 Markdown。"
        "保留已经合理的 finding 内容；补齐缺失字段；"
        "risk_level 只能是 低/中/高/需人工确认；"
        "basis 不能为空，没有充分检索依据时必须写“需人工确认”；"
        "删除无法被 retrieved_docs 支持的“根据第X条/第X章/某标准明确要求”等标准条款表述；"
        "recommendation 必须针对具体 issue，不能只写“加强管理”“提高意识”“加强培训”等空话；"
        "输入依据不足、basis 为需人工确认或风险无法判断时 manual_check_required 必须为 true。"
    )


def verify_audit_output(
    audit_output: Any,
    retrieved_docs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    校验审核检查输出。

    返回：
    {
      "passed": true/false,
      "issues": [...],
      "repair_instruction": "..."
    }
    """
    payload = _to_dict(audit_output)
    if not payload and isinstance(audit_output, list):
        payload = {"findings": audit_output}

    findings = _get_findings(payload)
    docs_text = _docs_text(retrieved_docs)
    issues: list[str] = []

    if not findings:
        issues.append("findings 不能为空，至少需要 1 条审核发现。")

    for index, raw_finding in enumerate(findings, 1):
        finding = _to_dict(raw_finding)
        label = _row_label(finding, index)

        if not finding:
            issues.append(f"{label} 不是有效对象。")
            continue

        for field in REQUIRED_FINDING_FIELDS:
            if field not in finding:
                issues.append(f"{label} 缺少必填字段：{field}。")
            elif field != "manual_check_required" and not _as_text(finding.get(field)):
                issues.append(f"{label} 字段为空：{field}。")

        basis = _as_text(finding.get("basis"))
        if not basis:
            issues.append(f"{label} basis 不能为空；没有依据时必须写“需人工确认”。")

        risk_level = _as_text(finding.get("risk_level"))
        if risk_level and risk_level not in VALID_RISK_LEVELS:
            issues.append(f"{label} risk_level 必须是 低/中/高/需人工确认。")

        evidence = _as_text(finding.get("evidence_from_input"))
        manual_check_required = finding.get("manual_check_required")
        evidence_insufficient = (
            not evidence
            or "输入依据不足" in evidence
            or "依据不足" in evidence
            or "需人工确认" in evidence
        )
        if evidence_insufficient and manual_check_required is not True:
            issues.append(f"{label} 输入依据不充分时 manual_check_required 必须为 true。")

        if basis == "需人工确认" and manual_check_required is not True:
            issues.append(f"{label} basis 为“需人工确认”时 manual_check_required 必须为 true。")

        issue_text = _as_text(finding.get("issue"))
        recommendation = _as_text(finding.get("recommendation"))
        if not _recommendation_is_specific(issue_text, recommendation):
            issues.append(f"{label} recommendation 未明显针对具体 issue，或只是空泛建议。")

        unsupported_claims = _unsupported_standard_claims(_finding_text(finding), docs_text)
        for claim in unsupported_claims:
            issues.append(f"{label} 出现无法由 retrieved_docs 支持的标准依据表述：{claim}。")

    return {
        "passed": not issues,
        "issues": issues,
        "repair_instruction": _build_repair_instruction(issues),
    }

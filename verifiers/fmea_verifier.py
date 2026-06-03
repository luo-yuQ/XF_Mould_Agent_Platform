"""
FMEA 输出校验器。

只负责检查 FMEA rows 是否满足 MVP 规则，并生成一次性修复提示。
不在这里做循环修复，也不接入现有 RAG / 前端 / Memory 流程。
"""
from __future__ import annotations

import re
from typing import Any


REQUIRED_ROW_FIELDS = (
    "function",
    "failure_mode",
    "effect",
    "cause",
    "prevention_control",
    "detection_control",
    "recommended_action",
    "evidence",
)

SUGGESTION_WORDS = ("建议", "需人工确认", "人工确认", "仅供参考", "suggested")
STANDARD_CLAIM_PATTERN = re.compile(
    r"(?:根据|依据|参照)?第\s*([A-Za-z0-9一二三四五六七八九十百千万点\.\-_/]+)\s*(?:条|章|节|款|项)?标准"
)


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return {}


def _get_rows(payload: dict[str, Any]) -> list[Any]:
    rows = payload.get("rows")
    if rows is None and isinstance(payload.get("output"), dict):
        rows = payload["output"].get("rows")
    if isinstance(rows, list):
        return rows
    return []


def _get_retrieved_docs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    docs = (
        payload.get("retrieved_docs")
        or payload.get("rag_chunks")
        or payload.get("docs")
        or payload.get("references")
        or []
    )
    return docs if isinstance(docs, list) else []


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _get_field(row: dict[str, Any], field: str) -> Any:
    aliases = {
        "effect": ("effect", "failure_effect"),
        "cause": ("cause", "potential_cause"),
    }
    for name in aliases.get(field, (field,)):
        if name in row:
            return row.get(name)
    return None


def _row_label(row: dict[str, Any], index: int) -> str:
    row_id = row.get("id") or index
    return f"第 {row_id} 行"


def _score_has_suggestion(score: Any) -> bool:
    score_dict = _to_dict(score)
    if score_dict.get("suggested") is True:
        return True
    text = " ".join(_as_text(v) for v in score_dict.values())
    if not text:
        text = _as_text(score)
    return any(word in text for word in SUGGESTION_WORDS)


def _row_text(row: dict[str, Any]) -> str:
    parts: list[str] = []
    for value in row.values():
        if isinstance(value, dict):
            parts.append(_row_text(value))
        elif isinstance(value, list):
            parts.append(" ".join(_as_text(item) for item in value))
        else:
            parts.append(_as_text(value))
    return " ".join(part for part in parts if part)


def _docs_text(retrieved_docs: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for doc in retrieved_docs:
        if not isinstance(doc, dict):
            continue
        parts.extend(
            _as_text(doc.get(field))
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
            )
        )
    return " ".join(part for part in parts if part)


def _action_matches_context(row: dict[str, Any]) -> bool:
    action = _as_text(row.get("recommended_action"))
    if not action:
        return False

    context = " ".join(
        _as_text(_get_field(row, field))
        for field in ("cause", "prevention_control", "detection_control")
    )
    if not context:
        return False

    action_tokens = _tokenize_cn(action)
    context_tokens = _tokenize_cn(context)
    if not action_tokens or not context_tokens:
        return False

    overlap = action_tokens & context_tokens
    control_words = {
        "优化",
        "调整",
        "增加",
        "加强",
        "检查",
        "检测",
        "点检",
        "控制",
        "预防",
        "探测",
        "校验",
        "维护",
        "清洁",
        "培训",
        "更换",
        "改善",
    }
    return bool(overlap) or any(word in action for word in control_words)


def _tokenize_cn(text: str) -> set[str]:
    tokens = set(re.findall(r"[A-Za-z0-9]+", text.lower()))
    tokens.update(re.findall(r"[\u4e00-\u9fff]{2,}", text))
    return tokens


def _standard_claims_without_docs(row: dict[str, Any], docs_text: str) -> list[str]:
    claims: list[str] = []
    for match in STANDARD_CLAIM_PATTERN.finditer(_row_text(row)):
        claim = match.group(0)
        key = match.group(1)
        if not docs_text or (claim not in docs_text and key not in docs_text):
            claims.append(claim)
    return claims


def _build_repair_instruction(issues: list[str]) -> str:
    if not issues:
        return ""
    return (
        "请只修复 FMEA JSON rows，不要输出 Markdown。"
        "保留用户输入和已有合理内容；补齐缺失字段；确保 rows 非空；"
        "S/O/D/AP 必须标记为建议值或写明需人工确认；"
        "evidence 不能为空，无检索依据时写“需人工确认：基于通用知识，未查到手册原文”；"
        "recommended_action 必须针对 failure cause、预防控制不足或探测控制不足；"
        "删除无法由 retrieved_docs 支撑的“根据第X条标准”等标准条款表述。"
    )


def verify_fmea_output(fmea_output: Any) -> dict[str, Any]:
    """
    校验 FMEA 输出。

    返回：
    {
      "passed": true/false,
      "issues": [...],
      "repair_instruction": "..."
    }
    """
    payload = _to_dict(fmea_output)
    if not payload and isinstance(fmea_output, list):
        payload = {"rows": fmea_output}

    rows = _get_rows(payload)
    retrieved_docs = _get_retrieved_docs(payload)
    docs_text = _docs_text(retrieved_docs)
    issues: list[str] = []

    if not rows:
        issues.append("rows 为空，至少需要 1 行 FMEA 记录。")

    for index, raw_row in enumerate(rows, 1):
        row = _to_dict(raw_row)
        label = _row_label(row, index)
        if not row:
            issues.append(f"{label} 不是有效对象。")
            continue

        for field in REQUIRED_ROW_FIELDS:
            if not _as_text(_get_field(row, field)):
                issues.append(f"{label} 缺少必填字段或字段为空：{field}。")

        for score_field in ("severity", "occurrence", "detection"):
            if score_field not in row:
                issues.append(f"{label} 缺少评分字段：{score_field}。")
                continue
            if not _score_has_suggestion(row.get(score_field)):
                issues.append(f"{label} 的 {score_field} 未体现建议值或需人工确认语义。")

        ap_score = row.get("action_priority") if "action_priority" in row else row.get("ap")
        if ap_score is None:
            issues.append(f"{label} 缺少评分字段：AP。")
        elif not _score_has_suggestion(ap_score):
            issues.append(f"{label} 的 AP 未体现建议值或需人工确认语义。")

        evidence = _as_text(_get_field(row, "evidence"))
        if not evidence:
            issues.append(f"{label} evidence 为空。")
        elif not retrieved_docs and "需人工确认" not in evidence:
            issues.append(f"{label} 无 retrieved_docs 依据时，evidence 必须包含“需人工确认”。")

        if not _action_matches_context(row):
            issues.append(f"{label} recommended_action 未明显对应 cause 或现行控制不足。")

        unsupported_claims = _standard_claims_without_docs(row, docs_text)
        for claim in unsupported_claims:
            issues.append(f"{label} 出现无法由 retrieved_docs 支撑的标准依据表述：{claim}。")

    return {
        "passed": not issues,
        "issues": issues,
        "repair_instruction": _build_repair_instruction(issues),
    }

"""
Audit Check 检索查询规划器。

根据审核检查输入生成 3~5 条检索 query。
本模块不调用 LLM，不引入知识图谱，不修改或调用 Milvus 入库逻辑。
"""
from __future__ import annotations

from typing import Any


_PHENOMENON_EXPANSION: dict[str, list[str]] = {
    "飞边": ["飞边", "毛刺", "披锋", "溢料", "合模线溢料"],
    "短射": ["短射", "充填不足", "缺料", "欠注", "未充满"],
    "缩水": ["缩水", "缩痕", "凹痕", "缩水印", "表面凹陷"],
    "尺寸超差": ["尺寸超差", "尺寸偏差", "公差超限", "尺寸不合格", "尺寸异常"],
}


def _get_value(audit_input: Any, field: str) -> str:
    if isinstance(audit_input, dict):
        value = audit_input.get(field, "")
    else:
        value = getattr(audit_input, field, "")
    return str(value or "").strip()


def _extract_expansion_terms(content: str) -> list[str]:
    terms: list[str] = []
    for keyword, expansions in _PHENOMENON_EXPANSION.items():
        if keyword in content:
            terms.extend(expansions)
    return list(dict.fromkeys(terms))


def _append_context(parts: list[str], content: str, focus: str, background: str) -> list[str]:
    result = list(parts)
    if focus:
        result.append(focus)
    if background:
        result.append(background)
    expansion_terms = _extract_expansion_terms(content)
    if expansion_terms:
        result.append(" ".join(expansion_terms))
    return result


def _dedupe_and_limit(queries: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        normalized = " ".join(query.split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return unique[:5]


def build_audit_queries(audit_input: Any) -> list[str]:
    """
    根据 AuditInput 或等价 dict 生成 3~5 条检索 query。

    Args:
        audit_input: AuditInput 实例或 dict，包含 audit_type、content、focus、background。

    Returns:
        3~5 条去重后的检索 query。
    """
    audit_type = _get_value(audit_input, "audit_type") or "general"
    content = _get_value(audit_input, "content")
    focus = _get_value(audit_input, "focus")
    background = _get_value(audit_input, "background")

    queries: list[str] = []

    if audit_type == "quality_issue":
        queries.append(
            " ".join(
                _append_context(
                    ["VDA6.4 质量问题 原因分析 纠正措施 预防措施 整改闭环 记录验证"],
                    content,
                    focus,
                    background,
                )
            )
        )
        queries.append("VDA6.4 不合格品 纠正措施 预防措施 有效性验证 质量记录")
        queries.append(
            " ".join(
                _append_context(
                    ["FMEA 失效原因 预防控制 探测控制 风险分析"],
                    content,
                    focus,
                    background,
                )
            )
        )
        queries.append("FMEA 失效模式 潜在原因 现行控制 措施优化 S O D AP")

    elif audit_type == "pfmea":
        queries.append(
            " ".join(
                _append_context(
                    ["PFMEA 功能 要求 失效模式 失效后果 潜在原因"],
                    content,
                    focus,
                    background,
                )
            )
        )
        queries.append("PFMEA 预防控制 探测控制 S O D AP 行动优先级 措施优化")
        queries.append("FMEA 七步法 功能分析 失效分析 风险分析 措施优化")
        queries.append(
            " ".join(
                _append_context(
                    ["VDA6.4 过程控制 质量记录 整改闭环 有效性验证"],
                    content,
                    focus,
                    background,
                )
            )
        )

    elif audit_type == "audit_record":
        queries.append(
            " ".join(
                _append_context(
                    ["VDA6.4 审核 不符合项 审核发现 证据"],
                    content,
                    focus,
                    background,
                )
            )
        )
        queries.append("VDA6.4 审核 整改措施 责任人 完成期限 验证闭环")
        queries.append("质量管理体系 内部审核 不符合项 纠正措施 有效性验证")
        queries.append("审核记录 证据 责任部门 整改计划 验收证据")

    else:
        queries.append(
            " ".join(
                _append_context(
                    ["VDA6.4 质量管理体系 过程控制 审核发现 整改闭环"],
                    content,
                    focus,
                    background,
                )
            )
        )
        queries.append("质量问题 原因分析 纠正措施 预防措施 有效性验证")
        queries.append("FMEA 失效模式 潜在原因 预防控制 探测控制 风险分析")

    return _dedupe_and_limit(queries)

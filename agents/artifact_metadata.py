"""Rule-based metadata builders for FMEA, Audit, and Report artifacts."""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any


_MAX_TITLE_LENGTH = 200
_MAX_SUMMARY_LENGTH = 500
_MAX_KEYWORDS = 30
_MAX_KEYWORD_LENGTH = 80
_MAX_REFERENCE_SNIPPET = 240


def _as_data(value: Any) -> Any:
    if value is None:
        return {}
    if isinstance(value, (Mapping, list, tuple)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in {"{", "["}:
            try:
                return json.loads(text)
            except (TypeError, ValueError):
                return value
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except Exception:
            return {}
    if hasattr(value, "__dict__"):
        try:
            return {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        except Exception:
            return {}
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    data = _as_data(value)
    return data if isinstance(data, Mapping) else {}


def _text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _first(data: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(data.get(key))
        if value:
            return value
    return ""


def _items(value: Any, wrapper_keys: tuple[str, ...]) -> list[Mapping[str, Any]]:
    data = _as_data(value)
    if isinstance(data, Mapping):
        for key in wrapper_keys:
            nested = _as_data(data.get(key))
            if isinstance(nested, (list, tuple)):
                data = nested
                break
        else:
            data = [data]
    if not isinstance(data, (list, tuple)):
        return []
    return [_mapping(item) for item in data if _mapping(item)]


def _dedupe(values: Iterable[Any], limit: int = _MAX_KEYWORDS) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value).strip("，,；;。.!！?？:：|")
        if not text or text.lower() in {"none", "null", "n/a"}:
            continue
        text = text[:_MAX_KEYWORD_LENGTH]
        marker = text.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _join_summary(parts: Iterable[Any]) -> str:
    summary = "；".join(_dedupe(parts, limit=12))
    if len(summary) <= _MAX_SUMMARY_LENGTH:
        return summary
    return summary[: _MAX_SUMMARY_LENGTH - 1].rstrip("，,；;。 ") + "。"


def _title(parts: Iterable[Any], fallback: str) -> str:
    value = " - ".join(_dedupe(parts, limit=3)) or fallback
    return value[:_MAX_TITLE_LENGTH]


def _nested_score(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        raw = _as_data(row.get(key))
        if isinstance(raw, Mapping):
            value = _text(raw.get("value"))
        else:
            value = _text(raw)
        if value:
            return value
    return ""


def _manual_items(*sources: Any) -> list[str]:
    values: list[Any] = []
    for source in sources:
        data = _as_data(source)
        if isinstance(data, Mapping):
            for key in ("manual_check_items", "manual_checks", "需人工确认项"):
                raw = data.get(key)
                if isinstance(raw, (list, tuple, set)):
                    values.extend(raw)
                elif raw:
                    values.append(raw)
    return _dedupe(values)


def _markdown_excerpt(markdown: Any) -> str:
    text = _text(markdown)
    if not text:
        return ""
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\|[-:\s|]+\|", " ", text)
    text = re.sub(r"[*_>`~-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:_MAX_SUMMARY_LENGTH].rstrip("，,；;。 ")


def _reference_entries(retrieved_refs: Any) -> list[Any]:
    data = _as_data(retrieved_refs)
    if isinstance(data, Mapping):
        for key in ("references", "refs", "retrieved_refs", "documents", "docs", "items"):
            nested = _as_data(data.get(key))
            if isinstance(nested, (list, tuple)):
                return list(nested)
        reference_fields = {
            "source_type",
            "type",
            "source_id",
            "id",
            "chunk_uid",
            "source",
            "doc_source",
            "title",
            "text",
            "content",
        }
        if not reference_fields.intersection(str(key) for key in data):
            entries: list[dict[str, Any]] = []
            for citation_id, raw_ref in data.items():
                ref = _mapping(raw_ref)
                if ref:
                    entries.append({"id": citation_id, **ref})
            return entries
        return [data]
    if isinstance(data, (list, tuple)):
        return list(data)
    return []


def build_references_summary(retrieved_refs: Any) -> list[dict[str, Any]]:
    """Map raw retrieval references to a new, compact references list."""
    try:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for index, raw_ref in enumerate(_reference_entries(retrieved_refs), 1):
            ref = _mapping(raw_ref)
            if not ref:
                continue

            source_type = _first(ref, "source_type", "type") or "rag"
            source_id = _first(ref, "source_id", "id", "chunk_uid", "chunk_id", "pk")
            source = _first(ref, "source", "doc_source", "file_name", "filename", "document")
            chapter = _first(ref, "chapter", "doc_chapter")
            section = _first(ref, "section_title", "section", "doc_section", "heading")
            page = _first(ref, "page", "page_number", "page_no")
            title = _first(ref, "title", "name")
            content = _first(ref, "text", "content", "snippet", "excerpt")

            if not title:
                title = " / ".join(part for part in (source, chapter, section) if part)
            if not title:
                title = f"检索引用 {index}"

            marker = (source_type, source_id, source, chapter, section, page, content)
            if marker in seen:
                continue
            seen.add(marker)

            summary: dict[str, Any] = {
                "source_type": source_type,
                "title": title[:_MAX_TITLE_LENGTH],
            }
            optional_fields = (
                ("source_id", source_id),
                ("source", source),
                ("chapter", chapter),
                ("section_title", section),
                ("page", page),
                ("snippet", content[:_MAX_REFERENCE_SNIPPET]),
            )
            summary.update({key: value for key, value in optional_fields if value})
            result.append(summary)
        return result
    except Exception:
        return []


def build_fmea_metadata(
    input_data: Any,
    output_json: Any = None,
    output_markdown: Any = None,
    retrieved_refs: Any = None,
) -> dict[str, Any]:
    """Build safe run-level metadata for one FMEA business artifact."""
    default = {
        "title": "FMEA分析",
        "summary": "",
        "keywords_json": [],
        "artifact_type": "fmea_run",
        "references_json": [],
    }
    try:
        input_map = _mapping(input_data)
        output_map = _mapping(output_json)
        if not input_map:
            input_map = _mapping(output_map.get("input"))
        rows = _items(output_json, ("rows", "output", "items"))

        product = _first(input_map, "product", "product_name", "分析对象")
        process = _first(input_map, "process", "process_name", "工序")
        phenomenon = _first(
            input_map,
            "failure_phenomenon",
            "quality_issue",
            "problem",
            "质量问题",
        )

        failure_modes = _dedupe(
            _first(row, "failure_mode", "失效模式") for row in rows
        )
        effects = _dedupe(
            _first(row, "effect", "failure_effect", "失效后果") for row in rows
        )
        causes = _dedupe(
            _first(row, "cause", "potential_cause", "潜在原因") for row in rows
        )
        actions = _dedupe(
            _first(row, "recommended_action", "recommendation", "整改措施") for row in rows
        )
        risk_levels = _dedupe(
            value
            for row in rows
            for value in (
                _nested_score(row, "action_priority", "ap"),
                f"RPN {_first(row, 'rpn')}" if _first(row, "rpn") else "",
            )
        )
        manual_items = _manual_items(output_map, input_map)

        summary = _join_summary((
            f"产品：{product}" if product else "",
            f"工序：{process}" if process else "",
            f"质量问题：{phenomenon}" if phenomenon else "",
            f"失效模式：{'、'.join(failure_modes[:3])}" if failure_modes else "",
            f"失效后果：{'、'.join(effects[:2])}" if effects else "",
            f"潜在原因：{'、'.join(causes[:2])}" if causes else "",
            f"整改措施：{'、'.join(actions[:2])}" if actions else "",
            f"风险等级：{'、'.join(risk_levels[:3])}" if risk_levels else "",
            f"需人工确认：{'、'.join(manual_items[:2])}" if manual_items else "",
        ))
        if not summary:
            summary = _markdown_excerpt(output_markdown)

        return {
            "title": _title((product, process, failure_modes[0] if failure_modes else phenomenon), "FMEA分析"),
            "summary": summary,
            "keywords_json": _dedupe((
                product,
                process,
                phenomenon,
                *failure_modes,
                *effects,
                *causes,
                *actions,
                *risk_levels,
                *manual_items,
            )),
            "artifact_type": "fmea_run",
            "references_json": build_references_summary(retrieved_refs),
        }
    except Exception:
        return default


def build_audit_metadata(
    input_data: Any,
    findings_json: Any = None,
    final_markdown: Any = None,
    retrieved_refs: Any = None,
) -> dict[str, Any]:
    """Build safe run-level metadata for one Audit business artifact."""
    default = {
        "title": "审核检查",
        "summary": "",
        "keywords_json": [],
        "artifact_type": "audit_run",
        "references_json": [],
    }
    try:
        input_map = _mapping(input_data)
        findings_map = _mapping(findings_json)
        if not input_map:
            input_map = _mapping(findings_map.get("input"))
        findings = _items(findings_json, ("findings", "items", "output"))

        audit_type = _first(input_map, "audit_type", "type", "审核类型")
        focus = _first(input_map, "focus", "audit_focus", "审核重点")
        product = _first(input_map, "product", "product_name", "产品")
        process = _first(input_map, "process", "process_name", "工序")
        quality_issue = _first(input_map, "quality_issue", "problem", "质量问题")
        issues = _dedupe(_first(item, "issue", "problem", "审核发现") for item in findings)
        categories = _dedupe(_first(item, "category", "issue_type", "问题类型") for item in findings)
        risks = _dedupe(_first(item, "risk_level", "risk", "风险等级") for item in findings)
        actions = _dedupe(
            _first(item, "recommendation", "recommended_action", "整改措施")
            for item in findings
        )
        manual_items = _manual_items(findings_map, input_map)
        manual_items.extend(
            _first(item, "issue", "problem", "审核发现")
            for item in findings
            if item.get("manual_check_required") is True
        )
        manual_items = _dedupe(manual_items)

        summary = _join_summary((
            f"审核类型：{audit_type}" if audit_type else "",
            f"审核重点：{focus}" if focus else "",
            f"产品：{product}" if product else "",
            f"工序：{process}" if process else "",
            f"质量问题：{quality_issue}" if quality_issue else "",
            f"审核发现：{'、'.join(issues[:3])}" if issues else "",
            f"风险等级：{'、'.join(risks[:3])}" if risks else "",
            f"整改措施：{'、'.join(actions[:2])}" if actions else "",
            f"需人工确认：{'、'.join(manual_items[:2])}" if manual_items else "",
        ))
        if not summary:
            summary = _markdown_excerpt(final_markdown)

        return {
            "title": _title((audit_type, issues[0] if issues else focus), "审核检查"),
            "summary": summary,
            "keywords_json": _dedupe((
                product,
                process,
                quality_issue,
                audit_type,
                focus,
                *issues,
                *categories,
                *risks,
                *actions,
                *manual_items,
            )),
            "artifact_type": "audit_run",
            "references_json": build_references_summary(retrieved_refs),
        }
    except Exception:
        return default


def build_report_metadata(
    report_input: Any = None,
    final_markdown: Any = None,
    source_snapshot: Any = None,
) -> dict[str, Any]:
    """Build safe run-level metadata for one Report business artifact."""
    default = {
        "summary": "",
        "keywords_json": [],
        "artifact_type": "report_run",
    }
    try:
        report_map = _mapping(report_input)
        snapshot = _mapping(source_snapshot)
        if not report_map:
            report_map = _mapping(snapshot.get("report_input"))

        title = _first(report_map, "title", "report_title") or "质量问题分析报告"
        background = _first(report_map, "extra_background", "background", "quality_issue")
        manual_items = _manual_items(report_map, snapshot)

        fmea_source = _mapping(snapshot.get("fmea_source"))
        audit_source = _mapping(snapshot.get("audit_source"))
        product = _first(fmea_source, "product")
        process = _first(fmea_source, "process")
        phenomenon = _first(fmea_source, "failure_phenomenon", "quality_issue")
        findings = _items(audit_source.get("findings_json"), ("findings", "items"))
        issues = _dedupe(_first(item, "issue", "problem") for item in findings)
        risks = _dedupe(_first(item, "risk_level", "risk") for item in findings)

        source_labels = _dedupe((
            "FMEA" if fmea_source.get("status") == "found" else "",
            "Audit" if audit_source.get("status") == "found" else "",
            "RAG参考" if snapshot.get("optional_rag_refs") else "",
            "用户补充背景" if background else "",
        ))
        summary = _join_summary((
            f"报告：{title}",
            f"质量问题：{phenomenon}" if phenomenon else "",
            f"产品：{product}" if product else "",
            f"工序：{process}" if process else "",
            f"审核发现：{'、'.join(issues[:3])}" if issues else "",
            f"风险等级：{'、'.join(risks[:3])}" if risks else "",
            f"来源：{'、'.join(source_labels)}" if source_labels else "",
            f"需人工确认：{'、'.join(manual_items[:2])}" if manual_items else "",
        ))
        if summary == f"报告：{title}" and final_markdown:
            excerpt = _markdown_excerpt(final_markdown)
            summary = _join_summary((f"报告：{title}", excerpt))

        return {
            "summary": summary,
            "keywords_json": _dedupe((
                title,
                product,
                process,
                phenomenon,
                *issues,
                *risks,
                *manual_items,
            )),
            "artifact_type": "report_run",
        }
    except Exception:
        return default

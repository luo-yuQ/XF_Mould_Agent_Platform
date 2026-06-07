"""Rule-based consistency check for user-selected Report sources."""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Literal


MatchStatus = Literal["yes", "no", "uncertain"]

_QUALITY_TERMS = (
    "飞边",
    "毛刺",
    "短射",
    "缩水",
    "尺寸超差",
    "装配干涉",
    "锁模力不足",
    "开裂",
    "变形",
    "错位",
    "缺料",
    "气孔",
    "烧焦",
    "色差",
    "表面缺陷",
    "整改闭环",
    "责任人缺失",
    "检验记录不完整",
)

_STOP_WORDS = {
    "fmea",
    "pfmea",
    "audit",
    "质量",
    "质量问题",
    "分析",
    "报告",
    "审核",
    "审核检查",
    "审核发现",
    "问题",
    "风险",
    "整改",
    "整改措施",
    "需人工确认",
    "人工确认",
    "质量问题分析报告",
}

_FIELD_KEYS = (
    "product",
    "product_name",
    "process",
    "process_name",
    "failure_phenomenon",
    "quality_issue",
    "focus",
)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "model_dump"):
        try:
            data = value.model_dump()
            return data if isinstance(data, Mapping) else {}
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
    return {}


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text[:1] not in {"[", "{"}:
        return value
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return value


def _text(value: Any) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _normalize(value: Any) -> str:
    text = _text(value).casefold()
    return re.sub(r"[\s\-_/\\|,，。；;：:、（）()\[\]【】]+", "", text)


def _add_keyword(target: dict[str, int], value: Any, weight: int) -> None:
    text = _text(value).strip("，,；;。.!！?？:：|")
    normalized = _normalize(text)
    if not normalized or normalized in _STOP_WORDS or len(normalized) < 2:
        return
    if len(text) > 40:
        return
    current = target.get(text, 0)
    if weight > current:
        target[text] = weight


def _add_split_keywords(target: dict[str, int], value: Any, weight: int) -> None:
    text = _text(value)
    if not text:
        return
    for part in re.split(r"[\n\r|,，。；;：:、/\\]+|\s+-\s+", text):
        cleaned = re.sub(
            r"^(?:产品|工序|过程|问题现象|质量问题|失效模式|审核重点|首条问题|风险等级)\s*",
            "",
            part.strip(),
        )
        _add_keyword(target, cleaned, weight)


def _add_known_terms(target: dict[str, int], value: Any, weight: int) -> None:
    text = _text(value)
    for term in _QUALITY_TERMS:
        if term in text:
            _add_keyword(target, term, weight)


def _list_items(value: Any, wrapper: str) -> list[Mapping[str, Any]]:
    data = _json_value(value)
    if isinstance(data, Mapping):
        data = data.get(wrapper, [])
    if not isinstance(data, (list, tuple)):
        return []
    return [_as_mapping(item) for item in data if _as_mapping(item)]


def _source_keywords(source: Any, source_type: str) -> tuple[list[str], dict[str, int]]:
    data = _as_mapping(source)
    weighted: dict[str, int] = {}

    raw_keywords = _json_value(data.get("keywords_json"))
    if isinstance(raw_keywords, (list, tuple, set)):
        for keyword in raw_keywords:
            _add_keyword(weighted, keyword, 30)

    for key in _FIELD_KEYS:
        _add_keyword(weighted, data.get(key), 25)

    input_json = _as_mapping(_json_value(data.get("input_json")))
    for key in _FIELD_KEYS:
        _add_keyword(weighted, input_json.get(key), 25)

    _add_split_keywords(weighted, data.get("title"), 18)
    _add_split_keywords(weighted, data.get("summary"), 15)

    if source_type == "fmea":
        rows = _list_items(data.get("output_json"), "rows")
        for row in rows[:10]:
            for key in ("failure_mode", "effect", "failure_effect", "cause", "potential_cause"):
                _add_keyword(weighted, row.get(key), 20)
                _add_known_terms(weighted, row.get(key), 20)
        _add_known_terms(weighted, data.get("output_markdown"), 12)
    else:
        findings = _list_items(data.get("findings_json"), "findings")
        for finding in findings[:10]:
            for key in ("issue", "category", "risk_explanation", "recommendation"):
                _add_keyword(weighted, finding.get(key), 20)
                _add_known_terms(weighted, finding.get(key), 20)
        _add_known_terms(weighted, data.get("content_text"), 12)
        _add_known_terms(weighted, data.get("final_markdown"), 12)

    ordered = sorted(weighted, key=lambda item: (-weighted[item], item.casefold()))
    return ordered[:30], weighted


def _common_keywords(
    fmea_keywords: list[str],
    audit_keywords: list[str],
) -> list[str]:
    common: list[str] = []
    seen: set[str] = set()
    for fmea_keyword in fmea_keywords:
        fmea_normalized = _normalize(fmea_keyword)
        for audit_keyword in audit_keywords:
            audit_normalized = _normalize(audit_keyword)
            if not fmea_normalized or not audit_normalized:
                continue
            same = fmea_normalized == audit_normalized
            contained = (
                min(len(fmea_normalized), len(audit_normalized)) >= 3
                and (
                    fmea_normalized in audit_normalized
                    or audit_normalized in fmea_normalized
                )
            )
            if not same and not contained:
                continue
            value = (
                fmea_keyword
                if len(fmea_normalized) <= len(audit_normalized)
                else audit_keyword
            )
            marker = _normalize(value)
            if marker not in seen:
                seen.add(marker)
                common.append(value)
            break
    return common[:20]


def _is_missing(source: Any) -> bool:
    data = _as_mapping(source)
    if not data:
        return True
    status = _text(data.get("status"))
    return bool(status and status != "found")


def check_report_source_match(
    fmea_run: Any = None,
    audit_run: Any = None,
    extra_background: Any = None,
) -> dict[str, Any]:
    """Compare selected FMEA and Audit sources using explainable rules only."""
    default = {
        "matched": "uncertain",
        "score": 0,
        "common_keywords": [],
        "fmea_keywords": [],
        "audit_keywords": [],
        "mismatch_reasons": [],
        "manual_check_required": True,
        "warning_message": "来源匹配检查未能完成，需人工确认所选 FMEA 与 Audit 是否属于同一质量问题。",
    }
    try:
        fmea_missing = _is_missing(fmea_run)
        audit_missing = _is_missing(audit_run)
        if fmea_missing or audit_missing:
            missing_labels = []
            if fmea_missing:
                missing_labels.append("FMEA")
            if audit_missing:
                missing_labels.append("Audit")
            missing_text = "、".join(missing_labels)
            return {
                **default,
                "mismatch_reasons": [f"缺少可用的 {missing_text} 来源。"],
                "warning_message": (
                    f"来源匹配提示：缺少可用的 {missing_text} 来源，"
                    "无法判断所选来源是否属于同一质量问题，需人工确认。"
                ),
            }

        fmea_keywords, fmea_weights = _source_keywords(fmea_run, "fmea")
        audit_keywords, audit_weights = _source_keywords(audit_run, "audit")
        common = _common_keywords(fmea_keywords, audit_keywords)
        reasons: list[str] = []

        if not common:
            return {
                "matched": "no",
                "score": 0,
                "common_keywords": [],
                "fmea_keywords": fmea_keywords,
                "audit_keywords": audit_keywords,
                "mismatch_reasons": ["未发现 FMEA 与 Audit 的明确共同业务关键词。"],
                "manual_check_required": True,
                "warning_message": (
                    "来源匹配提示：所选 FMEA 与 Audit 未发现明确共同业务关键词，"
                    "可能不属于同一质量问题，需人工确认。"
                ),
            }

        common_count = len(common)
        if common_count == 1:
            score = 45
        elif common_count == 2:
            score = 65
        elif common_count == 3:
            score = 80
        else:
            score = 90

        if any(
            fmea_weights.get(keyword, 0) >= 30
            and audit_weights.get(keyword, 0) >= 30
            for keyword in common
        ):
            score += 5

        background_keywords: dict[str, int] = {}
        _add_split_keywords(background_keywords, extra_background, 10)
        _add_known_terms(background_keywords, extra_background, 10)
        background_normalized = {_normalize(keyword) for keyword in background_keywords}
        if background_normalized.intersection(_normalize(keyword) for keyword in common):
            score += 5

        score = min(score, 95)
        if score >= 60:
            matched: MatchStatus = "yes"
            manual_required = False
            warning = (
                "来源匹配提示：所选 FMEA 与 Audit 存在共同业务关键词，"
                "规则检查未发现明显冲突；仍应结合业务上下文复核。"
            )
        else:
            matched = "uncertain"
            manual_required = True
            reasons.append("共同关键词较少，仅凭规则无法可靠判断来源一致性。")
            warning = (
                "来源匹配提示：所选 FMEA 与 Audit 仅有少量共同业务关键词，"
                "是否属于同一质量问题仍需人工确认。"
            )

        return {
            "matched": matched,
            "score": score,
            "common_keywords": common,
            "fmea_keywords": fmea_keywords,
            "audit_keywords": audit_keywords,
            "mismatch_reasons": reasons,
            "manual_check_required": manual_required,
            "warning_message": warning,
        }
    except Exception:
        return default

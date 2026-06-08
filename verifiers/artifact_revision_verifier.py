"""业务产物追改结果校验器。"""
from __future__ import annotations

import json
import re
from typing import Any

from verifiers.fmea_verifier import verify_fmea_output


GENERIC_ACTIONS = (
    "加强管理",
    "提高意识",
    "加强检查",
    "加强培训",
    "严格控制",
)
FIELD_HINTS = {
    "recommended_action": ("建议", "措施", "整改", "改进", "action"),
    "severity": ("严重度", "severity", "s评分", "s 评分"),
    "occurrence": ("发生度", "occurrence", "o评分", "o 评分"),
    "detection": ("探测度", "detection", "d评分", "d 评分"),
    "action_priority": ("行动优先级", "ap"),
    "prevention_control": ("预防", "预防控制"),
    "detection_control": ("探测控制", "检测控制", "检验"),
    "evidence": ("依据", "引用", "标准", "evidence"),
}


def _rows(output_json: Any) -> list[dict[str, Any]]:
    if not isinstance(output_json, dict):
        return []
    rows = output_json.get("rows", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _normalized_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _changed_fields(
    old_output_json: dict[str, Any],
    new_output_json: dict[str, Any],
) -> set[str]:
    old_rows = {str(row.get("id", index)): row for index, row in enumerate(_rows(old_output_json), 1)}
    new_rows = {str(row.get("id", index)): row for index, row in enumerate(_rows(new_output_json), 1)}
    changed: set[str] = set()
    for row_id in old_rows.keys() | new_rows.keys():
        old_row = old_rows.get(row_id, {})
        new_row = new_rows.get(row_id, {})
        for field in old_row.keys() | new_row.keys():
            if _normalized_json(old_row.get(field)) != _normalized_json(new_row.get(field)):
                changed.add(field)
    return changed


def _instruction_is_addressed(instruction: str, changed_fields: set[str]) -> bool:
    if not changed_fields:
        return False
    normalized = instruction.lower().replace(" ", "")
    hinted_fields = {
        field
        for field, hints in FIELD_HINTS.items()
        if any(hint.lower().replace(" ", "") in normalized for hint in hints)
    }
    return not hinted_fields or bool(hinted_fields & changed_fields)


def _is_only_generic_action(action: Any) -> bool:
    normalized = re.sub(r"[\s，。；、,.!?！？;：:]+", "", str(action or ""))
    return normalized in {re.sub(r"\s+", "", item) for item in GENERIC_ACTIONS}


def _references_lost(old_references: Any, new_references: Any) -> bool:
    old_items = old_references if isinstance(old_references, list) else []
    new_items = new_references if isinstance(new_references, list) else []
    if not old_items:
        return False
    new_serialized = {_normalized_json(item) for item in new_items}
    return any(_normalized_json(item) not in new_serialized for item in old_items)


def verify_artifact_revision(
    *,
    artifact_type: str,
    old_output_json: dict[str, Any],
    new_output_json: dict[str, Any],
    old_references_json: list[Any] | None,
    new_references_json: list[Any] | None,
    revision_instruction: str,
    final_markdown: str,
) -> dict[str, Any]:
    """校验追改结果并生成一次性 repair 指令。"""
    issues: list[str] = []
    if not isinstance(new_output_json, dict) or not new_output_json:
        issues.append("new_output_json 为空或不是有效对象。")

    if artifact_type != "fmea":
        issues.append(f"{artifact_type} 追改尚未开放。")
    else:
        fmea_result = verify_fmea_output(
            {
                "rows": _rows(new_output_json),
                "retrieved_docs": new_references_json or [],
            }
        )
        issues.extend(fmea_result.get("issues", []))

        old_rows = _rows(old_output_json)
        new_rows = _rows(new_output_json)
        if len(new_rows) < len(old_rows):
            issues.append("FMEA 追改不得无故删除已有失效模式行。")

        changed_fields = _changed_fields(old_output_json, new_output_json)
        if not _instruction_is_addressed(revision_instruction, changed_fields):
            issues.append("revision_instruction 未在结构化结果中得到可识别响应。")

        for index, row in enumerate(new_rows, 1):
            if _is_only_generic_action(row.get("recommended_action")):
                issues.append(
                    f"第 {row.get('id') or index} 行 recommended_action 只有空泛建议。"
                )

    if not str(final_markdown or "").strip():
        issues.append("final_markdown 为空。")

    if _references_lost(old_references_json, new_references_json):
        issues.append("references_json 丢失了基础版本中的引用。")

    repair_instruction = ""
    if issues:
        repair_instruction = (
            "只修复结构化 output_json，不要输出 Markdown。"
            "保留原有 FMEA 行和关键字段，明确响应用户修改要求；"
            "建议措施必须具体到预防、探测、责任、期限或验证动作，"
            "不能只写“加强管理”“提高意识”等空泛表述；"
            "不得新增无引用支撑的标准条款；依据不足时写“需人工确认”。"
        )

    return {
        "passed": not issues,
        "issues": issues,
        "repair_instruction": repair_instruction,
    }

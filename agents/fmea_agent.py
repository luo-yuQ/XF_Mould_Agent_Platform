"""
FMEA Agent MVP 后端核心逻辑。

本模块暂不接入现有 qa/rag/writer 主流程。
它只提供 PFMEA 生成所需的基础能力：
- 读取本地 FMEA skill 材料
- 将前端输入规范化为 FMEAInput
- 调用现有 LLM 生成结构化 JSON rows
- 校验 rows 并渲染固定 Markdown
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from schemas.fmea import APScore, FMEAInput, FMEARow, ScoreWithRationale


BASE_DIR = Path(__file__).resolve().parents[1]
SKILL_DIR = BASE_DIR / "skills" / "fmea_generation"
SKILL_FILES = ("SKILL.md", "pfmea_template.md", "check_rules.md")

_llm = None


def _get_llm():
    global _llm
    if _llm is None:
        from langchain_openai import ChatOpenAI

        _llm = ChatOpenAI(
            model=LLM_MODEL,
            temperature=LLM_TEMPERATURE,
            api_key=DASHSCOPE_API_KEY,
            base_url=DASHSCOPE_BASE_URL,
            extra_body={"thinking": {"type": "disabled"}},
        )
    return _llm


def load_fmea_skill() -> str:
    """读取本地 FMEA 生成 skill、Markdown 模板和校验规则。"""
    sections: list[str] = []
    for file_name in SKILL_FILES:
        path = SKILL_DIR / file_name
        sections.append(f"\n\n===== {file_name} =====\n{path.read_text(encoding='utf-8')}")
    return "".join(sections).strip()


def normalize_fmea_input(raw_input: dict[str, Any] | object) -> tuple[FMEAInput | None, list[str]]:
    """
    将前端传入参数规范化为 FMEAInput。

    返回 (fmea_input, missing_fields)。
    当必填字段缺失时，fmea_input 为 None，
    missing_fields 包含 product/process/failure_phenomenon。
    """
    data = raw_input if isinstance(raw_input, dict) else {
        "product": getattr(raw_input, "product", ""),
        "process": getattr(raw_input, "process", ""),
        "failure_phenomenon": getattr(raw_input, "failure_phenomenon", ""),
        "background": getattr(raw_input, "background", ""),
        "fmea_type": getattr(raw_input, "fmea_type", "PFMEA"),
    }

    product = str(data.get("product") or "").strip()
    process = str(data.get("process") or "").strip()
    failure_phenomenon = str(data.get("failure_phenomenon") or "").strip()
    background = str(data.get("background") or "").strip()
    fmea_type = str(data.get("fmea_type") or "PFMEA").strip() or "PFMEA"

    missing_fields = [
        field
        for field, value in (
            ("product", product),
            ("process", process),
            ("failure_phenomenon", failure_phenomenon),
        )
        if not value
    ]
    if missing_fields:
        return None, missing_fields

    return (
        FMEAInput(
            fmea_type=fmea_type,
            product=product[:200],
            process=process[:100],
            failure_phenomenon=failure_phenomenon,
            background=background,
        ),
        [],
    )


def _docs_to_prompt_text(retrieved_docs: list[dict[str, Any]] | str | None) -> str:
    if not retrieved_docs:
        return ""
    if isinstance(retrieved_docs, str):
        return retrieved_docs

    parts: list[str] = []
    for i, doc in enumerate(retrieved_docs, 1):
        source = doc.get("doc_source") or doc.get("source") or ""
        chapter = doc.get("doc_chapter") or doc.get("chapter") or ""
        section = doc.get("doc_section") or doc.get("section_title") or ""
        text = doc.get("text") or doc.get("content") or ""
        meta = " ".join(str(x) for x in (source, chapter, section) if x).strip()
        parts.append(f"[{i}] {meta}\n{text}".strip())
    return "\n\n".join(parts)


def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(1))


def _score(value: Any, default: int = 5) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        score = default
    return max(1, min(10, score))


def _ap(value: Any, rpn: int) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"H", "M", "L"}:
        return normalized
    if rpn >= 100:
        return "H"
    if rpn >= 50:
        return "M"
    return "L"


def _rationale(text: Any) -> str:
    value = str(text or "").strip()
    return value or "需人工确认：基于通用知识，未查到手册原文"


def _score_obj(raw: Any) -> ScoreWithRationale:
    raw = raw if isinstance(raw, dict) else {}
    return ScoreWithRationale(
        value=_score(raw.get("value")),
        suggested=True,
        rationale=_rationale(raw.get("rationale")),
    )


def _coerce_rows(payload: Any, fmea_input: FMEAInput) -> list[FMEARow]:
    rows_payload = payload.get("rows", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows_payload, list):
        raise ValueError("FMEA LLM output does not contain a rows array")

    rows: list[FMEARow] = []
    for index, raw_row in enumerate(rows_payload, 1):
        if not isinstance(raw_row, dict):
            continue

        severity = _score_obj(raw_row.get("severity"))
        occurrence = _score_obj(raw_row.get("occurrence"))
        detection = _score_obj(raw_row.get("detection"))
        rpn = severity.value * occurrence.value * detection.value

        raw_ap = raw_row.get("action_priority") or raw_row.get("ap") or {}
        raw_ap = raw_ap if isinstance(raw_ap, dict) else {"value": raw_ap}
        action_priority = APScore(
            value=_ap(raw_ap.get("value"), rpn),
            suggested=True,
            rationale=_rationale(raw_ap.get("rationale")),
        )

        supplied_rpn = raw_row.get("rpn")
        if supplied_rpn != rpn:
            print(
                f"[FMEA Check] row {index}: RPN 修正 {supplied_rpn} -> {rpn} "
                f"(S={severity.value} O={occurrence.value} D={detection.value})"
            )

        rows.append(
            FMEARow(
                id=index,
                function=str(raw_row.get("function") or "").strip(),
                requirement=str(raw_row.get("requirement") or "").strip(),
                failure_mode=str(raw_row.get("failure_mode") or "").strip(),
                effect=str(raw_row.get("effect") or raw_row.get("failure_effect") or "").strip(),
                severity=severity,
                cause=str(raw_row.get("cause") or raw_row.get("potential_cause") or "").strip(),
                occurrence=occurrence,
                prevention_control=str(raw_row.get("prevention_control") or "").strip(),
                detection_control=str(raw_row.get("detection_control") or "").strip(),
                detection=detection,
                action_priority=action_priority,
                rpn=rpn,
                recommended_action=str(raw_row.get("recommended_action") or "").strip(),
                evidence=_rationale(raw_row.get("evidence") or raw_row.get("rationale")),
            )
        )

    if len(rows) < 3:
        raise ValueError("FMEA rows must contain at least 3 rows")
    return rows


def _build_generation_prompt(
    fmea_input: FMEAInput,
    retrieved_docs: list[dict[str, Any]] | str | None,
    skill_text: str,
) -> str:
    docs_text = _docs_to_prompt_text(retrieved_docs)
    return f"""请基于以下输入生成 PFMEA JSON rows。

【FMEA 输入】
- fmea_type: {fmea_input.fmea_type}
- product: {fmea_input.product}
- process: {fmea_input.process}
- failure_phenomenon: {fmea_input.failure_phenomenon}
- background: {fmea_input.background}

【本地 FMEA Skill / 模板 / 校验规则】
{skill_text}

【RAG 检索材料】
{docs_text or "无检索材料。没有依据时必须标注：需人工确认：基于通用知识，未查到手册原文"}

【输出要求】
只输出一个 JSON 对象，不要输出 Markdown，不要包裹代码块。
顶层格式：
{{
  "rows": [
    {{
      "id": 1,
      "process": "{fmea_input.process}",
      "function": "...",
      "requirement": "...",
      "failure_mode": "...",
      "failure_effect": "...",
      "severity": {{"value": 1-10, "suggested": true, "rationale": "..."}},
      "potential_cause": "...",
      "occurrence": {{"value": 1-10, "suggested": true, "rationale": "..."}},
      "prevention_control": "...",
      "detection_control": "...",
      "detection": {{"value": 1-10, "suggested": true, "rationale": "..."}},
      "ap": {{"value": "H/M/L", "suggested": true, "rationale": "..."}},
      "rpn": "S*O*D 的整数",
      "recommended_action": "...",
      "rationale": "..."
    }}
  ]
}}
必须至少生成 3 行。"""


async def generate_fmea_rows(
    fmea_input: FMEAInput,
    retrieved_docs: list[dict[str, Any]] | str | None,
    skill_text: str,
) -> list[FMEARow]:
    """
    通过项目现有 LLM 生成并校验 FMEA rows。

    LLM 只负责输出 JSON；Markdown 渲染由 render_fmea_markdown 单独处理。
    """
    system = SystemMessage(
        content=(
            "你是 XF 模具的 PFMEA 生成 Agent。你只输出结构化 JSON rows，"
            "不得输出最终 Markdown 表格。S/O/D/AP 都是建议值，必须 suggested=true。"
        )
    )
    prompt = _build_generation_prompt(fmea_input, retrieved_docs, skill_text)

    last_error: Exception | None = None
    for attempt in range(2):
        response = await _get_llm().ainvoke([system, HumanMessage(content=prompt)])
        content = response.content if hasattr(response, "content") else str(response)
        try:
            return _coerce_rows(_extract_json(str(content)), fmea_input)
        except Exception as exc:
            last_error = exc
            print(f"[FMEA Check] JSON 解析/校验失败，第 {attempt + 1} 次: {exc}")
            prompt += (
                "\n\n上一次输出未通过校验。请重新输出严格 JSON，必须包含 rows 数组，"
                "不少于 3 行，RPN 必须等于 S*O*D。"
            )

    raise ValueError(f"FMEA row generation failed: {last_error}")


def _md_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text.replace("|", "\\|")


def render_fmea_markdown(fmea_input: FMEAInput, rows: list[FMEARow]) -> str:
    """
    将已校验的 FMEA rows 渲染为固定 Markdown。

    本函数只做格式化展示，不改写 row 内容、评分或 RPN。
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# PFMEA 分析报告",
        "",
        f"- **分析对象：** {_md_cell(fmea_input.product)}",
        f"- **目标工序：** {_md_cell(fmea_input.process)}",
        f"- **生成时间：** {timestamp}",
        "- **生成方式：** AI 辅助生成，评分为建议值，需人工确认",
        "",
        "## 失效模式分析",
        "",
        "| 序号 | 过程 | 功能要求 | 潜在失效模式 | 失效后果 | S | 潜在原因 | O | 预防控制 | 探测控制 | D | AP | RPN | 建议措施 |",
        "|------|------|----------|-------------|----------|---|----------|---|----------|----------|---|-----|-----|----------|",
    ]

    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.id),
                    _md_cell(fmea_input.process),
                    _md_cell(row.function),
                    _md_cell(row.failure_mode),
                    _md_cell(row.effect),
                    f"**{row.severity.value}**※",
                    _md_cell(row.cause),
                    f"**{row.occurrence.value}**※",
                    _md_cell(row.prevention_control),
                    _md_cell(row.detection_control),
                    f"**{row.detection.value}**※",
                    f"**{row.action_priority.value}**※",
                    str(row.rpn),
                    _md_cell(row.recommended_action),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 评分依据",
            "",
            "| 序号 | S 依据 | O 依据 | D 依据 |",
            "|------|--------|--------|--------|",
        ]
    )
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.id),
                    _md_cell(row.severity.rationale),
                    _md_cell(row.occurrence.rationale),
                    _md_cell(row.detection.rationale),
                ]
            )
            + " |"
        )

    high_risk_rows = [row for row in rows if row.rpn >= 100]
    lines.append("")
    if high_risk_rows:
        lines.append("## 高风险项（RPN >= 100）")
        lines.append("")
        for row in high_risk_rows:
            lines.append(
                f"{row.id}. **{_md_cell(row.failure_mode)}**"
                f"（RPN={row.rpn}）：{_md_cell(row.recommended_action)}"
            )
    else:
        lines.append("## 高风险项")
        lines.append("")
        lines.append("本次分析无 RPN >= 100 的高风险项。")

    lines.extend(
        [
            "",
            "---",
            "",
            "> **注意：** 本报告由 AI 辅助生成，S/O/D/AP 评分为模型建议值，",
            "> 仅供参考。正式使用前请结合实际生产数据和工程判断进行确认。",
            "> 引用来源见正文 [N] 标记。",
        ]
    )
    return "\n".join(lines)

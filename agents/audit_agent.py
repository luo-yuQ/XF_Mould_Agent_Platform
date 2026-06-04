"""
审核检查 Agent MVP 后端核心逻辑。

本模块不接入 LangGraph / API / 数据库 / Memory。
它只提供审核检查所需的基础能力：
- 读取本地 audit_check skill 材料
- 将前端输入规范化为 AuditInput
- 调用现有 LLM 生成结构化 AuditFinding JSON
- 将已校验/归一化的 findings 渲染为固定 Markdown
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from schemas.audit import AuditFinding, AuditInput


BASE_DIR = Path(__file__).resolve().parents[1]
SKILL_DIR = BASE_DIR / "skills" / "audit_check"
SKILL_FILES = ("SKILL.md", "audit_template.md", "check_rules.md")

VALID_AUDIT_TYPES = {"quality_issue", "pfmea", "audit_record", "general"}
VALID_RISK_LEVELS = {"低", "中", "高", "需人工确认"}

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


def load_audit_skill() -> str:
    """读取本地审核检查 skill、输出模板和校验规则。"""
    sections: list[str] = []
    for file_name in SKILL_FILES:
        path = SKILL_DIR / file_name
        sections.append(f"\n\n===== {file_name} =====\n{path.read_text(encoding='utf-8')}")
    return "".join(sections).strip()


def normalize_audit_input(raw_input: dict[str, Any] | object) -> tuple[AuditInput | None, list[str]]:
    """
    将前端传入参数规范化为 AuditInput。

    返回 (audit_input, missing_fields)。
    当 content 为空或 audit_type 非法时，audit_input 为 None。
    """
    data = raw_input if isinstance(raw_input, dict) else {
        "audit_type": getattr(raw_input, "audit_type", "general"),
        "content": getattr(raw_input, "content", ""),
        "focus": getattr(raw_input, "focus", None),
        "background": getattr(raw_input, "background", None),
    }

    audit_type = str(data.get("audit_type") or "general").strip() or "general"
    content = str(data.get("content") or "").strip()
    focus = str(data.get("focus") or "").strip() or None
    background = str(data.get("background") or "").strip() or None

    missing_fields: list[str] = []
    if audit_type not in VALID_AUDIT_TYPES:
        missing_fields.append("audit_type")
    if not content:
        missing_fields.append("content")
    if missing_fields:
        return None, missing_fields

    return (
        AuditInput(
            audit_type=audit_type,  # type: ignore[arg-type]
            content=content,
            focus=focus,
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
    for index, doc in enumerate(retrieved_docs, 1):
        source = doc.get("doc_source") or doc.get("source") or ""
        chapter = doc.get("doc_chapter") or doc.get("chapter") or ""
        section = doc.get("doc_section") or doc.get("section_title") or ""
        text = doc.get("text") or doc.get("content") or ""
        meta = " ".join(str(item) for item in (source, chapter, section) if item).strip()
        parts.append(f"[{index}] {meta}\n{text}".strip())
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


def _as_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _risk_level(value: Any) -> str:
    text = _as_text(value, "需人工确认")
    return text if text in VALID_RISK_LEVELS else "需人工确认"


def _manual_required(value: Any, basis: str, risk_level: str, evidence: str) -> bool:
    if isinstance(value, bool):
        supplied = value
    elif isinstance(value, str):
        supplied = value.strip().lower() in {"true", "1", "yes", "是", "需要", "需人工确认"}
    else:
        supplied = bool(value)

    return supplied or basis == "需人工确认" or risk_level == "需人工确认" or evidence == "输入依据不足"


def _coerce_findings(payload: Any) -> list[AuditFinding]:
    findings_payload = payload.get("findings", payload) if isinstance(payload, dict) else payload
    if not isinstance(findings_payload, list):
        raise ValueError("Audit LLM output does not contain a findings array")

    findings: list[AuditFinding] = []
    for raw_finding in findings_payload:
        if not isinstance(raw_finding, dict):
            continue

        basis = _as_text(raw_finding.get("basis"), "需人工确认")
        risk = _risk_level(raw_finding.get("risk_level"))
        evidence = _as_text(raw_finding.get("evidence_from_input"), "输入依据不足")

        findings.append(
            AuditFinding(
                issue=_as_text(raw_finding.get("issue"), "需人工确认：问题描述不足"),
                category=_as_text(raw_finding.get("category"), "需人工确认"),
                risk_level=risk,
                risk_explanation=_as_text(raw_finding.get("risk_explanation"), "需人工确认"),
                evidence_from_input=evidence,
                basis=basis,
                recommendation=_as_text(raw_finding.get("recommendation"), "需人工确认：需要补充具体整改建议"),
                manual_check_required=_manual_required(
                    raw_finding.get("manual_check_required"),
                    basis,
                    risk,
                    evidence,
                ),
            )
        )

    if not findings:
        raise ValueError("Audit findings must contain at least 1 finding")
    return findings


def _build_generation_prompt(
    audit_input: AuditInput,
    retrieved_docs: list[dict[str, Any]] | str | None,
    skill_text: str,
) -> str:
    docs_text = _docs_to_prompt_text(retrieved_docs)
    focus = audit_input.focus or "未指定"
    background = audit_input.background or "未提供"

    return f"""请基于以下输入生成审核检查 findings JSON。

【审核输入】
- audit_type: {audit_input.audit_type}
- focus: {focus}
- background: {background}
- content:
{audit_input.content}

【本地审核检查 Skill / 模板 / 校验规则】
{skill_text}

【RAG 检索材料】
{docs_text or "无检索材料。没有充分依据时，basis 必须写“需人工确认”，不得编造标准条款。"}

【输出要求】
只输出一个 JSON 对象，不要输出 Markdown，不要包裹代码块。
顶层格式：
{{
  "findings": [
    {{
      "issue": "发现问题",
      "category": "问题类型",
      "risk_level": "低/中/高/需人工确认",
      "risk_explanation": "风险说明",
      "evidence_from_input": "来自用户输入的依据",
      "basis": "来自 FMEA手册 / VDA6.4 的规范依据；依据不足时写：需人工确认",
      "recommendation": "针对具体问题的整改建议",
      "manual_check_required": true
    }}
  ]
}}

硬性规则：
1. 不得编造标准条款、条款编号、页码或文件要求。
2. basis 没有充分检索依据时必须写“需人工确认”。
3. recommendation 必须针对具体 issue，不能泛泛而谈。
4. evidence_from_input 必须来自用户输入；输入依据不足时写“输入依据不足”。
5. 不要输出最终 Markdown。"""


async def generate_audit_findings(
    audit_input: AuditInput,
    retrieved_docs: list[dict[str, Any]] | str | None,
    skill_text: str,
) -> list[AuditFinding]:
    """
    通过项目现有 LLM 生成结构化审核 findings。

    LLM 只负责输出 JSON；Markdown 渲染由 render_audit_markdown 单独处理。
    """
    system = SystemMessage(
        content=(
            "你是 XF质量 的审核检查 Agent。你只输出结构化 JSON findings，"
            "不得输出最终 Markdown。不得编造标准条款；依据不足时 basis 必须写“需人工确认”。"
        )
    )
    prompt = _build_generation_prompt(audit_input, retrieved_docs, skill_text)

    last_error: Exception | None = None
    for attempt in range(2):
        response = await _get_llm().ainvoke([system, HumanMessage(content=prompt)])
        content = response.content if hasattr(response, "content") else str(response)
        try:
            return _coerce_findings(_extract_json(str(content)))
        except Exception as exc:
            last_error = exc
            print(f"[Audit Check] JSON 解析/校验失败，第 {attempt + 1} 次: {exc}")
            prompt += (
                "\n\n上一次输出未通过校验。请重新输出严格 JSON，必须包含 findings 数组，"
                "每条 finding 必须包含 issue/category/risk_level/risk_explanation/"
                "evidence_from_input/basis/recommendation/manual_check_required。"
            )

    raise ValueError(f"Audit finding generation failed: {last_error}")


def _md_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text.replace("|", "\\|")


def render_audit_markdown(audit_input: AuditInput, findings: list[AuditFinding]) -> str:
    """
    将已校验的审核 findings 渲染为固定 Markdown。

    本函数只做格式化展示，不改写 finding 内容。
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    focus = audit_input.focus or "未指定"
    background = audit_input.background or "未提供"

    lines = [
        "# 审核检查报告",
        "",
        "## 基本信息",
        "",
        f"- **审核类型：** {_md_cell(audit_input.audit_type)}",
        f"- **审核重点：** {_md_cell(focus)}",
        f"- **补充背景：** {_md_cell(background)}",
        f"- **生成时间：** {timestamp}",
        "- **生成方式：** AI 辅助审核检查，结论需结合现场证据和正式审核程序确认",
        "",
        "## 审核发现",
        "",
        "| 序号 | 问题 | 类型 | 风险等级 | 输入依据 | 规范依据 | 整改建议 | 需人工确认 |",
        "|------|------|------|----------|----------|----------|----------|--------------|",
    ]

    for index, finding in enumerate(findings, 1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    _md_cell(finding.issue),
                    _md_cell(finding.category),
                    _md_cell(finding.risk_level),
                    _md_cell(finding.evidence_from_input),
                    _md_cell(finding.basis),
                    _md_cell(finding.recommendation),
                    "是" if finding.manual_check_required else "否",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 风险说明",
            "",
            "| 序号 | 风险说明 |",
            "|------|----------|",
        ]
    )

    for index, finding in enumerate(findings, 1):
        lines.append(f"| {index} | {_md_cell(finding.risk_explanation)} |")

    manual_items = [
        f"{index}. {finding.issue}"
        for index, finding in enumerate(findings, 1)
        if finding.manual_check_required
    ]
    lines.extend(["", "## 人工确认项", ""])
    if manual_items:
        lines.extend(f"- {_md_cell(item)}" for item in manual_items)
    else:
        lines.append("- 暂无")

    lines.extend(
        [
            "",
            "---",
            "",
            "> 本报告为 AI 辅助审核检查结果。不得将未被检索材料支持的内容当作正式标准条款；",
            "> 依据不足处必须由人工确认。",
        ]
    )
    return "\n".join(lines)

"""
报告生成 Agent 核心逻辑。

本模块只提供报告生成所需的基础能力，不接 API、前端、Supervisor、
Memory、Milvus 入库或向量化流程。
"""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, DATABASE_URL, LLM_MODEL, LLM_TEMPERATURE
from models.audit import AuditRun
from models.fmea import FMEARun
from schemas.report import ReportInput, ReportOutput, ReportSection


BASE_DIR = Path(__file__).resolve().parents[1]
SKILL_DIR = BASE_DIR / "skills" / "report_generation"
SKILL_FILES = ("SKILL.md", "report_template.md", "report_rules.md")

FIXED_SECTION_HEADINGS = [
    "问题背景",
    "分析对象与范围",
    "参考依据",
    "FMEA分析摘要",
    "审核发现摘要",
    "风险判断",
    "改进措施建议",
    "需人工确认事项",
    "结论",
]

_llm = None
_session_factory = None


def _get_llm():
    """按项目现有方式懒加载 ChatOpenAI。"""
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


def _get_session_factory():
    """创建本模块临时使用的 SQLAlchemy session factory。"""
    global _session_factory
    if _session_factory is None:
        engine = create_engine(DATABASE_URL, pool_pre_ping=True)
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _session_factory


@contextmanager
def _managed_db(db: Session | None = None) -> Iterator[Session]:
    """优先复用调用方传入的 DB session；未传入时临时创建并负责关闭。"""
    if db is not None:
        yield db
        return

    local_db = _get_session_factory()()
    try:
        yield local_db
    finally:
        local_db.close()


def load_report_skill() -> str:
    """读取报告生成 Skill、Markdown 模板和规则文件。"""
    sections: list[str] = []
    for file_name in SKILL_FILES:
        path = SKILL_DIR / file_name
        sections.append(f"\n\n===== {file_name} =====\n{path.read_text(encoding='utf-8')}")
    return "".join(sections).strip()


def _coerce_run_id(value: str | int | None) -> int | None:
    """将外部传入的 run id 转为整数；为空时返回 None。"""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_safe(value: Any) -> Any:
    """将 SQLAlchemy / Pydantic / datetime 等对象转为可 JSON 序列化结构。"""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _dump_json(data: Any, max_len: int | None = None) -> str:
    """稳定序列化来源快照，用于提示词和校验。"""
    text = json.dumps(data, ensure_ascii=False, default=_json_safe, indent=2)
    if max_len and len(text) > max_len:
        return text[:max_len] + "\n...（内容过长，已截断）"
    return text


def _missing_source(source_type: str, run_id: str | int | None, message: str) -> dict[str, Any]:
    """构造缺失来源对象。"""
    return {
        "status": "missing",
        "source_type": source_type,
        "run_id": str(run_id) if run_id else None,
        "message": message,
    }


def _not_found_source(source_type: str, run_id: str | int | None) -> dict[str, Any]:
    """构造未找到或无权限来源对象。"""
    return {
        "status": "not_found",
        "source_type": source_type,
        "run_id": str(run_id) if run_id else None,
        "message": "未找到对应运行记录，或当前用户无权读取，需人工确认。",
    }


def _serialize_fmea_run(run: FMEARun) -> dict[str, Any]:
    """将 FMEA 运行记录转为报告上下文来源。"""
    return {
        "status": "found",
        "source_type": "fmea",
        "run_id": str(run.id),
        "user_id": run.user_id,
        "title": run.title,
        "summary": run.summary,
        "keywords_json": run.keywords_json,
        "artifact_type": run.artifact_type or "fmea_run",
        "product": run.product,
        "process": run.process,
        "failure_phenomenon": run.failure_phenomenon,
        "input_json": run.input_json,
        "retrieval_queries_json": run.retrieval_queries_json,
        "retrieved_refs_json": run.retrieved_refs_json,
        "output_json": run.output_json,
        "output_markdown": run.output_markdown,
        "verify_result_json": run.verify_result_json,
        "created_at": run.created_at,
    }


def _serialize_audit_run(run: AuditRun) -> dict[str, Any]:
    """将 Audit 运行记录转为报告上下文来源。"""
    return {
        "status": "found",
        "source_type": "audit",
        "run_id": str(run.id),
        "user_id": run.user_id,
        "title": run.title,
        "summary": run.summary,
        "keywords_json": run.keywords_json,
        "artifact_type": run.artifact_type or "audit_run",
        "audit_type": run.audit_type,
        "content_text": run.content_text,
        "focus": run.focus,
        "background": run.background,
        "retrieval_queries_json": run.retrieval_queries_json,
        "retrieved_refs_json": run.retrieved_refs_json,
        "findings_json": run.findings_json,
        "final_markdown": run.final_markdown,
        "verify_result_json": run.verify_result_json,
        "created_at": run.created_at,
    }


def load_report_sources(
    user_id: int,
    fmea_run_id: str | int | None = None,
    audit_run_id: str | int | None = None,
    db: Session | None = None,
) -> dict[str, Any]:
    """
    根据明确 run_id 读取报告来源。

    必须按 `user_id + run_id` 查询，不能读取其他用户的数据，也不能通过
    `session_id` 自动查找最近的 FMEA / Audit 产物。
    """
    fmea_id = _coerce_run_id(fmea_run_id)
    audit_id = _coerce_run_id(audit_run_id)

    with _managed_db(db) as session:
        if fmea_run_id and fmea_id is None:
            fmea_source = _not_found_source("fmea", fmea_run_id)
        elif fmea_id is None:
            fmea_source = _missing_source("fmea", None, "未提供 fmea_run_id，需人工确认。")
        else:
            fmea_run = (
                session.query(FMEARun)
                .filter(FMEARun.id == fmea_id, FMEARun.user_id == user_id)
                .first()
            )
            fmea_source = _serialize_fmea_run(fmea_run) if fmea_run else _not_found_source("fmea", fmea_run_id)

        if audit_run_id and audit_id is None:
            audit_source = _not_found_source("audit", audit_run_id)
        elif audit_id is None:
            audit_source = _missing_source("audit", None, "未提供 audit_run_id，需人工确认。")
        else:
            audit_run = (
                session.query(AuditRun)
                .filter(AuditRun.id == audit_id, AuditRun.user_id == user_id)
                .first()
            )
            audit_source = _serialize_audit_run(audit_run) if audit_run else _not_found_source("audit", audit_run_id)

    return {
        "fmea_source": fmea_source,
        "audit_source": audit_source,
    }


def _as_report_input(report_input: ReportInput | dict[str, Any]) -> ReportInput:
    """兼容 dict 和 ReportInput。"""
    if isinstance(report_input, ReportInput):
        return report_input
    return ReportInput.model_validate(report_input)


def _source_reference(source: dict[str, Any]) -> dict[str, Any] | None:
    """把来源对象转换成引用条目。"""
    if source.get("status") != "found":
        return None
    source_type = source.get("source_type", "")
    if source_type == "fmea":
        title = f"FMEA运行记录 #{source.get('run_id')}"
    elif source_type == "audit":
        title = f"Audit运行记录 #{source.get('run_id')}"
    else:
        title = f"{source_type} #{source.get('run_id')}"
    return {
        "source_type": source_type,
        "source_id": source.get("run_id"),
        "title": title,
    }


def _normalize_rag_refs(optional_rag_refs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """规范化可选 RAG 引用，报告 Agent 不直接检索。"""
    refs: list[dict[str, Any]] = []
    for index, ref in enumerate(optional_rag_refs or [], 1):
        if not isinstance(ref, dict):
            continue
        refs.append({
            "source_type": "rag",
            "source_id": str(ref.get("id") or ref.get("chunk_uid") or index),
            "source": ref.get("source") or ref.get("doc_source") or "",
            "chapter": ref.get("chapter") or ref.get("doc_chapter") or "",
            "section_title": ref.get("section_title") or ref.get("doc_section") or "",
            "text": ref.get("text") or ref.get("content") or "",
        })
    return refs


def build_report_context(
    report_input: ReportInput | dict[str, Any],
    fmea_source: dict[str, Any],
    audit_source: dict[str, Any],
    optional_rag_refs: list[dict[str, Any]] | None = None,
    source_match_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    将 FMEA、Audit、用户补充背景和可选 RAG 引用组织为报告上下文。

    本函数只做结构化整理，不改写已校验的 FMEA / Audit 关键事实。
    """
    normalized_input = _as_report_input(report_input)
    rag_refs = _normalize_rag_refs(optional_rag_refs)

    references: list[dict[str, Any]] = []
    for ref in (_source_reference(fmea_source), _source_reference(audit_source)):
        if ref:
            references.append(ref)
    references.extend(rag_refs)
    if normalized_input.extra_background:
        references.append({
            "source_type": "user_input",
            "source_id": "extra_background",
            "title": "用户补充背景",
        })

    source_snapshot = {
        "report_input": normalized_input.model_dump(),
        "fmea_source": fmea_source,
        "audit_source": audit_source,
        "optional_rag_refs": rag_refs,
        "source_match_result": source_match_result or {},
    }

    missing_sources: list[str] = []
    if fmea_source.get("status") != "found":
        missing_sources.append("fmea")
    if audit_source.get("status") != "found":
        missing_sources.append("audit")

    return {
        "report_input": normalized_input.model_dump(),
        "title": normalized_input.title or "质量问题分析报告",
        "fixed_sections": FIXED_SECTION_HEADINGS,
        "fmea_source": fmea_source,
        "audit_source": audit_source,
        "optional_rag_refs": rag_refs,
        "extra_background": normalized_input.extra_background or "",
        "references": references,
        "source_snapshot": source_snapshot,
        "source_match_result": source_match_result or {},
        "missing_sources": missing_sources,
    }


def _build_generation_prompt(report_context: dict[str, Any], skill_text: str) -> str:
    """构造报告生成提示词。"""
    return f"""请基于下列来源生成一份 Markdown 质量问题分析报告。

【报告类型】
{report_context.get("report_input", {}).get("report_type", "quality_issue_report")}

【固定章节】
必须按顺序输出以下章节，章节标题必须完整出现：
{chr(10).join(f"- {heading}" for heading in FIXED_SECTION_HEADINGS)}

【报告生成 Skill / 模板 / 规则】
{skill_text}

【用户补充背景】
{report_context.get("extra_background") or "未提供"}

【FMEA 来源】
{_dump_json(report_context.get("fmea_source", {}), max_len=12000)}

【Audit 来源】
{_dump_json(report_context.get("audit_source", {}), max_len=12000)}

【可选 RAG 参考依据】
{_dump_json(report_context.get("optional_rag_refs", []), max_len=10000)}

【FMEA / Audit 来源匹配提示】
{_dump_json(report_context.get("source_match_result", {}), max_len=4000)}

【硬性要求】
1. 只能整合已有 FMEA、Audit、RAG 和用户补充背景。
2. 不得重新生成 FMEA 表，不得新增失效模式、S/O/D/AP、RPN 或控制措施。
3. 不得重新生成 Audit findings，不得新增审核发现、风险等级、证据或整改建议。
4. 不得编造标准条款、页码、章节编号、责任人、日期或具体数值。
5. FMEA 或 Audit 缺失时，对应章节写“未提供相关结果，需人工确认”。
6. 所有建议必须能追溯到 FMEA、Audit、用户输入或检索依据之一。
7. 如果来源匹配结果 manual_check_required=true，必须在“需人工确认事项”章节写入 warning_message。
8. 来源匹配仅是规则提示，不得据此替换用户选择的 FMEA / Audit 来源。
9. 只输出 Markdown，不要输出 JSON，不要包裹代码块。
"""


async def generate_report_markdown(report_context: dict[str, Any], skill_text: str) -> str:
    """
    调用项目现有 LLM 生成 Markdown 报告。

    报告必须包含固定章节，并且只能基于报告上下文中的来源成文。
    """
    system = SystemMessage(
        content=(
            "你是 XF质量 的报告生成 Agent。你只能整合、归纳和成文，"
            "不得改写已校验的 FMEA / Audit 关键事实，不得编造标准条款。"
        )
    )
    response = await _get_llm().ainvoke([
        system,
        HumanMessage(content=_build_generation_prompt(report_context, skill_text)),
    ])
    content = response.content if hasattr(response, "content") else str(response)
    return str(content).strip()


def _extract_sections(markdown: str) -> dict[str, str]:
    """从 Markdown 中提取固定章节内容。"""
    sections: dict[str, str] = {}
    pattern = re.compile(r"^#{1,3}\s*(.+?)\s*$", re.MULTILINE)
    matches = list(pattern.finditer(markdown or ""))
    for index, match in enumerate(matches):
        heading = match.group(1).strip()
        heading = re.sub(r"^\d+[.、]\s*", "", heading)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        for fixed_heading in FIXED_SECTION_HEADINGS:
            if heading == fixed_heading:
                sections[fixed_heading] = markdown[start:end].strip()
    return sections


def _source_text(source_snapshot: dict[str, Any]) -> str:
    """把来源快照压成文本，用于校验具体事实是否可追溯。"""
    return _dump_json(source_snapshot)


def _has_rag_refs(source_snapshot: dict[str, Any]) -> bool:
    """判断是否存在可用 RAG 依据。"""
    refs = source_snapshot.get("optional_rag_refs", [])
    return bool(refs)


def _find_precise_standard_claims(markdown: str) -> list[str]:
    """查找疑似精确标准条款、页码或章节编号。"""
    patterns = [
        r"第\s*[0-9一二三四五六七八九十]+(?:\.[0-9]+)*\s*条",
        r"第\s*[0-9一二三四五六七八九十]+(?:\.[0-9]+)*\s*章",
        r"[0-9]+(?:\.[0-9]+){1,3}\s*(?:条|章节|节)",
        r"(?:第\s*)?[0-9]+\s*页",
        r"clause\s+[0-9]+(?:\.[0-9]+)*",
        r"section\s+[0-9]+(?:\.[0-9]+)*",
    ]
    claims: list[str] = []
    for pattern in patterns:
        claims.extend(re.findall(pattern, markdown, flags=re.I))
    return sorted(set(str(claim).strip() for claim in claims if str(claim).strip()))


def _find_concrete_claims(markdown: str) -> list[str]:
    """查找需要追溯的具体数值、日期、责任人等信息。"""
    patterns = [
        r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?",
        r"\d+(?:\.\d+)?\s*(?:%|mm|cm|m|kg|g|N|MPa|小时|天|周|月)",
        r"(?:责任人|负责人|责任部门|完成期限)[:：]\s*[^，。\n|]+",
    ]
    claims: list[str] = []
    for pattern in patterns:
        claims.extend(re.findall(pattern, markdown))
    return sorted(set(str(claim).strip() for claim in claims if str(claim).strip()))


def _is_traceable(claim: str, source_text: str, markdown_prefix: str) -> bool:
    """判断具体声明是否能在来源或前文中找到。"""
    return claim in source_text or claim in markdown_prefix


def _conclusion_has_new_claims(markdown: str, sections: dict[str, str]) -> list[str]:
    """检查结论是否引入前文没有出现的新具体声明。"""
    conclusion = sections.get("结论", "")
    if not conclusion:
        return []
    before_conclusion = markdown.split("## 结论", 1)[0] if "## 结论" in markdown else markdown
    claims = _find_concrete_claims(conclusion) + _find_precise_standard_claims(conclusion)
    return [claim for claim in claims if claim not in before_conclusion]


def verify_report(report_output: ReportOutput | dict[str, Any] | str, source_snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    校验报告是否满足 MVP 规则。

    校验范围包括固定章节、来源完整性、是否编造依据、结论是否对应前文，
    以及缺失 FMEA / Audit 时是否写明“需人工确认”。
    """
    if isinstance(report_output, ReportOutput):
        markdown = report_output.final_markdown
    elif isinstance(report_output, dict):
        markdown = str(report_output.get("final_markdown") or "")
    else:
        markdown = str(report_output or "")

    sections = _extract_sections(markdown)
    source_text = _source_text(source_snapshot)
    issues: list[str] = []

    missing_sections = [heading for heading in FIXED_SECTION_HEADINGS if heading not in sections]
    if missing_sections:
        issues.append(f"缺少固定章节：{', '.join(missing_sections)}")

    fmea_source = source_snapshot.get("fmea_source", {})
    audit_source = source_snapshot.get("audit_source", {})
    if fmea_source.get("status") != "found":
        fmea_section = sections.get("FMEA分析摘要", "")
        if "需人工确认" not in fmea_section:
            issues.append("FMEA 缺失时，FMEA分析摘要未写明“需人工确认”。")
        if fmea_section and "未提供相关结果" not in fmea_section:
            issues.append("FMEA 缺失时，报告疑似使用了未提供的 FMEA 信息。")

    if audit_source.get("status") != "found":
        audit_section = sections.get("审核发现摘要", "")
        if "需人工确认" not in audit_section:
            issues.append("Audit 缺失时，审核发现摘要未写明“需人工确认”。")
        if audit_section and "未提供相关结果" not in audit_section:
            issues.append("Audit 缺失时，报告疑似使用了未提供的 Audit 信息。")

    standard_claims = _find_precise_standard_claims(markdown)
    if standard_claims and not _has_rag_refs(source_snapshot):
        issues.append(f"报告出现疑似标准条款或页码，但没有可用 RAG 依据：{', '.join(standard_claims[:5])}")
    else:
        untraceable_standard_claims = [
            claim for claim in standard_claims
            if claim not in source_text
        ]
        if untraceable_standard_claims:
            issues.append(f"报告出现无法追溯的标准条款或页码：{', '.join(untraceable_standard_claims[:5])}")

    for claim in _find_concrete_claims(markdown):
        prefix = markdown.split(claim, 1)[0]
        if not _is_traceable(claim, source_text, prefix):
            issues.append(f"报告出现无法追溯的具体信息：{claim}")

    new_conclusion_claims = _conclusion_has_new_claims(markdown, sections)
    if new_conclusion_claims:
        issues.append(f"结论中出现前文无法推出的具体信息：{', '.join(new_conclusion_claims[:5])}")

    passed = not issues
    repair_instruction = ""
    if not passed:
        repair_instruction = (
            "请在不新增事实的前提下修复报告：补齐固定章节；缺失 FMEA/Audit 时写明"
            "“未提供相关结果，需人工确认”；删除无法追溯的具体数值、条款号、责任人和日期；"
            "确保结论只总结前文已有证据。"
        )

    return {
        "passed": passed,
        "issues": issues,
        "repair_instruction": repair_instruction,
        "checked_sections": list(sections.keys()),
    }


async def repair_report_once(
    report_context: dict[str, Any],
    final_markdown: str,
    verify_result: dict[str, Any],
    skill_text: str,
) -> str:
    """
    根据 verifier 结果最多修复一次报告。

    本函数只做单次修复，不包含循环控制；循环次数应由 workflow 保证最多一次。
    """
    system = SystemMessage(
        content=(
            "你是 XF质量 的报告修复节点。你只能根据校验意见修复 Markdown，"
            "不得新增来源中不存在的事实，不得改写 FMEA / Audit 关键事实。"
        )
    )
    prompt = f"""请修复下面的质量问题分析报告。

【报告生成规则】
{skill_text}

【来源快照】
{_dump_json(report_context.get("source_snapshot", {}), max_len=20000)}

【校验问题】
{_dump_json(verify_result.get("issues", []))}

【修复要求】
{verify_result.get("repair_instruction", "")}

【待修复报告】
{final_markdown}

请只输出修复后的 Markdown，不要输出 JSON，不要包裹代码块。
"""
    response = await _get_llm().ainvoke([system, HumanMessage(content=prompt)])
    content = response.content if hasattr(response, "content") else str(response)
    return str(content).strip()


def _section_source_type(heading: str, source_snapshot: dict[str, Any]) -> str:
    """根据章节标题推断主要来源类型。"""
    if heading == "FMEA分析摘要":
        return "fmea" if source_snapshot.get("fmea_source", {}).get("status") == "found" else "manual_check"
    if heading == "审核发现摘要":
        return "audit" if source_snapshot.get("audit_source", {}).get("status") == "found" else "manual_check"
    if heading == "参考依据":
        return "rag" if source_snapshot.get("optional_rag_refs") else "generated_summary"
    if heading == "问题背景":
        return "user_input" if source_snapshot.get("report_input", {}).get("extra_background") else "generated_summary"
    if heading == "需人工确认事项":
        return "manual_check"
    return "generated_summary"


def _section_source_ids(source_type: str, source_snapshot: dict[str, Any]) -> list[str]:
    """根据来源类型生成章节来源 ID。"""
    if source_type == "fmea":
        run_id = source_snapshot.get("fmea_source", {}).get("run_id")
        return [str(run_id)] if run_id else []
    if source_type == "audit":
        run_id = source_snapshot.get("audit_source", {}).get("run_id")
        return [str(run_id)] if run_id else []
    if source_type == "rag":
        return [
            str(ref.get("source_id"))
            for ref in source_snapshot.get("optional_rag_refs", [])
            if ref.get("source_id")
        ]
    if source_type == "user_input":
        return ["extra_background"]
    return []


def _manual_check_items_from(markdown: str, verify_result: dict[str, Any]) -> list[str]:
    """从报告和校验结果中提取人工确认事项。"""
    items: list[str] = []
    sections = _extract_sections(markdown)
    manual_section = sections.get("需人工确认事项", "")
    for line in manual_section.splitlines():
        cleaned = re.sub(r"^\s*[-*]\s*", "", line).strip()
        cleaned = re.sub(r"^\s*\d+[.、]\s*", "", cleaned).strip()
        if cleaned:
            items.append(cleaned)
    for issue in verify_result.get("issues", []):
        if "需人工确认" in issue and issue not in items:
            items.append(issue)
    return items


def ensure_source_match_warning(
    markdown: str,
    source_match_result: dict[str, Any] | None,
) -> str:
    """Ensure a required source-match reminder is present in the manual-check section."""
    result = source_match_result or {}
    if not result.get("manual_check_required"):
        return markdown
    warning = str(result.get("warning_message") or "").strip()
    if not warning or warning in markdown:
        return markdown

    heading_pattern = re.compile(
        r"^(#{1,3})\s*(?:\d+[.、]\s*)?需人工确认事项\s*$",
        re.MULTILINE,
    )
    heading_match = heading_pattern.search(markdown or "")
    reminder = f"- {warning}"
    if not heading_match:
        suffix = "\n\n" if markdown and not markdown.endswith("\n") else "\n"
        return f"{markdown}{suffix}## 需人工确认事项\n\n{reminder}".strip()

    next_heading = re.search(
        r"^#{1,3}\s+.+$",
        markdown[heading_match.end():],
        re.MULTILINE,
    )
    insert_at = (
        heading_match.end() + next_heading.start()
        if next_heading
        else len(markdown)
    )
    before = markdown[:insert_at].rstrip()
    after = markdown[insert_at:].lstrip("\n")
    separator = "\n\n" if after else ""
    return f"{before}\n\n{reminder}{separator}{after}"


def render_report_result(
    final_markdown: str,
    verify_result: dict[str, Any],
    references: list[dict[str, Any]] | None = None,
    manual_check_items: list[str] | None = None,
    source_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    渲染报告核心逻辑的最终返回结果。

    返回字段包括 final_markdown、verify_result、references、manual_check_items。
    如果提供 source_snapshot，会额外返回结构化 sections。
    """
    result = {
        "final_markdown": final_markdown,
        "verify_result": verify_result,
        "references": references or [],
        "manual_check_items": manual_check_items or _manual_check_items_from(final_markdown, verify_result),
    }

    if source_snapshot is not None:
        sections = _extract_sections(final_markdown)
        result["sections"] = [
            ReportSection(
                heading=heading,
                content=sections.get(heading, ""),
                source_type=_section_source_type(heading, source_snapshot),  # type: ignore[arg-type]
                source_ids=_section_source_ids(_section_source_type(heading, source_snapshot), source_snapshot),
            ).model_dump()
            for heading in FIXED_SECTION_HEADINGS
        ]

    return result

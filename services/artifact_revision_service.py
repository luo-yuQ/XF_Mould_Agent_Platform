"""业务产物追改与版本记录服务。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agents.fmea_agent import (
    _coerce_rows,
    _extract_json,
    _get_llm,
    render_fmea_markdown,
)
from models.artifact_version import BusinessArtifactVersion
from models.audit import AuditRun
from models.chat import ChatSession
from models.fmea import FMEARun
from models.report import ReportRun
from schemas.artifact_revision import (
    ArtifactListItem,
    ArtifactVersionOutput,
    ArtifactVersionSummary,
    ArtifactVersionsOutput,
)
from schemas.fmea import FMEAInput
from time_utils import utc_now
from verifiers.artifact_revision_verifier import verify_artifact_revision


SUPPORTED_ARTIFACT_TYPES = {"fmea", "audit", "report"}


class ArtifactRevisionError(Exception):
    """带稳定错误码的追改异常。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _artifact_id(value: str | int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ArtifactRevisionError("artifact_not_found", "artifact_id 无效。") from exc


def _version_output(version: BusinessArtifactVersion) -> ArtifactVersionOutput:
    return ArtifactVersionOutput(
        artifact_id=str(version.artifact_id),
        version_id=version.id,
        version_no=version.version_no,
        parent_version_id=version.parent_version_id,
        artifact_type=version.artifact_type,
        output_json=version.output_json or {},
        final_markdown=version.final_markdown or "",
        diff_summary=version.diff_summary_json or [],
        verify_result=version.verify_result_json or {},
        references=version.references_json or [],
        created_at=version.created_at,
    )


def _version_summary(version: BusinessArtifactVersion) -> ArtifactVersionSummary:
    return ArtifactVersionSummary(
        version_id=version.id,
        version_no=version.version_no,
        parent_version_id=version.parent_version_id,
        operation_type=version.operation_type,
        revision_instruction=version.revision_instruction,
        created_at=version.created_at,
        diff_summary=version.diff_summary_json or [],
    )


def _timestamp(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _latest_time(*values: datetime | None) -> datetime:
    available = [value for value in values if value is not None]
    return max(available, key=_timestamp) if available else utc_now()


def _fmea_title(run: FMEARun) -> str:
    return str(run.title or "").strip() or f"{run.product} - {run.process}"


def _fmea_summary(run: FMEARun) -> str:
    return str(run.summary or "").strip() or f"问题现象：{run.failure_phenomenon}"


def _audit_title(run: AuditRun) -> str:
    return str(run.title or "").strip() or f"{run.audit_type} 审核检查"


def _audit_summary(run: AuditRun) -> str:
    return str(run.summary or "").strip() or " ".join(str(run.content_text or "").split())[:180]


def create_initial_fmea_version(
    db: Session,
    run: FMEARun,
    *,
    flush: bool = True,
) -> BusinessArtifactVersion:
    """为 FMEA run 幂等创建 V1，不修改原 run 内容。"""
    existing = (
        db.query(BusinessArtifactVersion)
        .filter(
            BusinessArtifactVersion.artifact_type == "fmea",
            BusinessArtifactVersion.artifact_id == run.id,
            BusinessArtifactVersion.version_no == 1,
        )
        .one_or_none()
    )
    if existing:
        return existing

    version = BusinessArtifactVersion(
        artifact_id=run.id,
        version_no=1,
        parent_version_id=None,
        artifact_type="fmea",
        operation_type="create",
        revision_instruction=None,
        input_snapshot_json=run.input_json or {},
        output_json=run.output_json or {},
        final_markdown=run.output_markdown or "",
        references_json=run.references_json or [],
        diff_summary_json=[],
        verify_result_json=run.verify_result_json or {},
        created_by=run.user_id,
        created_at=run.created_at or utc_now(),
    )
    db.add(version)
    if flush:
        db.flush()
    return version


def load_base_artifact_version(
    db: Session,
    artifact_id: str | int,
    base_version_id: str,
    *,
    artifact_type: str | None = None,
    created_by: int | None = None,
) -> BusinessArtifactVersion:
    """读取并校验基础版本归属。"""
    query = db.query(BusinessArtifactVersion).filter(
        BusinessArtifactVersion.id == base_version_id,
        BusinessArtifactVersion.artifact_id == _artifact_id(artifact_id),
    )
    if artifact_type:
        query = query.filter(BusinessArtifactVersion.artifact_type == artifact_type)
    if created_by is not None:
        query = query.filter(BusinessArtifactVersion.created_by == created_by)
    version = query.one_or_none()
    if not version:
        raise ArtifactRevisionError(
            "invalid_base_version",
            "基础版本不存在、不属于当前产物或无访问权限。",
        )
    return version


def _load_owned_fmea_run(
    db: Session,
    artifact_id: str | int,
    created_by: int,
) -> FMEARun:
    run = (
        db.query(FMEARun)
        .filter(
            FMEARun.id == _artifact_id(artifact_id),
            FMEARun.user_id == created_by,
        )
        .one_or_none()
    )
    if not run:
        raise ArtifactRevisionError("artifact_not_found", "业务产物不存在或无访问权限。")
    if run.artifact_type not in (None, "", "fmea_run"):
        raise ArtifactRevisionError(
            "artifact_type_mismatch",
            "业务产物记录与请求的 artifact_type 不匹配。",
        )
    return run


def _load_owned_artifact_run(
    db: Session,
    artifact_id: str | int,
    artifact_type: str,
    created_by: int,
) -> FMEARun | AuditRun | ReportRun:
    model = {
        "fmea": FMEARun,
        "audit": AuditRun,
        "report": ReportRun,
    }.get(artifact_type)
    if model is None:
        raise ArtifactRevisionError("artifact_type_mismatch", "不支持的 artifact_type。")
    run = (
        db.query(model)
        .filter(model.id == _artifact_id(artifact_id), model.user_id == created_by)
        .one_or_none()
    )
    if not run:
        raise ArtifactRevisionError("artifact_not_found", "业务产物不存在或无访问权限。")
    expected_run_type = f"{artifact_type}_run"
    if run.artifact_type not in (None, "", expected_run_type):
        raise ArtifactRevisionError(
            "artifact_type_mismatch",
            "业务产物记录与请求的 artifact_type 不匹配。",
        )
    return run


def _resolve_artifact_type(
    db: Session,
    *,
    artifact_id: str | int,
    artifact_type: str | None,
    created_by: int,
) -> str:
    if artifact_type:
        if artifact_type not in SUPPORTED_ARTIFACT_TYPES:
            raise ArtifactRevisionError("artifact_type_mismatch", "不支持的 artifact_type。")
        return artifact_type

    version_types = (
        db.query(BusinessArtifactVersion.artifact_type)
        .filter(
            BusinessArtifactVersion.artifact_id == _artifact_id(artifact_id),
            BusinessArtifactVersion.created_by == created_by,
        )
        .distinct()
        .all()
    )
    if len(version_types) == 1:
        return str(version_types[0][0])
    if len(version_types) > 1:
        raise ArtifactRevisionError(
            "artifact_type_mismatch",
            "artifact_id 在多个产物类型中存在，请显式传入 artifact_type。",
        )

    matches = []
    for candidate_type, model in (
        ("fmea", FMEARun),
        ("audit", AuditRun),
        ("report", ReportRun),
    ):
        exists = (
            db.query(model.id)
            .filter(model.id == _artifact_id(artifact_id), model.user_id == created_by)
            .first()
        )
        if exists:
            matches.append(candidate_type)
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ArtifactRevisionError("artifact_not_found", "业务产物不存在或无访问权限。")
    raise ArtifactRevisionError(
        "artifact_type_mismatch",
        "artifact_id 在多个产物类型中存在，请显式传入 artifact_type。",
    )


def _latest_version(
    db: Session,
    *,
    artifact_id: int,
    artifact_type: str,
    created_by: int,
) -> BusinessArtifactVersion | None:
    return (
        db.query(BusinessArtifactVersion)
        .filter(
            BusinessArtifactVersion.artifact_type == artifact_type,
            BusinessArtifactVersion.artifact_id == artifact_id,
            BusinessArtifactVersion.created_by == created_by,
        )
        .order_by(BusinessArtifactVersion.version_no.desc())
        .first()
    )


def list_session_artifacts(
    db: Session,
    *,
    session_id: str,
    created_by: int,
    artifact_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[ArtifactListItem]:
    """按会话列出业务产物，仅读取 run 表和版本表。"""
    if artifact_type and artifact_type not in SUPPORTED_ARTIFACT_TYPES:
        raise ArtifactRevisionError("artifact_type_mismatch", "不支持的 artifact_type。")
    if limit < 1 or limit > 100:
        raise ArtifactRevisionError("invalid_pagination", "limit 必须在 1-100 之间。")
    if offset < 0:
        raise ArtifactRevisionError("invalid_pagination", "offset 不能小于 0。")

    session = (
        db.query(ChatSession.id)
        .filter(ChatSession.id == session_id, ChatSession.user_id == created_by)
        .first()
    )
    if not session:
        raise ArtifactRevisionError("artifact_not_found", "会话不存在或无访问权限。")

    items: list[ArtifactListItem] = []
    if artifact_type in (None, "fmea"):
        runs = (
            db.query(FMEARun)
            .filter(FMEARun.session_id == session_id, FMEARun.user_id == created_by)
            .all()
        )
        created_initial = False
        for run in runs:
            if _latest_version(
                db,
                artifact_id=run.id,
                artifact_type="fmea",
                created_by=created_by,
            ) is None:
                create_initial_fmea_version(db, run)
                created_initial = True
        if created_initial:
            db.commit()

        for run in runs:
            latest = _latest_version(
                db,
                artifact_id=run.id,
                artifact_type="fmea",
                created_by=created_by,
            )
            created_at = run.created_at or utc_now()
            updated_at = _latest_time(
                latest.created_at if latest else None,
                run.updated_at,
                created_at,
            )
            items.append(
                ArtifactListItem(
                    artifact_id=str(run.id),
                    artifact_type="fmea",
                    title=_fmea_title(run),
                    latest_version_id=latest.id if latest else None,
                    latest_version_no=latest.version_no if latest else None,
                    created_at=created_at,
                    updated_at=updated_at,
                    summary=_fmea_summary(run),
                )
            )

    if artifact_type in (None, "audit"):
        runs = (
            db.query(AuditRun)
            .filter(AuditRun.session_id == session_id, AuditRun.user_id == created_by)
            .all()
        )
        for run in runs:
            latest = _latest_version(
                db,
                artifact_id=run.id,
                artifact_type="audit",
                created_by=created_by,
            )
            created_at = run.created_at or utc_now()
            updated_at = _latest_time(
                latest.created_at if latest else None,
                run.updated_at,
                created_at,
            )
            items.append(
                ArtifactListItem(
                    artifact_id=str(run.id),
                    artifact_type="audit",
                    title=_audit_title(run),
                    latest_version_id=latest.id if latest else None,
                    latest_version_no=latest.version_no if latest else None,
                    created_at=created_at,
                    updated_at=updated_at,
                    summary=_audit_summary(run),
                )
            )

    # report_runs 当前没有 session_id，不能把用户级报告错误归属到某个会话。
    items.sort(key=lambda item: _timestamp(item.updated_at), reverse=True)
    return items[offset : offset + limit]


def list_artifact_versions(
    db: Session,
    *,
    artifact_id: str | int,
    artifact_type: str | None,
    created_by: int,
) -> ArtifactVersionsOutput:
    """列出当前用户可访问的产物版本；旧 FMEA run 会幂等补建 V1。"""
    resolved_type = _resolve_artifact_type(
        db,
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        created_by=created_by,
    )
    run = _load_owned_artifact_run(db, artifact_id, resolved_type, created_by)
    versions = (
        db.query(BusinessArtifactVersion)
        .filter(
            BusinessArtifactVersion.artifact_type == resolved_type,
            BusinessArtifactVersion.artifact_id == run.id,
            BusinessArtifactVersion.created_by == created_by,
        )
        .order_by(BusinessArtifactVersion.version_no.asc())
        .all()
    )
    if not versions and resolved_type == "fmea":
        create_initial_fmea_version(db, run)
        db.commit()
        versions = (
            db.query(BusinessArtifactVersion)
            .filter(
                BusinessArtifactVersion.artifact_type == resolved_type,
                BusinessArtifactVersion.artifact_id == run.id,
                BusinessArtifactVersion.created_by == created_by,
            )
            .order_by(BusinessArtifactVersion.version_no.asc())
            .all()
        )
    return ArtifactVersionsOutput(
        artifact_id=str(run.id),
        artifact_type=resolved_type,
        versions=[_version_summary(version) for version in versions],
    )


def get_artifact_version(
    db: Session,
    *,
    artifact_id: str | int,
    version_id: str,
    artifact_type: str | None,
    created_by: int,
) -> ArtifactVersionOutput:
    """读取单个历史版本，不触发任何生成或检索逻辑。"""
    resolved_type = _resolve_artifact_type(
        db,
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        created_by=created_by,
    )
    _load_owned_artifact_run(db, artifact_id, resolved_type, created_by)
    version = (
        db.query(BusinessArtifactVersion)
        .filter(
            BusinessArtifactVersion.id == version_id,
            BusinessArtifactVersion.artifact_id == _artifact_id(artifact_id),
            BusinessArtifactVersion.artifact_type == resolved_type,
            BusinessArtifactVersion.created_by == created_by,
        )
        .one_or_none()
    )
    if version:
        return _version_output(version)
    raise ArtifactRevisionError(
        "invalid_base_version",
        "版本不存在、不属于当前产物或无访问权限。",
    )


def build_revision_prompt(
    *,
    artifact_type: str,
    old_output_json: dict[str, Any],
    input_snapshot_json: dict[str, Any],
    references_json: list[Any],
    revision_instruction: str,
) -> str:
    """构造结构化追改 prompt；Audit/Report 仅保留占位约束。"""
    if artifact_type in {"audit", "report"}:
        return (
            f"{artifact_type} 追改仅预留类型约束，MVP 不执行。"
            "不得改写已校验事实，不得编造依据。"
        )
    if artifact_type != "fmea":
        raise ArtifactRevisionError("artifact_type_mismatch", "不支持的 artifact_type。")

    return f"""请基于旧版 PFMEA 结构化结果执行一次定向追改。

【用户修改要求】
{revision_instruction}

【原始输入快照】
{json.dumps(input_snapshot_json, ensure_ascii=False)}

【旧版 output_json】
{json.dumps(old_output_json, ensure_ascii=False)}

【已有 references_json】
{json.dumps(references_json, ensure_ascii=False)}

【约束】
1. 只输出 JSON 对象，格式为 {{"rows": [...]}}，不要输出 Markdown。
2. 保留旧版所有失效模式行、字段结构和未被修改要求涉及的内容。
3. 优先修改 recommended_action 等明确被要求修改的结构化字段。
4. S/O/D/AP 必须保持 suggested=true，RPN 必须等于 S*O*D。
5. 不得编造标准条款或引用。已有 references 不足时，在 evidence 中写“需人工确认”。
6. 建议措施不能只写“加强管理”“提高意识”等空泛表述，应包含具体预防、探测、责任、期限或验证动作。
7. 不要返回 references_json；引用由服务层继承并保存。
"""


def render_artifact_markdown(
    *,
    artifact_type: str,
    input_snapshot_json: dict[str, Any],
    output_json: dict[str, Any],
) -> str:
    """将已结构化的业务结果渲染为展示 Markdown。"""
    if artifact_type in {"audit", "report"}:
        raise ArtifactRevisionError("feature_reserved", f"{artifact_type} 追改尚未开放。")
    if artifact_type != "fmea":
        raise ArtifactRevisionError("artifact_type_mismatch", "不支持的 artifact_type。")

    fmea_input = FMEAInput.model_validate(input_snapshot_json)
    rows = _coerce_rows(output_json, fmea_input)
    return render_fmea_markdown(fmea_input, rows)


def build_diff_summary(
    old_output_json: dict[str, Any],
    new_output_json: dict[str, Any],
) -> list[dict[str, str]]:
    """生成可读的基础字段差异摘要。"""
    old_rows = old_output_json.get("rows", []) if isinstance(old_output_json, dict) else []
    new_rows = new_output_json.get("rows", []) if isinstance(new_output_json, dict) else []
    old_by_id = {
        str(row.get("id", index)): row
        for index, row in enumerate(old_rows, 1)
        if isinstance(row, dict)
    }
    new_by_id = {
        str(row.get("id", index)): row
        for index, row in enumerate(new_rows, 1)
        if isinstance(row, dict)
    }
    summaries: list[dict[str, str]] = []
    field_labels = {
        "recommended_action": "建议措施",
        "prevention_control": "预防控制",
        "detection_control": "探测控制",
        "severity": "严重度",
        "occurrence": "发生度",
        "detection": "探测度",
        "action_priority": "行动优先级",
        "evidence": "依据",
    }

    for row_id in sorted(old_by_id.keys() | new_by_id.keys()):
        old_row = old_by_id.get(row_id)
        new_row = new_by_id.get(row_id)
        if old_row is None:
            summaries.append({"section": f"row:{row_id}", "summary": "新增失效模式行"})
            continue
        if new_row is None:
            summaries.append({"section": f"row:{row_id}", "summary": "删除失效模式行"})
            continue
        changed = [
            field_labels.get(field, field)
            for field in old_row.keys() | new_row.keys()
            if json.dumps(old_row.get(field), ensure_ascii=False, sort_keys=True, default=str)
            != json.dumps(new_row.get(field), ensure_ascii=False, sort_keys=True, default=str)
        ]
        if changed:
            failure_mode = str(new_row.get("failure_mode") or old_row.get("failure_mode") or row_id)
            summaries.append(
                {
                    "section": f"row:{row_id}",
                    "summary": f"{failure_mode}：修改了{'、'.join(changed)}",
                }
            )
    return summaries


async def _generate_revised_output(
    *,
    prompt: str,
    input_snapshot_json: dict[str, Any],
    llm: Any,
) -> dict[str, Any]:
    system = SystemMessage(
        content=(
            "你是业务产物追改节点，只修改 PFMEA 结构化 JSON。"
            "不得输出 Markdown，不得编造标准条款，不得删除无关内容。"
        )
    )
    response = await llm.ainvoke([system, HumanMessage(content=prompt)])
    content = response.content if hasattr(response, "content") else str(response)
    fmea_input = FMEAInput.model_validate(input_snapshot_json)
    rows = _coerce_rows(_extract_json(str(content)), fmea_input)
    return {"rows": [row.model_dump() for row in rows]}


async def revise_artifact_version(
    db: Session,
    *,
    artifact_id: str | int,
    artifact_type: str,
    base_version_id: str,
    revision_instruction: str,
    created_by: int,
    llm: Any | None = None,
) -> ArtifactVersionOutput:
    """基于明确的基础版本生成并保存一个新版本。"""
    if artifact_type not in SUPPORTED_ARTIFACT_TYPES:
        raise ArtifactRevisionError("artifact_type_mismatch", "不支持的 artifact_type。")
    if artifact_type in {"audit", "report"}:
        raise ArtifactRevisionError("feature_reserved", f"{artifact_type} 追改尚未开放。")

    instruction = str(revision_instruction or "").strip()
    if not instruction:
        raise ArtifactRevisionError("invalid_revision_instruction", "修改要求不能为空。")
    if len(instruction) > 4000:
        raise ArtifactRevisionError("invalid_revision_instruction", "修改要求超过长度上限。")

    _load_owned_fmea_run(db, artifact_id, created_by)

    base = load_base_artifact_version(
        db,
        artifact_id,
        base_version_id,
        artifact_type=artifact_type,
        created_by=created_by,
    )
    old_output_json = base.output_json or {}
    old_references_json = base.references_json or []
    input_snapshot_json = base.input_snapshot_json or {}
    revision_llm = llm or _get_llm()

    prompt = build_revision_prompt(
        artifact_type=artifact_type,
        old_output_json=old_output_json,
        input_snapshot_json=input_snapshot_json,
        references_json=old_references_json,
        revision_instruction=instruction,
    )
    new_references_json = list(old_references_json)
    new_output_json: dict[str, Any] = {}
    final_markdown = ""
    try:
        new_output_json = await _generate_revised_output(
            prompt=prompt,
            input_snapshot_json=input_snapshot_json,
            llm=revision_llm,
        )
        final_markdown = render_artifact_markdown(
            artifact_type=artifact_type,
            input_snapshot_json=input_snapshot_json,
            output_json=new_output_json,
        )
        verification = verify_artifact_revision(
            artifact_type=artifact_type,
            old_output_json=old_output_json,
            new_output_json=new_output_json,
            old_references_json=old_references_json,
            new_references_json=new_references_json,
            revision_instruction=instruction,
            final_markdown=final_markdown,
        )
    except Exception as exc:
        verification = {
            "passed": False,
            "issues": [f"首轮结构化输出解析或渲染失败：{exc}"],
            "repair_instruction": (
                "输出完整且可校验的 FMEA JSON，必须包含不少于 3 行的 rows；"
                "保留所有必要字段，RPN 等于 S*O*D，不要输出 Markdown。"
            ),
        }

    repair_attempted = False
    if not verification["passed"]:
        repair_attempted = True
        repair_prompt = (
            f"{prompt}\n\n【首次校验问题】\n"
            f"{json.dumps(verification['issues'], ensure_ascii=False)}\n"
            f"【修复要求】\n{verification['repair_instruction']}\n"
            "这是唯一一次 repair。请输出修复后的完整 JSON 对象。"
        )
        try:
            new_output_json = await _generate_revised_output(
                prompt=repair_prompt,
                input_snapshot_json=input_snapshot_json,
                llm=revision_llm,
            )
            final_markdown = render_artifact_markdown(
                artifact_type=artifact_type,
                input_snapshot_json=input_snapshot_json,
                output_json=new_output_json,
            )
            verification = verify_artifact_revision(
                artifact_type=artifact_type,
                old_output_json=old_output_json,
                new_output_json=new_output_json,
                old_references_json=old_references_json,
                new_references_json=new_references_json,
                revision_instruction=instruction,
                final_markdown=final_markdown,
            )
        except Exception as exc:
            verification = {
                "passed": False,
                "issues": [f"一次 repair 后结构化输出仍无效：{exc}"],
                "repair_instruction": "",
            }

    verification = {
        **verification,
        "repair_attempted": repair_attempted,
        "repair_count": 1 if repair_attempted else 0,
    }
    if not verification["passed"]:
        raise ArtifactRevisionError(
            "revision_verify_failed",
            "追改结果在一次 repair 后仍未通过校验。",
        )

    diff_summary = build_diff_summary(old_output_json, new_output_json)
    next_version_no = (
        db.query(func.coalesce(func.max(BusinessArtifactVersion.version_no), 0))
        .filter(
            BusinessArtifactVersion.artifact_type == artifact_type,
            BusinessArtifactVersion.artifact_id == _artifact_id(artifact_id),
        )
        .scalar()
        + 1
    )
    version = BusinessArtifactVersion(
        artifact_id=_artifact_id(artifact_id),
        version_no=next_version_no,
        parent_version_id=base.id,
        artifact_type=artifact_type,
        operation_type="revise",
        revision_instruction=instruction,
        input_snapshot_json=input_snapshot_json,
        output_json=new_output_json,
        final_markdown=final_markdown,
        references_json=new_references_json,
        diff_summary_json=diff_summary,
        verify_result_json=verification,
        created_by=created_by,
    )
    db.add(version)
    try:
        db.commit()
        db.refresh(version)
    except IntegrityError as exc:
        db.rollback()
        raise ArtifactRevisionError(
            "version_conflict",
            "并发追改导致版本号冲突，请基于最新版本重试。",
        ) from exc
    return _version_output(version)

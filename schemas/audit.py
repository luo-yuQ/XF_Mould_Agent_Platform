"""
审核检查 Agent MVP - Pydantic Schema 定义。

仅供 LLM 结构化输入/输出使用，不接 LangGraph / API / 数据库。
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AuditInput(BaseModel):
    """审核检查请求的输入参数。"""

    audit_type: Literal["quality_issue", "pfmea", "audit_record", "general"] = Field(
        description="审核类型：quality_issue=质量问题，pfmea=PFMEA 内容，audit_record=审核记录，general=通用文本。",
    )
    content: str = Field(
        description="用户粘贴的待审核文本内容。",
    )
    focus: Optional[str] = Field(
        default=None,
        description="可选的审核重点，例如重点检查原因分析、整改闭环、PFMEA 失效链等。",
    )
    background: Optional[str] = Field(
        default=None,
        description="可选的补充背景，例如产品、工序、客户要求、现场情况或审核场景。",
    )


class AuditFinding(BaseModel):
    """单条审核发现。"""

    issue: str = Field(
        description="发现的问题，必须是具体、可理解的审核发现。",
    )
    category: str = Field(
        description="问题类型，例如原因分析不足、整改措施不闭环、证据不足、规范依据不足等。",
    )
    risk_level: str = Field(
        description="风险等级，只能使用低、中、高、需人工确认。",
    )
    risk_explanation: str = Field(
        description="风险说明，解释该问题可能造成的质量、审核、合规或过程风险。",
    )
    evidence_from_input: str = Field(
        description="来自用户输入文本的依据；输入依据不足时应写明输入依据不足。",
    )
    basis: str = Field(
        description="来自 FMEA手册 / VDA6.4 检索材料的规范依据；依据不足时必须写需人工确认。",
    )
    recommendation: str = Field(
        description="针对具体问题的整改建议，必须可执行，不能泛泛而谈。",
    )
    manual_check_required: bool = Field(
        description="是否需要人工确认；依据不足、输入不完整或风险无法判断时应为 true。",
    )


class AuditOutput(BaseModel):
    """审核检查的完整结构化输出。"""

    input: AuditInput = Field(
        description="本次审核检查的输入参数。",
    )
    findings: list[AuditFinding] = Field(
        description="审核发现列表。",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="模型在审核过程中做出的假设；没有假设时为空列表。",
    )
    manual_check_items: list[str] = Field(
        default_factory=list,
        description="需要人工进一步确认的事项列表。",
    )
    references: list[dict] = Field(
        default_factory=list,
        description="引用来源列表，保存来自 FMEA手册 / VDA6.4 检索材料的结构化元数据。",
    )

"""
报告生成 Workflow MVP - Pydantic Schema 定义。

这些 schema 只定义报告生成的数据契约，不把报告工作流接入
LangGraph、API 路由、数据库模型或前端页面。
"""
from typing import Literal, Optional

from pydantic import BaseModel, Field


ReportType = Literal["quality_issue_report"]
ReportSourceType = Literal[
    "fmea",
    "audit",
    "rag",
    "user_input",
    "generated_summary",
    "manual_check",
]


class ReportInput(BaseModel):
    """报告生成 MVP 的输入参数。"""

    report_type: ReportType = Field(
        description="报告类型。MVP 只支持 quality_issue_report。",
    )
    title: Optional[str] = Field(
        default=None,
        description="可选报告标题。",
    )
    fmea_run_id: Optional[str] = Field(
        default=None,
        description="用户明确选择的 FMEA 运行记录 ID。",
    )
    audit_run_id: Optional[str] = Field(
        default=None,
        description="用户明确选择的 Audit 运行记录 ID。",
    )
    extra_background: Optional[str] = Field(
        default=None,
        description="用户补充的报告背景信息。",
    )
    include_chat_summary: bool = Field(
        default=False,
        description="是否显式包含对话摘要的预留开关，默认 false。",
    )
    quality_case_id: Optional[str] = Field(
        default=None,
        description="质量案例 ID 预留字段。MVP 不依赖完整质量案例系统。",
    )


class ReportSection(BaseModel):
    """带来源追溯信息的单个结构化报告章节。"""

    heading: str = Field(
        description="章节标题。",
    )
    content: str = Field(
        description="章节内容，使用兼容 Markdown 的文本。",
    )
    source_type: ReportSourceType = Field(
        description="本章节使用的主要来源类型。",
    )
    source_ids: list[str] = Field(
        default_factory=list,
        description="本章节引用的来源 ID，例如 fmea_run_id、audit_run_id 或 citation id。",
    )


class ReportOutput(BaseModel):
    """报告生成 MVP 的输出结果。"""

    report_type: ReportType = Field(
        description="报告类型。",
    )
    title: str = Field(
        description="最终报告标题。",
    )
    source_fmea_run_id: Optional[str] = Field(
        default=None,
        description="来源 FMEA 运行记录 ID。",
    )
    source_audit_run_id: Optional[str] = Field(
        default=None,
        description="来源 Audit 运行记录 ID。",
    )
    sections: list[ReportSection] = Field(
        description="结构化报告章节列表。",
    )
    final_markdown: str = Field(
        description="最终 Markdown 报告。",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="报告成文过程中产生的假设。",
    )
    manual_check_items: list[str] = Field(
        default_factory=list,
        description="需要人工确认的事项。",
    )
    references: list[dict] = Field(
        default_factory=list,
        description="来自已选择 FMEA、Audit、RAG 或用户输入的引用来源。",
    )
    verify_result: dict = Field(
        default_factory=dict,
        description="报告校验结果。",
    )

"""销售协作多智能体的数据契约。"""

from typing import Literal

from pydantic import BaseModel, Field


Confidence = Literal["high", "medium", "low"]
PlannerAgent = Literal["rd", "quality", "reviewer", "writer", "fmea", "audit"]


class Citation(BaseModel):
    """支持协作智能体输出内容的引用来源。"""

    citation_id: str
    source_type: str
    source_name: str
    title: str | None = None
    page: int | None = None
    chunk_id: str | None = None
    quote: str | None = None


class Claim(BaseModel):
    """带置信度和可选引用依据的结论。"""

    claim_id: str
    text: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: Confidence
    requires_manual_check: bool = False


class RiskItem(BaseModel):
    """专家智能体识别出的风险项。"""

    risk_id: str
    category: str
    description: str
    impact: str | None = None
    mitigation: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    requires_manual_check: bool = False


class Recommendation(BaseModel):
    """建议采取的行动及其理由和引用依据。"""

    recommendation_id: str
    text: str
    rationale: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    requires_manual_check: bool = False


class MissingInformation(BaseModel):
    """完成协作任务前仍需补充的信息。"""

    item_id: str
    question: str
    reason: str
    required_for: str | None = None


class PlannerTask(BaseModel):
    """协作规划智能体分配的一项任务。"""

    task_id: str
    agent: PlannerAgent
    objective: str
    required_sources: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    required: bool = True


class PlannerOutput(BaseModel):
    """协作规划智能体的标准结构化输出。"""

    tasks: list[PlannerTask]
    rationale: str
    complexity: Literal["simple", "collaboration", "requires_workflow"]
    warnings: list[str] = Field(default_factory=list)


class SpecialistOutput(BaseModel):
    """研发、质量等专家智能体共用的标准结构化输出。"""

    summary: str
    claims: list[Claim] = Field(default_factory=list)
    risks: list[RiskItem] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    missing_information: list[MissingInformation] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    confidence: Confidence


class ReviewerOutput(BaseModel):
    """对汇总后的专家输出进行审核的结构化结果。"""

    passed: bool
    conflicts: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    manual_check_items: list[str] = Field(default_factory=list)
    repair_instructions: list[str] = Field(default_factory=list)

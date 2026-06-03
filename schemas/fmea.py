"""
FMEA Agent MVP — Pydantic Schema 定义
仅供 LLM 结构化输出使用，不接 LangGraph / API / 数据库。
"""
from pydantic import BaseModel, Field


class FMEAInput(BaseModel):
    """FMEA 生成请求的输入参数"""

    fmea_type: str = Field(
        default="PFMEA",
        description="FMEA 类型，当前仅支持 PFMEA",
    )
    product: str = Field(
        description="分析对象 / 产品名称，如：汽车座椅滑轨冲压件",
    )
    process: str = Field(
        description="目标工序名称，如：落料、拉伸、翻边",
    )
    failure_phenomenon: str = Field(
        default="",
        description="用户描述的具体问题现象，如：开裂、毛刺超标。为空时覆盖该工序常见失效模式",
    )
    background: str = Field(
        default="",
        description="补充背景信息：材料、批量、设备、客户要求等。可选",
    )


class ScoreWithRationale(BaseModel):
    """带依据的评分对象（S / O / D 共用）"""

    value: int = Field(
        description="评分数值，S/O/D 均为 1-10",
    )
    suggested: bool = Field(
        default=True,
        description="固定为 True，表示此为模型建议值，需人工确认",
    )
    rationale: str = Field(
        description="评分依据说明，引用检索材料的 [N] 标记不得丢失",
    )


class APScore(BaseModel):
    """行动优先级评分"""

    value: str = Field(
        description="行动优先级：H(高) / M(中) / L(低)",
    )
    suggested: bool = Field(
        default=True,
        description="固定为 True，表示此为模型建议值，需人工确认",
    )
    rationale: str = Field(
        description="AP 判定依据",
    )


class FMEARow(BaseModel):
    """PFMEA 单行失效模式数据"""

    id: int = Field(
        description="行号，从 1 开始",
    )
    function: str = Field(
        description="该过程的功能要求",
    )
    requirement: str = Field(
        description="具体要求描述，如尺寸公差、表面质量等",
    )
    failure_mode: str = Field(
        description="潜在失效模式",
    )
    effect: str = Field(
        description="失效后果，对产品、下游工序或客户的影响",
    )
    severity: ScoreWithRationale = Field(
        description="严重度(S)评分，含依据",
    )
    cause: str = Field(
        description="潜在失效原因 / 机理",
    )
    occurrence: ScoreWithRationale = Field(
        description="发生度(O)评分，含依据",
    )
    prevention_control: str = Field(
        description="现行预防控制措施",
    )
    detection_control: str = Field(
        description="现行探测控制措施",
    )
    detection: ScoreWithRationale = Field(
        description="探测度(D)评分，含依据",
    )
    action_priority: APScore = Field(
        description="行动优先级(AP)，H/M/L",
    )
    rpn: int = Field(
        description="风险优先数 = S × O × D",
    )
    recommended_action: str = Field(
        description="建议的改进措施",
    )
    evidence: str = Field(
        description="评分依据汇总，引用 [N] 标记。无依据时标注'需人工确认：基于通用知识，未查到手册原文'",
    )


class FMEAOutput(BaseModel):
    """FMEA 生成的完整输出"""

    input: FMEAInput = Field(
        description="本次分析的输入参数",
    )
    rows: list[FMEARow] = Field(
        description="失效模式行列表，不少于 3 行",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="本次分析中模型做出的假设，如：'默认材料为 SPCC'、'默认批量 > 10000 件'",
    )
    manual_check_items: list[str] = Field(
        default_factory=list,
        description="需要人工确认的事项清单，如：'S 评分需结合客户投诉数据确认'",
    )
    references: list[str] = Field(
        default_factory=list,
        description="引用来源列表，如：'[1] FMEA 手册 第2章 步骤一'",
    )

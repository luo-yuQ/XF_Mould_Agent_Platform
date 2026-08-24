"""销售协作 Quality Specialist：复用 VDA 6.4 知识库生成质量分析。"""

from __future__ import annotations

from typing import Any

from config import MILVUS_COLLECTION_QUALITY
from schemas.sales_collaboration import SpecialistOutput

from agents.sales_specialist_common import (
    Retriever,
    build_retrieval_query,
    find_task,
    invoke_structured_specialist,
    retrieve_sales_chunks,
)


QUALITY_SPECIALIST_PROMPT = """你是销售协作流程中的 Quality Specialist。

职责：
- 基于 XF VDA 6.4 和质量体系知识，分析质量保障、审核准备、过程控制和记录要求。
- 输出面向售前方案的结论、风险、建议和信息缺口。

边界：
- 不编造模具结构、材料选择、成型参数或其他技术工艺方案。
- 不生成正式 Audit 报告，不宣称尚无材料证明的认证或项目执行事实。
- 质量建议必须区分体系要求、建议措施和当前项目已确认事实。
"""


def run_sales_quality_specialist(
    *,
    user_request: str,
    customer_context: dict[str, Any],
    execution_plan: list[dict[str, Any]],
    task: dict[str, Any] | None = None,
    retriever: Retriever | None = None,
    llm: Any = None,
) -> SpecialistOutput:
    """调用现有质量 RAG 和协作专用结构化 LLM。"""
    current_task = task or find_task(execution_plan, "quality_analysis")
    query = build_retrieval_query(user_request, customer_context, current_task)
    chunks = (retriever or retrieve_sales_chunks)(query, MILVUS_COLLECTION_QUALITY)
    return invoke_structured_specialist(
        system_prompt=QUALITY_SPECIALIST_PROMPT,
        user_request=user_request,
        customer_context=customer_context,
        execution_plan=execution_plan,
        task=current_task,
        chunks=chunks,
        citation_prefix="quality-source",
        no_source_question="请补充客户质量要求、验收标准、审核范围和过程控制记录。",
        llm=llm,
    )

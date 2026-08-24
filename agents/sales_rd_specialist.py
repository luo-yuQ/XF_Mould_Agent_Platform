"""销售协作 R&D Specialist：复用 FMEA 知识库生成技术风险分析。"""

from __future__ import annotations

from typing import Any

from config import MILVUS_COLLECTION_FMEA
from schemas.sales_collaboration import SpecialistOutput

from agents.sales_specialist_common import (
    Retriever,
    build_retrieval_query,
    find_task,
    invoke_structured_specialist,
    retrieve_sales_chunks,
)


RD_SPECIALIST_PROMPT = """你是销售协作流程中的 R&D Specialist。

职责：
- 基于 FMEA 方法和技术风险知识，分析模具技术可行性、工艺风险和验证重点。
- 输出面向售前方案的结论、风险、建议和信息缺口。

边界：
- 不声明 XF 公司的质量体系、认证、审核或组织能力。
- 不生成正式 DFMEA/PFMEA 表格，不给出未经项目数据验证的 S/O/D 或 RPN。
- 不把知识库的一般方法要求表述为当前项目已完成的事实。
"""


def run_sales_rd_specialist(
    *,
    user_request: str,
    customer_context: dict[str, Any],
    execution_plan: list[dict[str, Any]],
    task: dict[str, Any] | None = None,
    retriever: Retriever | None = None,
    llm: Any = None,
) -> SpecialistOutput:
    """调用现有 FMEA RAG 和协作专用结构化 LLM。"""
    current_task = task or find_task(execution_plan, "rd_analysis")
    query = build_retrieval_query(user_request, customer_context, current_task)
    chunks = (retriever or retrieve_sales_chunks)(query, MILVUS_COLLECTION_FMEA)
    return invoke_structured_specialist(
        system_prompt=RD_SPECIALIST_PROMPT,
        user_request=user_request,
        customer_context=customer_context,
        execution_plan=execution_plan,
        task=current_task,
        chunks=chunks,
        citation_prefix="rd-source",
        no_source_question="请补充材料、关键尺寸、成型工序和试模验证数据。",
        llm=llm,
    )

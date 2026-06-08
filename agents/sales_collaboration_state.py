"""销售协作流程的共享状态契约。"""

from typing import TypedDict


class SalesCollaborationState(TypedDict):
    """销售协作多智能体之间传递的共享状态。"""

    request_id: str
    user_id: int
    session_id: str | None
    user_request: str
    customer_context: dict
    execution_plan: list[dict]
    rd_analysis: dict
    quality_analysis: dict
    optional_artifacts: list[dict]
    review_result: dict
    final_report: str
    citations: list[dict]
    status: str
    error: str | None

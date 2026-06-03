"""
XF 模具智能体平台 - 共享状态定义
"""
from typing import Any, NotRequired, Sequence, TypedDict


class AgentState(TypedDict):
    """LangGraph 共享状态"""

    # 对话消息历史
    messages: Sequence

    # 当前发送方（用于追踪流程）
    sender: str

    # ============ Supervisor 产出 ============
    next_agent: str       # "rd" / "quality"
    intent: str           # 意图标签
    agent_override: str   # 用户手动指定: "" / "rd" / "quality"（空串=自动）

    # ============ RAG 检索结果 ============
    rag_result: str       # 向量检索原始文本（兼容旧协议）
    rag_is_relevant: bool # RAG 结果是否相关

    # ============ 结构化引用 ============
    rag_chunks: list      # 结构化检索块: [{"chunk_uid":"FMEA 手册_text_000001", "text":"...", "doc_source":"FMEA手册", "doc_chapter":"2.1", "doc_section":"步骤一", "chunk_type":"text|table_parent|table_summary|table_row_block", "parent_chunk_uid":"", "table_id":"...", "heading_path":"2 > 2.1 步骤一", "row_range":"1-50"}, ...]
    citation_map: dict    # id → 元数据映射: {1: {"source":"FMEA手册", "chapter":"2.1", "section_title":"步骤一", "heading_path":"...", "chunk_type":"text", "table_id":"", "row_range":"", "chunk_uid":"", "parent_chunk_uid":""}, ...}
    citation_ids: list    # Writer 实际引用的 id 列表

    # ============ 输出相关 ============
    task_completed: bool  # 任务是否完成

    # ============ FMEA MVP 可选状态 ============
    fmea_input_raw: NotRequired[dict]
    fmea_input: NotRequired[dict]
    fmea_missing_fields: NotRequired[list]
    fmea_retrieval_queries: NotRequired[list]
    fmea_rows: NotRequired[list]
    fmea_verification: NotRequired[dict]
    fmea_repair_attempted: NotRequired[bool]
    fmea_markdown: NotRequired[str]
    fmea_run_id: NotRequired[str]
    fmea_user_id: NotRequired[int]
    fmea_session_id: NotRequired[str]
    fmea_db_session: NotRequired[Any]
    fmea_error: NotRequired[str]
    fmea_extra: NotRequired[dict[str, Any]]

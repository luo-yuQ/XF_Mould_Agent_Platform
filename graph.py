"""
XF 模具智能体平台 - 图拓扑与路由编排
Supervisor → 研发子图 / 质量子图
"""
from typing import Literal
from langgraph.graph import StateGraph, START, END
from state import AgentState
from agents.supervisor import supervisor_node
from agents.rd_agent import rd_rag_node, rd_writer_node
from agents.quality_agent import qa_rag_node, qa_writer_node
from agents.chat_agent import chat_chat_node


def build_graph():
    """构建主图"""
    workflow = StateGraph(AgentState)

    # =============================================================================
    # 注册节点
    # =============================================================================
    # 宏观层
    workflow.add_node("supervisor", supervisor_node)

    # 研发子图（R&D Agent）
    workflow.add_node("rd_rag", rd_rag_node)
    workflow.add_node("rd_writer", rd_writer_node)

    # 质量子图（Quality Agent）
    workflow.add_node("qa_rag", qa_rag_node)
    workflow.add_node("qa_writer", qa_writer_node)

    # 闲聊节点（Chat Agent）
    workflow.add_node("chat_chat", chat_chat_node)

    # =============================================================================
    # Supervisor → 子图路由
    # =============================================================================
    def macro_router(state: AgentState) -> Literal["rd_rag", "qa_rag", "chat_chat", "__end__"]:
        next_agent = state.get("next_agent", "")
        print(f"[Macro Router] 路由到: {next_agent}")
        if next_agent == "rd":
            return "rd_rag"
        elif next_agent == "quality":
            return "qa_rag"
        elif next_agent == "chat":
            return "chat_chat"
        return "__end__"

    workflow.add_conditional_edges(
        "supervisor",
        macro_router,
        {
            "rd_rag": "rd_rag",
            "qa_rag": "qa_rag",
            "chat_chat": "chat_chat",
            "__end__": END,
        }
    )

    # =============================================================================
    # 子图内部路由: RAG → Writer（直连，无 grader）
    # =============================================================================
    workflow.add_edge("rd_rag", "rd_writer")
    workflow.add_edge("qa_rag", "qa_writer")

    # =============================================================================
    # 最终输出
    # =============================================================================
    workflow.add_edge("rd_writer", END)
    workflow.add_edge("qa_writer", END)
    workflow.add_edge("chat_chat", END)

    # =============================================================================
    # 入口
    # =============================================================================
    workflow.add_edge(START, "supervisor")

    return workflow.compile()

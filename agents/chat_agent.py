"""
闲聊智能体（Chat Agent）
处理问候、天气查询等非专业对话，可调用天气等生活工具
"""
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import ToolNode
from state import AgentState
from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from tools.weather import get_weather


SYSTEM_PROMPT = """你是 XF 模具智能体平台的闲聊助手。

【能力】
1. 回答天气等日常问题（会调用天气工具获取实时数据）
2. 处理问候、闲聊等非专业对话
3. 如果用户问的是模具技术、FMEA 或质量管理等专业问题，请礼貌告知这些已转给对应专业智能体，你可以帮忙转达

【风格】
- 友好、热情、轻松
- 回答简洁自然
"""

llm = ChatOpenAI(
    model=LLM_MODEL,
    temperature=LLM_TEMPERATURE,
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
    extra_body={"thinking": {"type": "disabled"}},
)

tools = [get_weather]
llm_with_tools = llm.bind_tools(tools)
tool_node = ToolNode(tools)

system_msg = SystemMessage(content=SYSTEM_PROMPT)

SENDER = "chat_chat"


async def chat_chat_node(state: AgentState) -> AgentState:
    """闲聊节点：问候、天气查询等非专业对话"""
    messages = list(state["messages"])

    local_messages = [system_msg] + messages

    # 第一轮：LLM 决定是否调用工具
    ai_msg = await llm_with_tools.ainvoke(local_messages)

    if ai_msg.tool_calls:
        # 执行工具调用
        tool_state = {"messages": [ai_msg]}
        result = tool_node.invoke(tool_state)
        tool_msgs = [m for m in result.get("messages", []) if isinstance(m, ToolMessage)]

        # 第二轮：LLM 基于工具结果生成最终回答
        second_round = local_messages + [ai_msg] + tool_msgs
        final = await llm.ainvoke(second_round)
        content = final.content if hasattr(final, "content") else str(final)
    else:
        content = ai_msg.content if hasattr(ai_msg, "content") else str(ai_msg)

    return {
        "messages": messages + [AIMessage(content=content, name="chat_agent")],
        "sender": SENDER,
        "next_agent": "chat",
        "rag_result": "",
        "rag_chunks": [],
        "citation_map": {},
        "citation_ids": [],
        "rag_is_relevant": False,
        "task_completed": True,
    }

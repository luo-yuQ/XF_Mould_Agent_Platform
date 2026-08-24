"""
Supervisor 节点：意图识别与路由分发
判断用户问题是研发类（FMEA）还是质量类（VDA6.4），路由到对应智能体
"""
from pydantic import BaseModel, Field
from typing import Literal

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from agents.structured_llm import ainvoke_structured_json
from state import AgentState
from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, LLM_MODEL, LLM_TEMPERATURE


# =============================================================================
# LLM 初始化
# =============================================================================
LLM = ChatOpenAI(
    model=LLM_MODEL,
    temperature=LLM_TEMPERATURE,
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
    extra_body={"thinking": {"type": "disabled"}},
)


# =============================================================================
# Supervisor System Prompt
# =============================================================================
SUPERVISOR_PROMPT = """【角色定位】
你是 XF 模具智能体平台的调度中枢。你的职责是理解客户意图，将问题路由到最合适的智能体。

【意图分类】
用户问题分为以下几类：

1. rd（研发类）：涉及模具技术方案、FMEA 失效模式分析、产品设计、工艺过程、风险评级、FMEA 方法论等；
   例如："怎么做 DFMEA？"、"冲压开裂的失效原因有哪些？"、"帮我生成一份 PFMEA 报告"

2. quality（质量类）：涉及质量管理体系、VDA6.4 标准、公司资质认证、流程职责、文件管理、质量体系审核等；
   例如："你们通过了什么认证？"、"质量部的职责是什么？"、"文件修改要走什么流程？"

3. chat（闲聊类）：涉及天气查询、问候闲聊、日常对话等非专业问题；
   例如："今天天气怎么样？"、"你好"、"你能做什么"、"讲个笑话"

【调度规则】
- 所有研发/技术/FMEA 相关问题 → rd
- 所有质量/体系/认证/流程相关问题 → quality
- 所有问候、闲聊、天气等非专业问题 → chat
- 若问题同时涉及多方面，判断核心诉求，路由到最相关的一个

【输出格式】
必须输出一个有效的 JSON 对象：
- "reasoning": 字符串，思考过程
- "next_agent": "rd" 或 "quality" 或 "chat"
- "intent": 字符串，意图简述

示例：
{"reasoning": "客户询问 FMEA 的严重度评级标准，属于研发类技术问题", "next_agent": "rd", "intent": "fmea_methodology"}
{"reasoning": "客户想了解公司的质量体系认证情况，属于质量类问题", "next_agent": "quality", "intent": "quality_certification"}
{"reasoning": "客户问今天天气怎么样，属于闲聊类问题", "next_agent": "chat", "intent": "weather"}
"""


# =============================================================================
# 结构化输出 Schema
# =============================================================================
class RouteDecision(BaseModel):
    reasoning: str = Field(description="思考过程")
    next_agent: Literal["rd", "quality", "chat"] = Field(description="路由目标")
    intent: str = Field(description="意图标签")


# =============================================================================
# Supervisor 节点函数
# =============================================================================
async def supervisor_node(state: AgentState) -> AgentState:
    """
    Supervisor 节点：意图识别 + 宏观路由
    如果用户手动指定了 agent_override，跳过 LLM 分类直接路由
    """
    messages = list(state["messages"])

    # 用户手动指定智能体，跳过 LLM 分类
    override = state.get("agent_override", "")
    if override in ("rd", "quality"):
        print(f"\n[Supervisor] 用户指定路由: {override}，跳过意图识别")
        return {
            "messages": messages,
            "sender": "supervisor",
            "next_agent": override,
            "intent": f"user_override_{override}",
            "agent_override": override,
            "rag_result": "",
            "rag_chunks": [],
            "citation_map": {},
            "citation_ids": [],
            "rag_is_relevant": False,
            "task_completed": False,
        }

    last_msg = messages[-1].content if messages else ""
    print(f"\n[Supervisor] 分析用户输入: {str(last_msg)[:80]}...")

    prompt_messages = [SystemMessage(content=SUPERVISOR_PROMPT)] + messages

    import json, re

    # 使用结构化输出（json_mode 兼容 DashScope）
    try:
        decision = await ainvoke_structured_json(
            LLM,
            RouteDecision,
            prompt_messages,
        )
    except Exception:
        # 兜底：解析 JSON
        raw = (await LLM.ainvoke(prompt_messages)).content
        try:
            data = json.loads(raw)
            decision = RouteDecision(**data)
        except Exception:
            match = re.search(r'\{.*?"next_agent".*?\}', raw, re.DOTALL)
            if match:
                decision = RouteDecision.model_validate_json(match.group())
            else:
                decision = RouteDecision(reasoning="解析失败默认路由", next_agent="rd", intent="default")

    print(f"[Supervisor] 路由: {decision.next_agent}, 意图: {decision.intent}")
    print(f"[Supervisor] 推理: {decision.reasoning}")

    return {
        "messages": messages,
        "sender": "supervisor",
        "next_agent": decision.next_agent,
        "intent": decision.intent,
        "rag_result": "",
        "rag_chunks": [],
        "citation_map": {},
        "citation_ids": [],
        "rag_is_relevant": False,
        "task_completed": False,
    }

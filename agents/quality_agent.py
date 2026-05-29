"""
质量智能体（Quality Agent）
基于 VDA6.4 质量手册，提供质量管理体系问答、公司资质介绍、流程查询等服务
"""
import json
import re
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from state import AgentState
from config import (
    DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, LLM_MODEL, LLM_TEMPERATURE,
    MILVUS_COLLECTION_QUALITY,
)
from tools.rag import retrieve_structured, chunks_to_text


# =============================================================================
# LLM 初始化
# =============================================================================
llm = ChatOpenAI(
    model=LLM_MODEL,
    temperature=LLM_TEMPERATURE,
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
    extra_body={"thinking": {"type": "disabled"}},
)

# =============================================================================
# 辅助函数
# =============================================================================
def _extract_user_query(messages) -> str:
    for msg in reversed(messages):
        if hasattr(msg, "content") and isinstance(msg, HumanMessage):
            return msg.content.strip()
    return ""


# =============================================================================
# RAG 检索节点
# =============================================================================
QA_RAG_PROMPT = """你是一个质量管理体系检索专家。

你的职责是根据用户问题，生成精确的搜索词，调用 quality_rag_search 工具从 VDA6.4 质量手册中检索相关内容。

【搜索词生成规则】
- 提取核心实体、术语、缩写作为搜索词
- 搜索词要精准简洁
- 优先使用手册中的专业术语（如：VDA6.4、COP、MP、SP、管理评审、内审、过程审核、不合格品、纠正预防等）

【输出要求】
只输出一个 Tool Call，不要输出其他内容。
"""

qa_rag_system = SystemMessage(content=QA_RAG_PROMPT)


import asyncio

async def qa_rag_node(state: AgentState) -> AgentState:
    """质量 RAG 节点：直接使用用户输入检索，不额外调 LLM 生成搜索词"""
    messages = list(state["messages"])
    user_query = _extract_user_query(messages)

    print(f"\n[质量 Agent - RAG] 用户问题: {user_query[:80]}...")

    # 同步检索（embedding API + Milvus）丢到线程池，避免阻塞事件循环
    loop = asyncio.get_event_loop()
    rag_chunks = await loop.run_in_executor(
        None, retrieve_structured, user_query, MILVUS_COLLECTION_QUALITY
    )
    tool_result = chunks_to_text(rag_chunks)

    print(f"[质量 Agent - RAG] 检索结果: {len(rag_chunks)} chunks")

    return {
        "messages": messages,
        "sender": "qa_rag",
        "rag_result": tool_result,
        "rag_chunks": rag_chunks,
        "rag_is_relevant": False,
        "task_completed": False,
    }


# =============================================================================
# Writer（最终输出节点）—— JSON Mode + 结构化引用
# =============================================================================
QA_WRITER_PROMPT = """你是一个专业的质量管理顾问，也是 XF 模具公司的质量智能体。

【角色定位】
你是面向客户的质量专家，负责回答 VDA6.4 质量管理体系相关问题，介绍公司的质量能力。

【引用规则】
- 当提供检索材料时，请基于材料扩充回答，并在文中使用 [N] 标记引用来源（如 [1]、[2]）
- 引用标记放在引用内容的句尾或段尾
- 如果检索材料与问题不相关或无材料提供，则基于自身知识回答，不使用引用标记

【核心能力】
1. 体系认证问答：VDA6.4、ISO9001 认证相关问题
2. 公司能力介绍：公司历史、规模、技术实力、资质荣誉
3. 组织分工查询：各部门职责和权限
4. 过程流程解释：COP/MP/SP 各过程的含义和流程
5. 文件管理说明：文件分级体系和管理要求
6. 风险管理咨询：风险识别和应对措施
7. 审核支持：内审、管理评审、产品审核等

【输出要求】
- 回答必须内容充实且有深度，总字数不得少于 1200 字，禁止输出简短、概括性的回答
- 结构清晰，按以下层次组织（每个层次都要充分展开，不能一句话带过）：
  1. 背景与概述：简要说明问题涉及的质量体系背景
  2. 核心解答：对用户问题逐点详细回答，每条要点配以说明和举例
  3. 流程说明：如有相关流程，详细描述步骤、责任人、输入输出
  4. 文件与记录：提及相关的体系文件、表单或记录要求
  5. 总结：概括关键要求和建议
- 语言专业、准确
- 基于手册内容作答，不编造手册中没有的信息，但可以在手册内容基础上进行合理的业务解读和展开

【输出格式（重要）】
你必须输出一个严格的 JSON 对象：
{"answer": "你的回答正文（含 [N] 引用标记）", "citation_ids": [1, 2, 3]}
citation_ids 是你正文中实际引用的引用文献编号列表（按出现顺序，去重）。如果未引用任何材料，citation_ids 为空数组 []。
"""

qa_writer_system = SystemMessage(content=QA_WRITER_PROMPT)


async def qa_writer_node(state: AgentState) -> AgentState:
    """质量 Writer 节点：JSON Mode 输出，生成含 [id] 引用的回答"""
    messages = list(state["messages"])
    rag_chunks = state.get("rag_chunks", [])
    user_query = _extract_user_query(messages)

    print(f"\n[质量 Agent - Writer] 生成回答...")
    print(f"[质量 Agent - Writer] chunks={len(rag_chunks)}")

    # 只要有检索结果就构建 citation_map 和引用文本，不依赖 grader 的判断
    citation_map = {}
    chunks_text = ""
    if rag_chunks:
        for i, chunk in enumerate(rag_chunks, 1):
            citation_map[i] = {
                "source": chunk.get("doc_source", ""),
                "chapter": chunk.get("doc_chapter", ""),
                "section_title": chunk.get("doc_section", ""),
                "heading_path": chunk.get("heading_path", ""),
                "chunk_type": chunk.get("chunk_type", "text"),
                "table_id": chunk.get("table_id", ""),
                "row_range": chunk.get("row_range", ""),
                "chunk_uid": chunk.get("chunk_uid", ""),
                "parent_chunk_uid": chunk.get("parent_chunk_uid", ""),
            }
            ch = f"第{chunk['doc_chapter']}章" if chunk.get("doc_chapter") else ""
            sec = chunk.get("doc_section", "")
            meta = f"（{chunk['doc_source']} {ch} {sec}）".replace("  ", " ").strip()
            chunks_text += f"\n【引用文献 {i}】{meta}\n{chunk['text']}\n"

    content_block = ""
    if chunks_text:
        content_block = f"\n\n--- 【质量手册检索材料】 ---\n{chunks_text}\n"

    writer_input = f"""【用户问题】
{user_query}

{content_block}

请根据上述信息生成一份详尽的回答（不少于 800 字），严格遵循输出要求中的五层结构展开。如果无检索材料，基于自身知识回答，citation_ids 为空数组。务必写得充分、具体，禁止泛泛而谈。
"""

    local_messages = [qa_writer_system, HumanMessage(content=writer_input)]

    # 不使用 response_format=json_object（该模型在此模式下输出不稳定），
    # 改为纯文本输出 + 正则/JSON 解析兜底
    final = ""
    async for chunk in llm.astream(local_messages):
        if chunk.content:
            final += chunk.content

    print(f"[质量 Agent - Writer] 原始输出长度: {len(final)} 字符")

    # 解析 JSON 输出（从最终文本中提取 JSON 对象）
    answer_text = ""
    citation_ids = []
    try:
        # 尝试从文本中提取 JSON 对象
        json_match = re.search(r'\{.*?\}', final, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            if isinstance(parsed, dict):
                answer_text = parsed.get("answer", "")
                citation_ids = [int(c) for c in parsed.get("citation_ids", []) if isinstance(c, (int, float))]
        if answer_text:
            print(f"[质量 Agent - Writer] 解析成功, answer={len(answer_text)}字符, citations={citation_ids}")
        else:
            raise ValueError("no valid JSON found")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as e:
        print(f"[质量 Agent - Writer] JSON 解析失败: {e}，降级为原始文本")
        match = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', final, re.DOTALL)
        if match:
            answer_text = match.group(1)
        else:
            answer_text = final
        ids_match = re.search(r'"citation_ids"\s*:\s*\[([^\]]*)\]', final)
        if ids_match:
            citation_ids = [int(x.strip()) for x in ids_match.group(1).split(",") if x.strip().isdigit()]
        citation_ids = citation_ids or list(citation_map.keys())

    # 过滤：只保留 citation_map 中真实存在的 ID
    citation_ids = [cid for cid in citation_ids if cid in citation_map]

    if not answer_text:
        answer_text = "抱歉，未能生成回答。"

    return {
        "messages": messages + [AIMessage(content=answer_text, name="quality_agent")],
        "sender": "qa_writer",
        "rag_result": state.get("rag_result", ""),
        "rag_chunks": rag_chunks,
        "rag_is_relevant": bool(citation_ids),
        "citation_map": citation_map,
        "citation_ids": citation_ids,
        "task_completed": True,
    }

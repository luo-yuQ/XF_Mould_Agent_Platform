"""
研发智能体（R&D Agent）
基于 FMEA 手册，提供失效模式分析、FMEA 方法问答、FMEA 报告生成等服务
"""
import json
import re
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from state import AgentState
from config import (
    DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, LLM_MODEL, LLM_TEMPERATURE,
    MILVUS_COLLECTION_FMEA,
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

llm_cheap = ChatOpenAI(
    model=LLM_MODEL,
    temperature=0.0,
    api_key=DASHSCOPE_API_KEY,
    base_url=DASHSCOPE_BASE_URL,
    extra_body={"thinking": {"type": "disabled"}},
)

# JSON Mode LLM
llm_json = ChatOpenAI(
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
        if hasattr(msg, "content") and "user" in (getattr(msg, "name", "") or getattr(msg, "type", "")):
            return msg.content.strip()
        if hasattr(msg, "content") and isinstance(msg, HumanMessage):
            return msg.content.strip()
    return ""


# =============================================================================
# RAG 检索节点
# =============================================================================
RD_RAG_PROMPT = """你是一个 FMEA 领域检索专家。

你的职责是根据用户问题，生成精确的搜索词，调用 fmea_rag_search 工具从 FMEA 手册中检索相关内容。

【搜索词生成规则】
- 提取核心实体、术语、缩写作为搜索词
- 搜索词要精准简洁，不要输入完整长句
- 优先使用专业术语（如：DFMEA、PFMEA、严重度、发生度、探测度、RPN、AP、失效模式等）

【输出要求】
只输出一个 Tool Call，不要输出其他内容。
"""

rd_rag_system = SystemMessage(content=RD_RAG_PROMPT)


async def rd_rag_node(state: AgentState) -> AgentState:
    """研发 RAG 节点：LLM 生成搜索词 → 结构化检索（一次检索，双格式输出）"""
    messages = list(state["messages"])
    user_query = _extract_user_query(messages)

    print(f"\n[R&D Agent - RAG] 用户问题: {user_query[:80]}...")

    prompt = f"用户问题: {user_query}\n\n请生成搜索词并调用 fmea_rag_search 工具。"
    local_messages = [rd_rag_system, HumanMessage(content=prompt)]

    ai_msg = await llm.ainvoke(local_messages)

    # 提取 LLM 生成的搜索词
    search_query = user_query
    if ai_msg.tool_calls:
        print(f"[R&D Agent - RAG] Tool Call: {[c['name'] for c in ai_msg.tool_calls]}")
        for tc in ai_msg.tool_calls:
            if tc.get("name") == "fmea_rag_search":
                search_query = tc.get("args", {}).get("query", user_query)
                break

    print(f"[R&D Agent - RAG] 搜索词: {search_query[:80]}...")

    # 一次检索，两用
    rag_chunks = retrieve_structured(search_query, MILVUS_COLLECTION_FMEA)
    tool_result = chunks_to_text(rag_chunks)

    print(f"[R&D Agent - RAG] 检索结果: {len(rag_chunks)} chunks")

    return {
        "messages": messages,
        "sender": "rd_rag",
        "rag_result": tool_result,
        "rag_chunks": rag_chunks,
        "rag_is_relevant": False,
        "task_completed": False,
    }


# =============================================================================
# 相关性评估节点
# =============================================================================
GRADER_PROMPT = """你是一个信息相关性评判员。

判断检索到的内容是否与用户问题相关：
- 相关：内容与用户问题在同一领域，提供了相关信息
- 不相关：内容与问题无关，或检索结果表示"未检索到相关内容"或"未初始化"

输出 JSON：{"is_relevant": true/false}
"""

grader_system = SystemMessage(content=GRADER_PROMPT)


async def rd_grader_node(state: AgentState) -> AgentState:
    """评估 RAG 检索结果的相关性"""
    messages = list(state["messages"])
    rag_result = state.get("rag_result", "")
    rag_chunks = state.get("rag_chunks", [])
    user_query = _extract_user_query(messages)

    print(f"\n[R&D Agent - Grader] 评估中...")

    if not rag_result or "未检索到相关内容" in rag_result or "未初始化" in rag_result:
        print(f"[R&D Agent - Grader] 结果为空，标记不相关")
        return {
            "messages": messages,
            "sender": "rd_grader",
            "rag_result": rag_result,
            "rag_chunks": rag_chunks,
            "rag_is_relevant": False,
            "task_completed": False,
        }

    grade_prompt = f"""用户问题：{user_query}

检索到的内容：
{rag_result[:2000]}

请判断相关性，输出 JSON。"""

    local_messages = [grader_system, HumanMessage(content=grade_prompt)]
    resp = await llm_cheap.ainvoke(local_messages)
    raw = resp.content if hasattr(resp, "content") else str(resp)

    is_relevant = False
    try:
        match = re.search(r'\{.*?"is_relevant".*?\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            is_relevant = data.get("is_relevant", False)
    except Exception:
        pass

    print(f"[R&D Agent - Grader] 相关: {is_relevant}")
    return {
        "messages": messages,
        "sender": "rd_grader",
        "rag_result": rag_result,
        "rag_chunks": rag_chunks,
        "rag_is_relevant": is_relevant,
        "task_completed": False,
    }


# =============================================================================
# Writer（最终输出节点）—— JSON Mode + 结构化引用
# =============================================================================
RD_WRITER_PROMPT = """你是一个专业的 FMEA 技术顾问，也是 XF 模具公司的研发智能体。

【角色定位】
你是面向客户的技术专家，负责回答 FMEA 相关问题、生成 FMEA 分析报告。

【引用规则】
- 当提供检索材料时，请基于材料回答，并在文中使用 [N] 标记引用来源（如 [1]、[2]）
- 引用标记放在引用内容的句尾或段尾
- 如果检索材料与问题不相关或无材料提供，则基于自身知识回答，不使用引用标记

【核心能力】
1. FMEA 方法问答：解释 DFMEA/PFMEA 的七步法、S/O/D 评级标准等
2. 失效模式推理：根据用户描述的场景推理可能的失效模式、后果和原因
3. FMEA 报告生成：按标准格式生成 DFMEA 或 PFMEA 分析表
4. 风险评级建议：给出 S/O/D 评级的参考依据和建议值

【输出要求】
- 结构清晰，使用分段或表格组织内容
- 语言专业、准确
- 如果生成 FMEA 报告，使用表格格式呈现

【输出格式（重要）】
你必须输出一个严格的 JSON 对象：
{"answer": "你的回答正文（含 [N] 引用标记）", "citation_ids": [1, 2, 3]}
citation_ids 是你正文中实际引用的引用文献编号列表（按出现顺序，去重）。如果未引用任何材料，citation_ids 为空数组 []。
"""

rd_writer_system = SystemMessage(content=RD_WRITER_PROMPT)


async def rd_writer_node(state: AgentState) -> AgentState:
    """研发 Writer 节点：JSON Mode 输出，生成含 [id] 引用的回答"""
    messages = list(state["messages"])
    rag_chunks = state.get("rag_chunks", [])
    rag_is_relevant = state.get("rag_is_relevant", False)
    user_query = _extract_user_query(messages)

    print(f"\n[R&D Agent - Writer] 生成回答...")
    print(f"[R&D Agent - Writer] rag_is_relevant={rag_is_relevant}, chunks={len(rag_chunks)}")

    # 构建 citation_map 和引用文本
    citation_map = {}
    chunks_text = ""
    if rag_is_relevant and rag_chunks:
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
        content_block = f"\n\n--- 【FMEA 手册检索材料】 ---\n{chunks_text}\n"

    writer_input = f"""【用户问题】
{user_query}

{content_block}

请根据上述信息生成回答。如果无检索材料，基于自身知识回答，citation_ids 为空数组。
"""

    local_messages = [rd_writer_system, HumanMessage(content=writer_input)]

    # 不使用 response_format=json_object（该模型在此模式下输出不稳定），
    # 改为纯文本输出 + 正则/JSON 解析兜底
    final = ""
    async for chunk in llm.astream(local_messages):
        if chunk.content:
            final += chunk.content

    print(f"[R&D Agent - Writer] 原始输出长度: {len(final)} 字符")

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
            print(f"[R&D Agent - Writer] 解析成功, answer={len(answer_text)}字符, citations={citation_ids}")
        else:
            raise ValueError("no valid JSON found")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as e:
        print(f"[R&D Agent - Writer] JSON 解析失败: {e}，降级为原始文本")
        # 降级：尝试用正则提取
        match = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', final, re.DOTALL)
        if match:
            answer_text = match.group(1)
        else:
            answer_text = final
        # 尝试提取 citation_ids
        ids_match = re.search(r'"citation_ids"\s*:\s*\[([^\]]*)\]', final)
        if ids_match:
            citation_ids = [int(x.strip()) for x in ids_match.group(1).split(",") if x.strip().isdigit()]
        citation_ids = citation_ids or list(citation_map.keys())

    if not answer_text:
        answer_text = "抱歉，未能生成回答。"

    return {
        "messages": messages + [AIMessage(content=answer_text, name="rd_agent")],
        "sender": "rd_writer",
        "rag_result": state.get("rag_result", ""),
        "rag_chunks": rag_chunks,
        "rag_is_relevant": rag_is_relevant,
        "citation_map": citation_map,
        "citation_ids": citation_ids,
        "task_completed": True,
    }

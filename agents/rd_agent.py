"""
研发智能体（R&D Agent）
基于 FMEA 手册，提供失效模式分析、FMEA 方法问答、FMEA 报告生成等服务
"""
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


import asyncio

async def rd_rag_node(state: AgentState) -> AgentState:
    """研发 RAG 节点：直接使用用户输入检索，不额外调 LLM 生成搜索词"""
    messages = list(state["messages"])
    user_query = _extract_user_query(messages)

    print(f"\n[R&D Agent - RAG] 用户问题: {user_query[:80]}...")

    # 同步检索（embedding API + Milvus）丢到线程池，避免阻塞事件循环
    loop = asyncio.get_event_loop()
    rag_chunks = await loop.run_in_executor(
        None, retrieve_structured, user_query, MILVUS_COLLECTION_FMEA
    )
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
# Writer（最终输出节点）—— 直接输出 Markdown + 结构化引用
# =============================================================================

# —— 表格生成专用 Prompt ——
RD_TABLE_PROMPT = """你是先锋模具（XF 模具）公司的 FMEA 研发智能体，专注冷冲压模具领域。

【你的任务】
用户要求你生成一份 DFMEA/PFMEA 分析表。你必须**直接输出 Markdown 格式的完整分析报告**。

【输出结构 —— 严格按以下顺序组织】
1. **引言**（1-2 段）：简要说明本 DFMEA 分析的对象、目的和范围，结合先锋模具冷冲压模具的实际场景。
2. **DFMEA 分析表**：Markdown 表格，包含以下标准列：
   | 序号 | 过程/功能要求 | 潜在失效模式 | 失效后果 | 严重度(S) | 失效原因/机理 | 发生度(O) | 现行控制(探测) | 探测度(D) | RPN | 建议措施 |
   - 严重度S/发生度O/探测度D 评分 1~10，RPN = S×O×D
   - 结合冷冲压模具的典型工序（落料、冲孔、弯曲、拉伸、翻边、整形等）展开
   - 不少于 5 行失效模式，每行都要有具体的技术细节
3. **分析与建议**（1-2 段）：对表中高 RPN 项目进行总结分析，给出优先级建议。
4. **总结**（1 段）：概括本次 DFMEA 分析的核心结论和下一步行动建议，不要再列出参考资料。

【引用规则 —— 极其重要】
- 如果提供了 FMEA 手册检索材料，你**必须**在回答中充分引用它们
- **至少引用 3 个不同的来源**（如果提供了足够的材料），在表格和分析段落中都要使用 [N] 标记
- 每条失效模式的分析、S/O/D 评分依据都应尽可能标注对应手册来源
- 无检索材料则基于自身知识，不使用引用标记

【输出格式】
直接输出 Markdown 文本，**不要输出 JSON**。
"""

# —— 通用问答 Prompt ——
RD_WRITER_PROMPT = """你是先锋模具（XF 模具）公司的 FMEA 研发智能体，专注冷冲压模具领域。

【引用规则 —— 极其重要】
- 当提供检索材料时，你**必须充分引用**这些材料来支撑你的回答
- 在正文中使用 [N] 标记引用来源（如 [1]、[2]）
- **至少引用 3 个不同的来源**，将引用分布在回答的不同段落中，而不是只在开头引一次
- 如果检索材料与问题不相关或无材料，基于自身知识回答，不使用引用标记

【输出要求】
- 结构清晰，使用 markdown 标题分层（## 大标题，### 小标题）
- 每个要点都应有具体的技术细节和冷冲压模具实际场景举例
- 语言专业、准确，末尾给出总结性建议，**不要列出参考资料**（引用已在正文中标注）
- **不要输出 JSON 格式**，直接输出 markdown 文本
"""

rd_writer_system = SystemMessage(content=RD_WRITER_PROMPT)
rd_table_system = SystemMessage(content=RD_TABLE_PROMPT)


def _is_table_request(user_query: str) -> bool:
    """判断用户是否要求生成 DFMEA/PFMEA 表格"""
    q = user_query.lower()
    keywords = [
        "dfmea表", "pfmea表", "fmea表", "出个表", "生成一个表",
        "dfmea表格", "pfmea表格", "fmea表格", "绘制一个表",
        "出一份dfmea", "出一份pfmea", "给我一张表", "列个表",
        "fmea报告", "输出表格", "生成dfmea", "生成pfmea",
    ]
    return any(kw in q for kw in keywords)


def _extract_citation_ids(answer_text: str) -> list[int]:
    """从正文中提取 [N] 引用编号"""
    ids = set()
    for match in re.finditer(r'\[(\d+)\]', answer_text):
        ids.add(int(match.group(1)))
    return sorted(ids)


async def rd_writer_node(state: AgentState) -> AgentState:
    """研发 Writer 节点：直接输出 markdown，支持表格优先"""
    messages = list(state["messages"])
    rag_chunks = state.get("rag_chunks", [])
    user_query = _extract_user_query(messages)
    is_table_req = _is_table_request(user_query)

    print(f"\n[R&D Agent - Writer] 生成回答 (表格模式={is_table_req})...")
    print(f"[R&D Agent - Writer] chunks={len(rag_chunks)}")

    # 只要有检索结果就构建 citation_map 和 chunks_text，不依赖 grader 的判断
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

    # 选择 prompt
    has_material = bool(chunks_text)
    if is_table_req:
        system = rd_table_system
        content_block = f"\n\n--- 【FMEA 手册参考材料】 ---\n{chunks_text}\n" if chunks_text else ""
        material_hint = "必须在表格和分析中**充分使用 [N] 引用标记**，至少引用 3 个不同来源" if has_material else "基于冷冲压模具的典型工艺知识自行生成"
        user_msg = f"""【用户需求】
{user_query}

{content_block}

请根据上述需求和检索材料，生成一份完整的 DFMEA 分析报告。
重要：{material_hint}。"""
    else:
        system = rd_writer_system
        content_block = f"\n\n--- 【FMEA 手册检索材料】 ---\n{chunks_text}\n" if chunks_text else ""
        material_hint = "务必充分引用（至少 3 处 [N] 标记，分布在回答不同段落）" if has_material else "基于自身知识回答"
        user_msg = f"""【用户问题】
{user_query}

{content_block}

请根据上述信息回答。如果提供了检索材料，{material_hint}。"""

    local_messages = [system, HumanMessage(content=user_msg)]

    final = ""
    async for chunk in llm.astream(local_messages):
        if chunk.content:
            final += chunk.content

    print(f"[R&D Agent - Writer] 原始输出长度: {len(final)} 字符")

    # 从正文中提取引用，但只保留 citation_map 中真实存在的 ID
    answer_text = final.strip()
    raw_ids = _extract_citation_ids(answer_text)
    citation_ids = [cid for cid in raw_ids if cid in citation_map]

    if not answer_text:
        answer_text = "抱歉，未能生成回答。"

    return {
        "messages": messages + [AIMessage(content=answer_text, name="rd_agent")],
        "sender": "rd_writer",
        "rag_result": state.get("rag_result", ""),
        "rag_chunks": rag_chunks,
        "rag_is_relevant": bool(citation_ids),
        "citation_map": citation_map,
        "citation_ids": citation_ids,
        "task_completed": True,
    }

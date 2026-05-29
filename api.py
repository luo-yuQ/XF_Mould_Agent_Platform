"""
XF 模具智能体平台 - FastAPI 后端服务
支持流式 SSE + JSON Mode 增量解析 + 结构化引文
"""
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain_core.messages import HumanMessage, AIMessage
from state import AgentState
from graph import build_graph


app = FastAPI(title="XF 模具智能体平台 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# 数据模型
# =============================================================================
class ChatMessage(BaseModel):
    role: str
    content: str
    name: str = ""


class AskRequest(BaseModel):
    question: str
    chat_history: list[ChatMessage] = []


class Citation(BaseModel):
    id: int
    source: str
    chapter: str = ""
    section_title: str = ""
    heading_path: str = ""
    chunk_type: str = ""
    table_id: str = ""
    row_range: str = ""


class AskResponse(BaseModel):
    answer: str
    agent_type: str = ""
    intent: str = ""
    citations: list[Citation] = []


# =============================================================================
# 全局 Graph 实例
# =============================================================================
_agent_graph = None

def get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_graph()
    return _agent_graph


def _build_state(request: AskRequest) -> AgentState:
    """将请求转换为 AgentState"""
    lc_history: list = []
    for msg in request.chat_history:
        if msg.role == "user":
            lc_history.append(HumanMessage(content=msg.content, name=msg.name or "user"))
        else:
            lc_history.append(AIMessage(content=msg.content, name=msg.name or "agent"))

    history = lc_history + [HumanMessage(content=request.question, name="user")]
    return {
        "messages": history,
        "sender": "user",
        "next_agent": "",
        "intent": "",
        "rag_result": "",
        "rag_chunks": [],
        "citation_map": {},
        "citation_ids": [],
        "rag_is_relevant": False,
        "task_completed": False,
    }


# =============================================================================
# 节点名称 → 中文状态描述
# =============================================================================
NODE_STATUS = {
    "supervisor": "正在分析问题意图...",
    "rd_rag": "正在检索 FMEA 手册...",
    "rd_writer": "正在生成 FMEA 回答...",
    "qa_rag": "正在检索质量手册...",
    "qa_writer": "正在生成质量回答...",
    "chat_chat": "正在处理您的询问...",
}

WRITER_NODES = {"rd_writer", "qa_writer"}


def _sse_event(event: str, data: dict) -> str:
    """构造 SSE 格式字符串"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _build_citations(citation_ids: list, citation_map: dict) -> list[dict]:
    """将 citation_ids 映射为真实的 Citation 对象"""
    result = []
    seen = set()
    for cid in citation_ids:
        if cid in seen:
            continue
        seen.add(cid)
        meta = citation_map.get(cid, {})
        if meta:
            result.append({
                "id": cid,
                "source": meta.get("source", ""),
                "chapter": meta.get("chapter", ""),
                "section_title": meta.get("section_title", ""),
                "heading_path": meta.get("heading_path", ""),
                "chunk_type": meta.get("chunk_type", ""),
                "table_id": meta.get("table_id", ""),
                "row_range": meta.get("row_range", ""),
            })
    return result


# =============================================================================
# API 端点
# =============================================================================
@app.post("/api/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """接收问题，返回 Agent 回答（同步，兼容旧客户端）"""
    state = _build_state(request)

    try:
        agent = get_agent_graph()
        final_state = await agent.ainvoke(state, config={"recursion_limit": 12})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"执行出错: {e}")

    messages = final_state.get("messages", [])
    answer = messages[-1].content if messages else "抱歉，未能生成回答。"

    citation_map = final_state.get("citation_map", {})
    citation_ids = final_state.get("citation_ids", [])
    citations = _build_citations(citation_ids, citation_map)

    return AskResponse(
        answer=answer,
        agent_type=final_state.get("next_agent", ""),
        intent=final_state.get("intent", ""),
        citations=citations,
    )


@app.post("/api/ask/stream")
async def ask_stream(request: AskRequest):
    """SSE 流式端点：实时推送 Agent 思考过程、逐 token 回答（JSON Mode 增量解析）、结构化引文"""
    state = _build_state(request)
    agent = get_agent_graph()
    final_state = {}

    async def event_generator():
        try:
            is_writer_active = False
            stream_depth = 0

            async for event in agent.astream_events(state, version="v2", config={"recursion_limit": 12}):
                kind = event.get("event", "")
                name = event.get("name", "")

                # ---- 节点开始 ----
                if kind == "on_chain_start" and name in NODE_STATUS:
                    yield _sse_event("status", {
                        "node": name,
                        "message": NODE_STATUS[name],
                    })
                    if name in WRITER_NODES:
                        is_writer_active = True
                        stream_depth = 1

                elif kind == "on_chain_start" and is_writer_active:
                    stream_depth += 1

                # ---- LLM token 流 ----
                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if not chunk or not chunk.content:
                        continue

                    if is_writer_active:
                        yield _sse_event("token", {"content": chunk.content})

                # ---- 节点/chain 结束 ----
                elif kind == "on_chain_end":
                    if is_writer_active:
                        stream_depth -= 1
                        if stream_depth <= 0:
                            is_writer_active = False
                            stream_depth = 0

                    if isinstance(event.get("data", {}).get("output"), dict):
                        out = event["data"]["output"]
                        if "next_agent" in out or "task_completed" in out:
                            final_state.update(out)

            # ---- 流结束 → 发送 done 事件 ----
            agent_type = final_state.get("next_agent", "")
            intent = final_state.get("intent", "")
            citation_map = final_state.get("citation_map", {})
            citation_ids = final_state.get("citation_ids", [])
            citations = _build_citations(citation_ids, citation_map)

            messages = final_state.get("messages", [])
            full_answer = messages[-1].content if messages else "抱歉，未能生成回答。"

            yield _sse_event("done", {
                "agent_type": agent_type,
                "intent": intent,
                "full_answer": full_answer,
                "citations": citations,
            })

        except Exception as e:
            yield _sse_event("error", {"message": f"执行出错: {e}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}

"""
XF 模具智能体平台 - FastAPI 后端服务
支持流式 SSE + JSON Mode 增量解析 + 结构化引文
"""
import asyncio
import json
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Response, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from passlib.context import CryptContext
from jose import JWTError, jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config import DATABASE_URL, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_HOURS
from models.user import User
from models.chat import ChatSession, ChatMessage
import chat_memory

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from state import AgentState
from graph import build_graph
from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, LLM_MODEL, LLM_TEMPERATURE


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
class AskRequest(BaseModel):
    session_id: str
    question: str
    agent_override: str = ""  # ""=自动, "rd"=研发, "quality"=质量


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
# 数据库
# =============================================================================
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# 密码哈希
# =============================================================================
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# =============================================================================
# JWT 工具
# =============================================================================
def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


# =============================================================================
# 认证模型
# =============================================================================
class RegisterRequest(BaseModel):
    username: str
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(c.isalpha() for c in v):
            raise ValueError("密码必须包含字母")
        if not any(c.isdigit() for c in v):
            raise ValueError("密码必须包含数字")
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class UserInfo(BaseModel):
    id: int
    username: str
    email: str | None


# =============================================================================
# 会话 DTO
# =============================================================================
class SessionCreateRequest(BaseModel):
    title: str | None = None


class SessionUpdateRequest(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("标题不能为空")
        if len(v) > 200:
            raise ValueError("标题不能超过 200 字符")
        return v


class SessionItem(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    agent_type: str | None = None
    intent: str | None = None
    citations: list[dict] | None = None
    created_at: datetime


# =============================================================================
# 认证依赖
# =============================================================================
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """从 HttpOnly Cookie 提取并验证 JWT，返回当前用户或 None"""
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    username = payload.get("sub")
    if not username:
        return None
    user = db.query(User).filter(User.username == username).first()
    return user


# =============================================================================
# 认证端点
# =============================================================================
@app.post("/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """注册新用户"""
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    hashed = get_password_hash(req.password)
    user = User(username=req.username, password_hash=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username}


@app.post("/auth/login")
def login(req: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """登录并设置 HttpOnly Cookie"""
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token({"sub": user.username})
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        samesite="lax",
    )
    return {"username": user.username}


@app.post("/auth/logout")
def logout(response: Response):
    """清除 Cookie 注销"""
    response.delete_cookie(key="access_token", path="/")
    return {"message": "已注销"}


@app.get("/auth/me")
def get_me(response: Response, user=Depends(get_current_user)):
    """获取当前登录用户信息"""
    response.headers["Cache-Control"] = "no-store"
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return {"id": user.id, "username": user.username, "email": user.email}


# =============================================================================
# 全局 Graph 实例
# =============================================================================
_agent_graph = None

def get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_graph()
    return _agent_graph


def _build_state(
    history_msgs: list,
    question: str,
    summary_text: str | None = None,
    agent_override: str = "",
) -> AgentState:
    """将数据库中已持久化的历史消息转换为 AgentState，可选注入滚动摘要"""
    lc_history: list = []
    if summary_text:
        lc_history.append(SystemMessage(content=f"[对话历史摘要]\n{summary_text}"))
    for msg in history_msgs:
        if msg.role == "user":
            lc_history.append(HumanMessage(content=msg.content, name="user"))
        else:
            lc_history.append(AIMessage(content=msg.content, name="agent"))

    history = lc_history + [HumanMessage(content=question, name="user")]
    return {
        "messages": history,
        "sender": "user",
        "next_agent": "",
        "intent": "",
        "agent_override": agent_override,
        "rag_result": "",
        "rag_chunks": [],
        "citation_map": {},
        "citation_ids": [],
        "rag_is_relevant": False,
        "task_completed": False,
    }


def _get_owned_session(db: Session, session_id: str, user_id: int) -> ChatSession | None:
    """校验 session 归属当前用户"""
    return (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )


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
# 标题自动生成
# =============================================================================
TITLE_MAX_LEN = 30
TITLE_MIN_LEN = 4

# 中文/英文句末标点
_SENTENCE_END_PUNCT = r"[。.!?！？]"


def _truncate_question(question: str) -> str:
    """问题前 30 字符作为标题 fallback"""
    if not question or not question.strip():
        return "新对话"
    q = question.strip()
    if len(q) > TITLE_MAX_LEN:
        return q[:TITLE_MAX_LEN] + "..."
    return q


def _extract_title(answer: str, question: str) -> str:
    """
    从 AI 回答中提取首句作为会话标题。
    规则：跳过代码块 / # 标题 / > 引用 / 空行 → 取首个非噪音行 → 截到标点或 30 字符。
    若结果 < 4 字符或为空，回退到问题前 30 字符。
    """
    if not answer or not answer.strip():
        return _truncate_question(question)

    # 1) 移除代码块（```...```，含多行）
    import re
    cleaned = re.sub(r"```[\s\S]*?```", "", answer)

    # 2) 按段落分割（双换行）
    paragraphs = re.split(r"\n\s*\n", cleaned)

    first_line = ""
    for para in paragraphs:
        for raw in para.split("\n"):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#") or line.startswith(">"):
                continue
            first_line = line
            break
        if first_line:
            break

    if not first_line:
        return _truncate_question(question)

    # 3) 截到第一个标点
    m = re.search(_SENTENCE_END_PUNCT, first_line)
    if m:
        title = first_line[: m.start()].strip()
    else:
        title = first_line

    # 4) 截到 30 字符
    if len(title) > TITLE_MAX_LEN:
        title = title[:TITLE_MAX_LEN]

    # 5) 太短/空则 fallback
    if len(title.strip()) < TITLE_MIN_LEN:
        return _truncate_question(question)

    return title


# =============================================================================
# API 端点
# =============================================================================
def _require_user(user: User | None) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


# ---- 会话管理 ----
@app.get("/chat/sessions", response_model=list[SessionItem])
def list_sessions(
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户的全部会话（按更新时间倒序）"""
    user = _require_user(user)
    rows = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [
        SessionItem(
            id=s.id,
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in rows
    ]


@app.post("/chat/sessions", response_model=SessionItem)
def create_session(
    req: SessionCreateRequest,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新建一个空会话"""
    user = _require_user(user)
    import uuid
    sid = uuid.uuid4().hex
    session = ChatSession(
        id=sid,
        user_id=user.id,
        title=req.title or "新对话",
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionItem(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@app.patch("/chat/sessions/{session_id}", response_model=SessionItem)
def update_session(
    session_id: str,
    req: SessionUpdateRequest,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    更新会话标题。
    - 拒绝空/纯空白
    - 最大 200 字符
    - 不更新 updated_at（仅元数据修改，不影响排序）
    """
    user = _require_user(user)
    session = _get_owned_session(db, session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权限")
    session.title = req.title
    db.commit()
    db.refresh(session)
    return SessionItem(
        id=session.id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@app.delete("/chat/sessions/{session_id}")
def delete_session(
    session_id: str,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除会话（及其全部消息）"""
    user = _require_user(user)
    session = _get_owned_session(db, session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权限")
    db.delete(session)
    db.commit()
    return {"message": "已删除"}


@app.get("/chat/sessions/{session_id}/messages", response_model=list[MessageItem])
def get_messages(
    session_id: str,
    limit: int | None = None,
    before_id: int | None = None,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取会话的消息。
    - 不传参：返回该会话的全部消息（按时间正序，兼容老调用）
    - ?limit=N：分页，单次最多 N 条
    - ?limit=N&before_id=X：返回 id < X 的最近 N 条，再翻转为正序
    """
    user = _require_user(user)
    session = _get_owned_session(db, session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权限")

    if limit is not None and (limit <= 0 or limit > 100):
        raise HTTPException(status_code=400, detail="limit 必须在 1-100 之间")
    if before_id is not None and before_id <= 0:
        raise HTTPException(status_code=400, detail="before_id 必须为正整数")

    query = db.query(ChatMessage).filter(ChatMessage.session_id == session.id)

    if before_id is not None:
        query = query.filter(ChatMessage.id < before_id)

    if limit is not None:
        # 取最近 N 条（按 id 倒序），再翻转为正序返回
        msgs = query.order_by(ChatMessage.id.desc()).limit(limit).all()
        msgs.reverse()
    else:
        msgs = query.order_by(ChatMessage.created_at).all()

    return [
        MessageItem(
            id=m.id,
            role=m.role,
            content=m.content,
            agent_type=m.agent_type,
            intent=m.intent,
            citations=m.citations,
            created_at=m.created_at,
        )
        for m in msgs
    ]


# ---- 异步摘要更新 ----
async def _async_update_summary(session_id: str, current_msg_id: int):
    """后台异步：检查是否需要更新滚动摘要，需要时调用 LLM 生成"""
    db = SessionLocal()
    try:
        if not chat_memory.should_update_summary(db, session_id, current_msg_id):
            return

        old_summary, msgs_to_summarize, new_covered_id = chat_memory.build_summary_update_messages(
            db, session_id, current_msg_id,
        )
        if not msgs_to_summarize:
            return

        conversation_text = ""
        for m in msgs_to_summarize:
            role = "用户" if m.role == "user" else "助手"
            conversation_text += f"{role}: {m.content}\n\n"

        prompt_parts = [chat_memory.SUMMARY_PROMPT]
        if old_summary:
            prompt_parts.append(f"【已有摘要】\n{old_summary}")
        prompt_parts.append(f"【需要总结的新对话】\n{conversation_text}")

        full_prompt = "\n\n".join(prompt_parts)

        llm = ChatOpenAI(
            model=LLM_MODEL,
            temperature=0.1,
            api_key=DASHSCOPE_API_KEY,
            base_url=DASHSCOPE_BASE_URL,
            extra_body={"thinking": {"type": "disabled"}},
        )
        resp = await llm.ainvoke([HumanMessage(content=full_prompt)])
        new_summary = resp.content.strip()

        chat_memory.save_summary(db, session_id, new_summary, new_covered_id)
        print(f"[Summary] session={session_id[:8]}.. updated, covered_until={new_covered_id}")
    except Exception as e:
        print(f"[Summary] session={session_id[:8]}.. update failed: {e}")
    finally:
        db.close()


# ---- 提问 ----
@app.post("/api/ask/stream")
async def ask_stream(
    request: AskRequest,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SSE 流式端点：服务端按 session_id 自行加载最近历史，过程中消息全部入库"""
    user = _require_user(user)
    session = _get_owned_session(db, request.session_id, user.id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在或无权限")

    # 1. 清理孤儿 user 消息（距今超过 2 分钟且后续无 assistant）
    chat_memory.cleanup_orphan_user_messages(db, session.id)

    # 2. 插入当前 user 消息
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=request.question,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # 3. 取历史：summary + 未覆盖消息（冷启动时退化为原滑动窗口）
    summary_text, history_msgs, history_meta = chat_memory.get_history_with_summary(
        db, session.id, user_msg.id,
    )
    print(
        f"[Memory] session={session.id[:8]}.. "
        f"has_summary={history_meta['has_summary']} "
        f"fetched={history_meta['fetched']} "
        f"uncovered={history_meta['uncovered_count']} "
        f"total={history_meta['session_total']} "
        f"truncated={history_meta['truncated']}"
    )

    # 4. 构造 state 并跑 agent（标题自动生成移到 done 事件后，详见 event_generator）
    state = _build_state(history_msgs, request.question, summary_text, request.agent_override)
    agent = get_agent_graph()
    final_state: dict = {}

    # 流开始前拍下当前标题，event_generator 据此判断是否需要自动生成
    initial_title = session.title

    async def event_generator():
        full_answer = ""
        agent_type = ""
        intent = ""
        citations: list = []
        assistant_persisted = False
        new_title: str | None = None

        try:
            is_writer_active = False
            stream_depth = 0

            async for event in agent.astream_events(state, version="v2", config={"recursion_limit": 12}):
                kind = event.get("event", "")
                name = event.get("name", "")

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

                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if not chunk or not chunk.content:
                        continue
                    if is_writer_active:
                        yield _sse_event("token", {"content": chunk.content})

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

            agent_type = final_state.get("next_agent", "")
            intent = final_state.get("intent", "")
            citation_map = final_state.get("citation_map", {})
            citation_ids = final_state.get("citation_ids", [])
            citations = _build_citations(citation_ids, citation_map)

            messages = final_state.get("messages", [])
            full_answer = messages[-1].content if messages else "抱歉，未能生成回答。"

            # 标题自动生成：仅在标题还是默认 "新对话" 时覆盖
            if initial_title == "新对话":
                new_title = _extract_title(full_answer, request.question)

            yield _sse_event("done", {
                "agent_type": agent_type,
                "intent": intent,
                "full_answer": full_answer,
                "citations": citations,
                "title": new_title,  # None 表示没改动
            })

        except Exception as e:
            yield _sse_event("error", {"message": f"执行出错: {e}"})
            full_answer = f"[错误] {e}"

        # ---- 流结束后入库 assistant 消息（独立 db 会话） ----
        if not assistant_persisted:
            local_db = SessionLocal()
            try:
                asst = ChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=full_answer,
                    agent_type=agent_type,
                    intent=intent,
                    citations=citations or None,
                )
                local_db.add(asst)
                local_session = local_db.query(ChatSession).filter(ChatSession.id == session.id).first()
                if local_session:
                    if new_title:
                        local_session.title = new_title
                    local_session.updated_at = datetime.utcnow()
                local_db.commit()
                assistant_persisted = True
            except Exception:
                local_db.rollback()
            finally:
                local_db.close()

        # ---- 后台异步检查是否需要更新滚动摘要 ----
        asyncio.create_task(_async_update_summary(session.id, user_msg.id))

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

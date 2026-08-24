"""
XF 模具智能体平台 - FastAPI 后端服务
支持流式 SSE + JSON Mode 增量解析 + 结构化引文
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Query, Response, status, Request
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
from fmea_graph import build_fmea_graph
from audit_graph import build_audit_graph
from report_graph import build_report_graph
from graphs.sales_collaboration_graph import build_sales_collaboration_graph
from config import DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, LLM_MODEL, LLM_TEMPERATURE
from schemas.artifact_revision import (
    ArtifactListItem,
    ArtifactRevisionInput,
    ArtifactVersionOutput,
    ArtifactVersionsOutput,
)
from services.artifact_revision_service import (
    ArtifactRevisionError,
    get_artifact_version,
    list_artifact_versions,
    list_session_artifacts,
    revise_artifact_version,
)
from repositories.collaboration_repository import (
    create_collaboration_run,
    fail_collaboration_run,
    finalize_collaboration_run,
    get_owned_collaboration_run,
    list_collaboration_steps,
)
from schemas.sales_collaboration import (
    SalesProposalGenerateRequest,
    SalesProposalResponse,
    SalesProposalStepResponse,
)
from time_utils import utc_now

logger = logging.getLogger("uvicorn.error")

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


class FMEAGenerateRequest(BaseModel):
    session_id: str
    product: str
    process: str
    failure_phenomenon: str
    background: str = ""
    quality_case_id: str | None = None


class FMEAGenerateResponse(BaseModel):
    final_answer: str
    fmea_run_id: str | None = None
    artifact_id: str | None = None
    current_version_id: str | None = None
    current_version_no: int | None = None
    fmea_rows: list[dict] = []
    verify_result: dict = {}


class AuditCheckRequest(BaseModel):
    session_id: str
    audit_type: str
    content: str
    focus: str = ""
    background: str = ""
    quality_case_id: str | None = None


class AuditCheckResponse(BaseModel):
    final_answer: str
    audit_run_id: str | None = None
    findings: list[dict] = []
    verify_result: dict = {}
    references: list[dict] = []


class ReportSourceItem(BaseModel):
    id: str
    title: str
    summary: str
    keywords_json: list[str] = []
    artifact_type: str
    created_at: datetime
    updated_at: datetime


class ReportSourcesResponse(BaseModel):
    fmea_runs: list[ReportSourceItem] = []
    audit_runs: list[ReportSourceItem] = []


class ReportGenerateRequest(BaseModel):
    report_type: str = "quality_issue_report"
    title: str | None = None
    fmea_run_id: str | None = None
    audit_run_id: str | None = None
    extra_background: str | None = None
    include_chat_summary: bool = False
    quality_case_id: str | None = None


class ReportGenerateResponse(BaseModel):
    final_markdown: str
    report_run_id: str | None = None
    verify_result: dict = {}
    references: list[dict] = []
    manual_check_items: list[str] = []
    source_match_result: dict = {}


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


def _artifact_revision_http_error(exc: ArtifactRevisionError) -> HTTPException:
    status_by_code = {
        "artifact_not_found": status.HTTP_404_NOT_FOUND,
        "invalid_base_version": status.HTTP_404_NOT_FOUND,
        "feature_reserved": status.HTTP_501_NOT_IMPLEMENTED,
        "version_conflict": status.HTTP_409_CONFLICT,
        "revision_verify_failed": status.HTTP_422_UNPROCESSABLE_ENTITY,
    }
    return HTTPException(
        status_code=status_by_code.get(exc.code, status.HTTP_400_BAD_REQUEST),
        detail={"code": exc.code, "message": exc.message},
    )


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
    expire = utc_now() + (expires_delta or timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS))
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
_fmea_graph = None
_audit_graph = None
_report_graph = None
_sales_collaboration_graph = None

def get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_graph()
    return _agent_graph


def get_fmea_graph():
    global _fmea_graph
    if _fmea_graph is None:
        _fmea_graph = build_fmea_graph()
    return _fmea_graph


def get_audit_graph():
    global _audit_graph
    if _audit_graph is None:
        _audit_graph = build_audit_graph()
    return _audit_graph


def get_report_graph():
    global _report_graph
    if _report_graph is None:
        _report_graph = build_report_graph()
    return _report_graph


def get_sales_collaboration_graph():
    global _sales_collaboration_graph
    if _sales_collaboration_graph is None:
        _sales_collaboration_graph = build_sales_collaboration_graph()
    return _sales_collaboration_graph


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


def _sales_proposal_summary(final_report: str | None, limit: int = 200) -> str:
    """从 Markdown 报告中提取简短摘要。"""
    lines = [
        line.strip()
        for line in str(final_report or "").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    summary = " ".join(lines)
    return summary[:limit] + ("..." if len(summary) > limit else "")


def _sales_proposal_response(run) -> SalesProposalResponse:
    return SalesProposalResponse(
        run_id=run.run_id,
        status=run.status,
        title="售前协作方案",
        summary=_sales_proposal_summary(run.final_report),
        user_request=run.user_request,
        customer_context=run.customer_context_json or {},
        final_report=run.final_report or "",
        execution_plan=run.execution_plan_json or [],
        review_result=run.review_result_json or {},
        citations=run.citations_json or [],
        error=run.error,
        metrics=run.metrics_json,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _sales_step_response(step) -> SalesProposalStepResponse:
    return SalesProposalStepResponse(
        step_id=step.step_id,
        step_name=step.step_name,
        agent=step.agent,
        status=step.status,
        input_json=step.input_json,
        output_json=step.output_json,
        error=step.error,
        started_at=step.started_at,
        finished_at=step.finished_at,
        duration_ms=step.duration_ms,
        model_info_json=step.model_info_json,
        metrics_json=step.metrics_json,
    )


def _sales_generation_error(run_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={
            "code": "sales_collaboration_failed",
            "message": "售前协作方案生成失败",
            "run_id": run_id,
        },
    )


# ---- 销售协作方案 ----
@app.post(
    "/sales/proposals/generate",
    response_model=SalesProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_sales_proposal(
    request: SalesProposalGenerateRequest,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """执行销售协作 graph，并持久化 run 和全部 steps。"""
    user = _require_user(user)
    logger.info(
        "sales_collaboration.request.started user_id=%s session_id=%s",
        user.id,
        request.session_id,
    )
    user_request = request.user_request.strip()
    if not user_request:
        logger.warning(
            "sales_collaboration.request.failed user_id=%s session_id=%s "
            "reason=empty_request",
            user.id,
            request.session_id,
        )
        raise HTTPException(status_code=400, detail="user_request 不能为空")

    if request.session_id and not _get_owned_session(db, request.session_id, user.id):
        logger.warning(
            "sales_collaboration.request.failed user_id=%s session_id=%s "
            "reason=session_not_found",
            user.id,
            request.session_id,
        )
        raise HTTPException(status_code=404, detail="会话不存在或无权限")

    run_id = f"sales_{uuid.uuid4().hex}"
    run = create_collaboration_run(
        db,
        run_id=run_id,
        user_id=user.id,
        session_id=request.session_id,
        user_request=user_request,
        customer_context=request.customer_context,
    )
    logger.info(
        "sales_collaboration.request.run_created run_id=%s user_id=%s "
        "session_id=%s",
        run_id,
        user.id,
        request.session_id,
    )
    state = {
        "request_id": run_id,
        "user_id": user.id,
        "session_id": request.session_id,
        "user_request": user_request,
        "customer_context": request.customer_context,
        "status": "running",
        "error": None,
    }

    try:
        final_state = await get_sales_collaboration_graph().ainvoke(
            state,
            config={"recursion_limit": 20},
        )
    except Exception:
        logger.exception(
            "sales_collaboration.request.failed run_id=%s user_id=%s "
            "session_id=%s phase=graph",
            run_id,
            user.id,
            request.session_id,
        )
        db.rollback()
        fail_collaboration_run(
            db,
            run=run,
            error="Sales collaboration graph execution failed.",
        )
        raise _sales_generation_error(run_id)

    try:
        run = finalize_collaboration_run(db, run=run, final_state=final_state)
    except Exception:
        logger.exception(
            "sales_collaboration.request.failed run_id=%s user_id=%s "
            "session_id=%s phase=persist",
            run_id,
            user.id,
            request.session_id,
        )
        db.rollback()
        fail_collaboration_run(
            db,
            run=run,
            error="Sales collaboration persistence failed.",
            final_state=final_state,
        )
        raise _sales_generation_error(run_id)

    if run.status != "completed":
        logger.error(
            "sales_collaboration.request.failed run_id=%s user_id=%s "
            "session_id=%s status=%s error=%s",
            run_id,
            user.id,
            request.session_id,
            run.status,
            str(run.error or "")[:300],
        )
        raise _sales_generation_error(run_id)
    logger.info(
        "sales_collaboration.request.completed run_id=%s user_id=%s "
        "session_id=%s status=%s",
        run_id,
        user.id,
        request.session_id,
        run.status,
    )
    return _sales_proposal_response(run)


@app.get(
    "/sales/proposals/{run_id}",
    response_model=SalesProposalResponse,
)
def get_sales_proposal(
    run_id: str,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询当前用户拥有的销售协作 run。"""
    user = _require_user(user)
    run = get_owned_collaboration_run(db, run_id=run_id, user_id=user.id)
    if not run:
        raise HTTPException(status_code=404, detail="售前协作任务不存在或无权限")
    return _sales_proposal_response(run)


@app.get(
    "/sales/proposals/{run_id}/steps",
    response_model=list[SalesProposalStepResponse],
)
def get_sales_proposal_steps(
    run_id: str,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询当前用户拥有的销售协作步骤。"""
    user = _require_user(user)
    run = get_owned_collaboration_run(db, run_id=run_id, user_id=user.id)
    if not run:
        raise HTTPException(status_code=404, detail="售前协作任务不存在或无权限")
    return [
        _sales_step_response(step)
        for step in list_collaboration_steps(db, run_id=run.run_id)
    ]


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


# ---- FMEA 生成 ----
@app.post("/quality/fmea/generate", response_model=FMEAGenerateResponse)
async def generate_fmea(
    request: FMEAGenerateRequest,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """独立 FMEA 生成接口：不写 ChatMessage，不触发 Memory。"""
    user = _require_user(user)
    logger.info(
        "fmea.request.started user_id=%s session_id=%s artifact_type=fmea",
        user.id,
        request.session_id,
    )
    session = _get_owned_session(db, request.session_id, user.id)
    if not session:
        logger.warning(
            "fmea.request.failed user_id=%s session_id=%s reason=session_not_found",
            user.id,
            request.session_id,
        )
        raise HTTPException(status_code=404, detail="会话不存在或无权限")

    state: AgentState = {
        "messages": [
            HumanMessage(
                content=(
                    f"产品：{request.product}\n"
                    f"工序：{request.process}\n"
                    f"问题现象：{request.failure_phenomenon}\n"
                    f"背景：{request.background}"
                ),
                name="user",
            )
        ],
        "sender": "user",
        "next_agent": "fmea",
        "intent": "fmea_generate",
        "agent_override": "",
        "rag_result": "",
        "rag_chunks": [],
        "citation_map": {},
        "citation_ids": [],
        "rag_is_relevant": False,
        "task_completed": False,
        "fmea_input_raw": {
            "product": request.product,
            "process": request.process,
            "failure_phenomenon": request.failure_phenomenon,
            "background": request.background,
            "quality_case_id": request.quality_case_id,
        },
        "fmea_user_id": user.id,
        "fmea_session_id": session.id,
        "fmea_db_session": db,
    }

    try:
        final_state = await get_fmea_graph().ainvoke(state, config={"recursion_limit": 20})
    except Exception as exc:
        logger.exception(
            "fmea.request.failed user_id=%s session_id=%s",
            user.id,
            session.id,
        )
        raise HTTPException(status_code=500, detail=f"FMEA 生成失败: {exc}") from exc

    messages = final_state.get("messages", [])
    final_answer = messages[-1].content if messages else final_state.get("fmea_markdown", "")
    if final_state.get("fmea_error"):
        logger.error(
            "fmea.request.failed user_id=%s session_id=%s error=%s",
            user.id,
            session.id,
            str(final_state.get("fmea_error"))[:300],
        )

    response = FMEAGenerateResponse(
        final_answer=final_answer,
        fmea_run_id=final_state.get("fmea_run_id"),
        artifact_id=final_state.get("fmea_run_id"),
        current_version_id=final_state.get("fmea_current_version_id"),
        current_version_no=final_state.get("fmea_current_version_no"),
        fmea_rows=final_state.get("fmea_rows", []),
        verify_result=final_state.get("fmea_verification", {}),
    )
    logger.info(
        "fmea.request.completed run_id=%s user_id=%s session_id=%s",
        response.fmea_run_id,
        user.id,
        session.id,
    )
    return response


# ---- 业务产物版本与追改 ----
@app.get(
    "/quality/sessions/{session_id}/artifacts",
    response_model=list[ArtifactListItem],
)
def get_session_artifacts(
    session_id: str,
    artifact_type: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _require_user(user)
    try:
        return list_session_artifacts(
            db,
            session_id=session_id,
            artifact_type=artifact_type,
            limit=limit,
            offset=offset,
            created_by=user.id,
        )
    except ArtifactRevisionError as exc:
        raise _artifact_revision_http_error(exc) from exc


@app.post(
    "/quality/artifacts/{artifact_id}/revise",
    response_model=ArtifactVersionOutput,
)
async def revise_artifact(
    artifact_id: str,
    request: ArtifactRevisionInput,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _require_user(user)
    try:
        return await revise_artifact_version(
            db,
            artifact_id=artifact_id,
            artifact_type=request.artifact_type,
            base_version_id=request.base_version_id,
            revision_instruction=request.revision_instruction,
            created_by=user.id,
        )
    except ArtifactRevisionError as exc:
        raise _artifact_revision_http_error(exc) from exc


@app.get(
    "/quality/artifacts/{artifact_id}/versions",
    response_model=ArtifactVersionsOutput,
)
def get_artifact_versions(
    artifact_id: str,
    artifact_type: str | None = None,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _require_user(user)
    try:
        return list_artifact_versions(
            db,
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            created_by=user.id,
        )
    except ArtifactRevisionError as exc:
        raise _artifact_revision_http_error(exc) from exc


@app.get(
    "/quality/artifacts/{artifact_id}/versions/{version_id}",
    response_model=ArtifactVersionOutput,
)
def get_artifact_version_detail(
    artifact_id: str,
    version_id: str,
    artifact_type: str | None = None,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _require_user(user)
    try:
        return get_artifact_version(
            db,
            artifact_id=artifact_id,
            version_id=version_id,
            artifact_type=artifact_type,
            created_by=user.id,
        )
    except ArtifactRevisionError as exc:
        raise _artifact_revision_http_error(exc) from exc


# ---- 提问 ----
@app.post("/quality/audit/check", response_model=AuditCheckResponse)
async def check_audit(
    request: AuditCheckRequest,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """独立审核检查接口：不写 ChatMessage，不触发 Memory。"""
    user = _require_user(user)
    logger.info(
        "audit.request.started user_id=%s session_id=%s artifact_type=audit",
        user.id,
        request.session_id,
    )
    session = _get_owned_session(db, request.session_id, user.id)
    if not session:
        logger.warning(
            "audit.request.failed user_id=%s session_id=%s reason=session_not_found",
            user.id,
            request.session_id,
        )
        raise HTTPException(status_code=404, detail="会话不存在或无权限")

    state: AgentState = {
        "messages": [
            HumanMessage(
                content=(
                    f"audit_type: {request.audit_type}\n"
                    f"content: {request.content}\n"
                    f"focus: {request.focus}\n"
                    f"background: {request.background}"
                ),
                name="user",
            )
        ],
        "sender": "user",
        "next_agent": "audit",
        "intent": "audit_check",
        "agent_override": "",
        "rag_result": "",
        "rag_chunks": [],
        "citation_map": {},
        "citation_ids": [],
        "rag_is_relevant": False,
        "task_completed": False,
        "audit_input_raw": {
            "audit_type": request.audit_type,
            "content": request.content,
            "focus": request.focus,
            "background": request.background,
            "quality_case_id": request.quality_case_id,
        },
        "audit_user_id": user.id,
        "audit_session_id": session.id,
        "audit_db_session": db,
    }

    try:
        final_state = await get_audit_graph().ainvoke(state, config={"recursion_limit": 20})
    except Exception as exc:
        logger.exception(
            "audit.request.failed user_id=%s session_id=%s",
            user.id,
            session.id,
        )
        raise HTTPException(status_code=500, detail=f"审核检查失败: {exc}") from exc

    messages = final_state.get("messages", [])
    final_answer = messages[-1].content if messages else final_state.get("audit_markdown", "")
    if final_state.get("audit_error"):
        logger.error(
            "audit.request.failed user_id=%s session_id=%s error=%s",
            user.id,
            session.id,
            str(final_state.get("audit_error"))[:300],
        )
    citation_map = final_state.get("citation_map", {})
    references = [
        {"id": key, **value}
        for key, value in citation_map.items()
        if isinstance(value, dict)
    ]

    response = AuditCheckResponse(
        final_answer=final_answer,
        audit_run_id=final_state.get("audit_run_id"),
        findings=final_state.get("audit_findings", []),
        verify_result=final_state.get("audit_verification", {}),
        references=references,
    )
    logger.info(
        "audit.request.completed run_id=%s user_id=%s session_id=%s",
        response.audit_run_id,
        user.id,
        session.id,
    )
    return response


def _trim_text(value: str | None, limit: int = 120) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _fmea_source_item(run) -> ReportSourceItem:
    rows = []
    if isinstance(run.output_json, dict):
        rows = run.output_json.get("rows", []) or []
    fallback_title = f"{run.product} - {run.process}"
    summary_parts = [
        f"问题现象：{run.failure_phenomenon}",
        f"FMEA行数：{len(rows)}",
    ]
    fallback_summary = "；".join(summary_parts)
    created_at = run.created_at or utc_now()
    keywords = run.keywords_json if isinstance(run.keywords_json, list) else []
    return ReportSourceItem(
        id=str(run.id),
        title=_trim_text(run.title, 80) or _trim_text(fallback_title, 80),
        summary=_trim_text(run.summary, 180) or _trim_text(fallback_summary, 180),
        keywords_json=keywords,
        artifact_type=run.artifact_type or "fmea_run",
        created_at=created_at,
        updated_at=run.updated_at or created_at,
    )


def _audit_source_item(run) -> ReportSourceItem:
    findings = []
    if isinstance(run.findings_json, dict):
        findings = run.findings_json.get("findings", []) or []
    first_issue = ""
    if findings and isinstance(findings[0], dict):
        first_issue = str(findings[0].get("issue") or "")
    fallback_title_parts = [run.audit_type]
    if run.focus:
        fallback_title_parts.append(_trim_text(run.focus, 40))
    summary_parts = [
        f"审核发现数：{len(findings)}",
        f"首条问题：{first_issue}" if first_issue else _trim_text(run.content_text, 80),
    ]
    fallback_title = " - ".join(fallback_title_parts)
    fallback_summary = "；".join(part for part in summary_parts if part)
    created_at = run.created_at or utc_now()
    keywords = run.keywords_json if isinstance(run.keywords_json, list) else []
    return ReportSourceItem(
        id=str(run.id),
        title=_trim_text(run.title, 80) or _trim_text(fallback_title, 80),
        summary=_trim_text(run.summary, 180) or _trim_text(fallback_summary, 180),
        keywords_json=keywords,
        artifact_type=run.artifact_type or "audit_run",
        created_at=created_at,
        updated_at=run.updated_at or created_at,
    )


def _coerce_optional_run_id(value: str | None, field_name: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是数字 ID") from exc


def _ensure_owned_report_source_runs(
    db: Session,
    user_id: int,
    fmea_run_id: str | None,
    audit_run_id: str | None,
) -> None:
    from models.audit import AuditRun
    from models.fmea import FMEARun

    fmea_id = _coerce_optional_run_id(fmea_run_id, "fmea_run_id")
    audit_id = _coerce_optional_run_id(audit_run_id, "audit_run_id")

    if fmea_id is not None:
        exists = (
            db.query(FMEARun.id)
            .filter(FMEARun.id == fmea_id, FMEARun.user_id == user_id)
            .first()
        )
        if not exists:
            raise HTTPException(status_code=404, detail="fmea_run_id 不存在或无权限")

    if audit_id is not None:
        exists = (
            db.query(AuditRun.id)
            .filter(AuditRun.id == audit_id, AuditRun.user_id == user_id)
            .first()
        )
        if not exists:
            raise HTTPException(status_code=404, detail="audit_run_id 不存在或无权限")


@app.get("/quality/report/sources", response_model=ReportSourcesResponse)
def list_report_sources(
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出当前用户可选择的 FMEA / Audit 运行结果，不按 session_id 强过滤。"""
    from models.audit import AuditRun
    from models.fmea import FMEARun

    user = _require_user(user)
    fmea_runs = (
        db.query(FMEARun)
        .filter(FMEARun.user_id == user.id)
        .order_by(FMEARun.created_at.desc())
        .limit(20)
        .all()
    )
    audit_runs = (
        db.query(AuditRun)
        .filter(AuditRun.user_id == user.id)
        .order_by(AuditRun.created_at.desc())
        .limit(20)
        .all()
    )

    return ReportSourcesResponse(
        fmea_runs=[_fmea_source_item(run) for run in fmea_runs],
        audit_runs=[_audit_source_item(run) for run in audit_runs],
    )


@app.post("/quality/report/generate", response_model=ReportGenerateResponse)
async def generate_report(
    request: ReportGenerateRequest,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """根据用户明确选择的 FMEA / Audit run_id 生成质量问题分析报告。"""
    user = _require_user(user)
    logger.info(
        "report.request.started user_id=%s artifact_type=report "
        "fmea_run_id=%s audit_run_id=%s",
        user.id,
        request.fmea_run_id,
        request.audit_run_id,
    )
    if request.report_type != "quality_issue_report":
        logger.warning(
            "report.request.failed user_id=%s reason=unsupported_report_type",
            user.id,
        )
        raise HTTPException(status_code=400, detail="report_type 当前只支持 quality_issue_report")

    try:
        _ensure_owned_report_source_runs(
            db=db,
            user_id=user.id,
            fmea_run_id=request.fmea_run_id,
            audit_run_id=request.audit_run_id,
        )
    except HTTPException:
        logger.warning(
            "report.request.failed user_id=%s fmea_run_id=%s audit_run_id=%s "
            "reason=source_not_found",
            user.id,
            request.fmea_run_id,
            request.audit_run_id,
        )
        raise

    state: AgentState = {
        "messages": [],
        "sender": "user",
        "next_agent": "report",
        "intent": "quality_issue_report",
        "agent_override": "",
        "rag_result": "",
        "rag_chunks": [],
        "citation_map": {},
        "citation_ids": [],
        "rag_is_relevant": False,
        "task_completed": False,
        "report_input_raw": {
            "report_type": request.report_type,
            "title": request.title,
            "fmea_run_id": request.fmea_run_id,
            "audit_run_id": request.audit_run_id,
            "extra_background": request.extra_background,
            "include_chat_summary": request.include_chat_summary,
            "quality_case_id": request.quality_case_id,
        },
        "report_user_id": user.id,
        "report_db_session": db,
        "report_include_rag": True,
    }

    try:
        final_state = await get_report_graph().ainvoke(state, config={"recursion_limit": 20})
    except HTTPException:
        logger.exception(
            "report.request.failed user_id=%s fmea_run_id=%s audit_run_id=%s",
            user.id,
            request.fmea_run_id,
            request.audit_run_id,
        )
        raise
    except Exception as exc:
        logger.exception(
            "report.request.failed user_id=%s fmea_run_id=%s audit_run_id=%s",
            user.id,
            request.fmea_run_id,
            request.audit_run_id,
        )
        raise HTTPException(status_code=500, detail=f"报告生成失败：{exc}") from exc

    if final_state.get("report_error"):
        logger.error(
            "report.request.failed user_id=%s fmea_run_id=%s audit_run_id=%s "
            "error=%s",
            user.id,
            request.fmea_run_id,
            request.audit_run_id,
            str(final_state.get("report_error"))[:300],
        )
        raise HTTPException(status_code=500, detail=final_state.get("report_error"))

    report_result = final_state.get("report_result", {}) or {}
    response = ReportGenerateResponse(
        final_markdown=report_result.get("final_markdown") or final_state.get("report_markdown", ""),
        report_run_id=final_state.get("report_run_id"),
        verify_result=report_result.get("verify_result") or final_state.get("report_verify_result", {}),
        references=report_result.get("references", []),
        manual_check_items=report_result.get("manual_check_items", []),
        source_match_result=report_result.get("source_match_result", {}),
    )
    logger.info(
        "report.request.completed report_run_id=%s user_id=%s "
        "fmea_run_id=%s audit_run_id=%s",
        response.report_run_id,
        user.id,
        request.fmea_run_id,
        request.audit_run_id,
    )
    return response


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
                    local_session.updated_at = utc_now()
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


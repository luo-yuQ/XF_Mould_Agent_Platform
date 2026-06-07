"""
聊天记忆管理：滑动窗口 + 孤儿清理 + 滚动摘要。

Phase 1: 滑动窗口 + 孤儿清理
Phase 2: 滚动摘要（summary + 未覆盖消息 + current query）

不在本模块：
  - LangChain 状态构造（保留在 api.py 的 _build_state 中）
  - DB schema 定义（在 models/chat.py）
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from models.chat import ChatMessage, ChatSessionSummary
from time_utils import utc_now


HISTORY_WINDOW = 20
SUMMARY_TRIGGER = 40
ORPHAN_THRESHOLD = timedelta(minutes=2)

SUMMARY_PROMPT = """请将以下对话历史压缩为一段简洁摘要。

要求：
1. 优先保留与模具、FMEA、VDA6.4、质量管理、RAG系统、Agent系统操作相关的信息。
2. 对用户的关键意图、已确认的方案、技术参数、接口设计、数据库字段、流程决策要保留。
3. 如果出现与上述领域无关的闲聊或临时问题，只做简要概括，不要展开。
4. 不要编造原文没有的信息。
5. 摘要控制在 300～500 字。"""


def cleanup_orphan_user_messages(db: Session, session_id: str) -> int:
    """
    清理孤儿 user 消息。

    孤儿定义：同 session 内，某条 user 消息之后到下一条 user 出现前
    （若没有下一条 user 则到末尾），没有任何 assistant 消息。

    仅删除 created_at 距今超过 ORPHAN_THRESHOLD 的孤儿，避免误删
    "AI 还在流式生成但 assistant 消息尚未入库"的最新 user 消息。

    Returns:
        删除的消息数。
    """
    if not session_id:
        return 0

    threshold_time = utc_now() - ORPHAN_THRESHOLD

    msgs = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
        .all()
    )

    orphans: list[ChatMessage] = []
    n = len(msgs)
    for i, msg in enumerate(msgs):
        if msg.role != "user":
            continue
        if msg.created_at >= threshold_time:
            continue

        has_assistant = False
        for j in range(i + 1, n):
            if msgs[j].role == "user":
                break
            if msgs[j].role == "assistant":
                has_assistant = True
                break

        if not has_assistant:
            orphans.append(msg)

    for orphan in orphans:
        db.delete(orphan)

    if orphans:
        db.commit()

    return len(orphans)


def get_summary(db: Session, session_id: str) -> ChatSessionSummary | None:
    """获取会话的滚动摘要记录"""
    return (
        db.query(ChatSessionSummary)
        .filter(ChatSessionSummary.session_id == session_id)
        .first()
    )


def get_history_with_summary(
    db: Session,
    session_id: str,
    current_msg_id: int,
) -> tuple[str | None, list[ChatMessage], dict]:
    """
    取历史消息，优先使用 summary + 未覆盖消息。

    - 若有 summary：返回 (summary_text, id > covered_until_msg_id 的最近20条, meta)
    - 若无 summary：返回 (None, 最近20条历史, meta)，退化为原滑动窗口

    Args:
        db: SQLAlchemy Session
        session_id: 会话 ID
        current_msg_id: 当前 user 消息的 id（不会被包含在返回中）

    Returns:
        (summary_text, msgs, meta)：
          - summary_text: 摘要文本，无摘要时为 None
          - msgs: 历史消息列表（按 id 升序）
          - meta: {"fetched": int, "session_total": int, "truncated": bool,
                   "uncovered_count": int, "has_summary": bool}

    Raises:
        ValueError: current_msg_id 为空时
    """
    if not current_msg_id:
        raise ValueError("current_msg_id 不能为空")
    if not session_id:
        return None, [], {"fetched": 0, "session_total": 0, "truncated": False,
                          "uncovered_count": 0, "has_summary": False}

    # 历史消息总数（不含 current_msg_id）
    session_total = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == session_id,
            ChatMessage.id < current_msg_id,
        )
        .count()
    )

    summary_record = get_summary(db, session_id)
    summary_text = None
    uncovered_count = 0

    if summary_record:
        summary_text = summary_record.summary
        # 取 id > covered_until_msg_id 的最近 HISTORY_WINDOW 条
        msgs = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.id < current_msg_id,
                ChatMessage.id > summary_record.covered_until_msg_id,
            )
            .order_by(ChatMessage.id.desc())
            .limit(HISTORY_WINDOW)
            .all()
        )
        msgs.reverse()
        uncovered_count = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.id < current_msg_id,
                ChatMessage.id > summary_record.covered_until_msg_id,
            )
            .count()
        )
    else:
        # 冷启动：无 summary，走原滑动窗口
        msgs = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.id < current_msg_id,
            )
            .order_by(ChatMessage.id.desc())
            .limit(HISTORY_WINDOW)
            .all()
        )
        msgs.reverse()

    fetched = len(msgs)
    truncated = session_total > fetched if not summary_record else uncovered_count > HISTORY_WINDOW

    return summary_text, msgs, {
        "fetched": fetched,
        "session_total": session_total,
        "truncated": truncated,
        "uncovered_count": uncovered_count,
        "has_summary": summary_record is not None,
    }


def should_update_summary(db: Session, session_id: str, current_msg_id: int) -> bool:
    """判断是否需要触发摘要更新（未覆盖消息 >= SUMMARY_TRIGGER）"""
    summary_record = get_summary(db, session_id)
    if summary_record:
        uncovered = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.id < current_msg_id,
                ChatMessage.id > summary_record.covered_until_msg_id,
            )
            .count()
        )
    else:
        # 无 summary 时，历史消息总数 >= SUMMARY_TRIGGER 才触发首次摘要
        uncovered = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.id < current_msg_id,
            )
            .count()
        )
    return uncovered >= SUMMARY_TRIGGER


def build_summary_update_messages(
    db: Session,
    session_id: str,
    current_msg_id: int,
) -> tuple[str | None, list[ChatMessage], int]:
    """
    构建摘要更新所需的数据。

    返回 (old_summary, messages_to_summarize, new_covered_until_msg_id)：
      - old_summary: 旧摘要文本（首次为 None）
      - messages_to_summarize: 需要被总结的最老 20 条消息
      - new_covered_until_msg_id: 更新后的锚点 id
    """
    summary_record = get_summary(db, session_id)

    if summary_record:
        old_summary = summary_record.summary
        # 取 id > covered_until_msg_id 且 < current_msg_id 的最老 20 条
        msgs_to_summarize = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.id < current_msg_id,
                ChatMessage.id > summary_record.covered_until_msg_id,
            )
            .order_by(ChatMessage.id.asc())
            .limit(HISTORY_WINDOW)
            .all()
        )
    else:
        old_summary = None
        # 首次：取最老 20 条
        msgs_to_summarize = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session_id,
                ChatMessage.id < current_msg_id,
            )
            .order_by(ChatMessage.id.asc())
            .limit(HISTORY_WINDOW)
            .all()
        )

    if not msgs_to_summarize:
        return old_summary, [], 0

    new_covered_until_msg_id = msgs_to_summarize[-1].id
    return old_summary, msgs_to_summarize, new_covered_until_msg_id


def save_summary(
    db: Session,
    session_id: str,
    summary_text: str,
    covered_until_msg_id: int,
) -> None:
    """保存或更新摘要记录"""
    record = (
        db.query(ChatSessionSummary)
        .filter(ChatSessionSummary.session_id == session_id)
        .first()
    )
    if record:
        record.summary = summary_text
        record.covered_until_msg_id = covered_until_msg_id
        record.updated_at = utc_now()
    else:
        record = ChatSessionSummary(
            session_id=session_id,
            summary=summary_text,
            covered_until_msg_id=covered_until_msg_id,
        )
        db.add(record)
    db.commit()

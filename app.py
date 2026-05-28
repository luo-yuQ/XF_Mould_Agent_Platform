"""
XF 模具智能体平台 - Streamlit Web 界面
"""
import os
import sys
import json
import requests
from datetime import datetime

import streamlit as st
import redis

from state import AgentState
from langgraph.graph import START
from langchain_core.messages import HumanMessage, AIMessage
from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_SESSION_TTL

# =============================================================================
# 页面配置
# =============================================================================
st.set_page_config(
    page_title="XF 模具智能体平台",
    page_icon="🔧",
    layout="wide",
)

# =============================================================================
# Redis 连接
# =============================================================================
_r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
SESSION_PREFIX = "xf:session"

def _meta_key(sid: str) -> str:
    return f"{SESSION_PREFIX}:{sid}:meta"

def _msg_key(sid: str) -> str:
    return f"{SESSION_PREFIX}:{sid}:messages"


# =============================================================================
# 会话管理（Redis 持久化）
# =============================================================================
def init_sessions():
    if "current_session" not in st.session_state:
        st.session_state.current_session = None

init_sessions()

def get_all_sessions() -> dict:
    """扫描 Redis 中所有会话，返回 {sid: {title, created_at}}，按创建时间倒序"""
    sessions = {}
    for key in _r.scan_iter(f"{SESSION_PREFIX}:*:meta"):
        parts = key.split(":")
        if len(parts) >= 4:
            sid = parts[2]
            meta = _r.hgetall(key)
            if meta:
                sessions[sid] = {
                    "title": meta.get("title", "无标题"),
                    "created_at": meta.get("created_at", ""),
                }
    return dict(sorted(sessions.items(), key=lambda x: x[1]["created_at"], reverse=True))

def create_new_session(title: str = None) -> str:
    sid = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    if title is None:
        existing = get_all_sessions()
        title = f"新对话 {len(existing) + 1}"

    meta_k = _meta_key(sid)
    now = datetime.now().isoformat()
    _r.hset(meta_k, mapping={"title": title, "created_at": now})
    _r.expire(meta_k, REDIS_SESSION_TTL)

    st.session_state.current_session = sid
    return sid

def get_current_history() -> list:
    sid = st.session_state.current_session
    if not sid:
        return []
    if not _r.exists(_meta_key(sid)):
        return []
    raw = _r.lrange(_msg_key(sid), 0, -1)
    return [json.loads(m) for m in raw]

def add_to_history(role: str, content: str):
    sid = st.session_state.current_session
    if not sid:
        return
    msg = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    msg_k = _msg_key(sid)
    meta_k = _meta_key(sid)
    _r.rpush(msg_k, msg)
    _r.expire(msg_k, REDIS_SESSION_TTL)
    _r.expire(meta_k, REDIS_SESSION_TTL)


# =============================================================================
# 侧边栏
# =============================================================================
with st.sidebar:
    st.title("🔧 XF 模具")
    st.caption("研发 & 质量 双智能体平台")

    st.divider()

    if st.button("➕ 新建对话", use_container_width=True):
        create_new_session()
        st.rerun()

    st.divider()
    st.subheader("对话历史")

    all_sessions = get_all_sessions()
    for sid, session in all_sessions.items():
        if st.button(
            f"{session['title']}",
            key=f"session_{sid}",
            use_container_width=True,
            type="secondary" if sid != st.session_state.current_session else "primary",
        ):
            st.session_state.current_session = sid
            st.rerun()

    st.divider()
    st.caption("知识源：")
    st.caption("• FMEA 手册 (AIAG-VDA)")
    st.caption("• VDA6.4 质量手册")

    # 清空所有
    if st.button("🗑 清空所有对话", use_container_width=True, type="secondary"):
        for sid in list(get_all_sessions().keys()):
            _r.delete(_meta_key(sid), _msg_key(sid))
        create_new_session()
        st.rerun()


# =============================================================================
# 主聊天区
# =============================================================================
st.title("💬 XF 模具智能体")

# 自动创建第一个会话
if st.session_state.current_session is None:
    create_new_session()

# 渲染历史消息
history = get_current_history()
for msg in history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 禁用直接调用 graph（使用 API 模式）
API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000")

if prompt := st.chat_input("请输入您的问题..."):
    # 显示用户消息
    with st.chat_message("user"):
        st.markdown(prompt)
    add_to_history("user", prompt)

    # 构建 API 请求
    with st.chat_message("assistant"):
        with st.spinner("智能体思考中..."):
            try:
                prev_msgs = [
                    {"role": m["role"], "content": m["content"]}
                    for m in history
                ]
                resp = requests.post(
                    f"{API_URL}/api/ask",
                    json={"question": prompt, "chat_history": prev_msgs},
                    timeout=120,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    answer = data.get("answer", "")
                    agent_type = data.get("agent_type", "")
                    intent = data.get("intent", "")

                    # 显示标签
                    if agent_type == "rd":
                        st.caption("🤖 研发智能体")
                    elif agent_type == "quality":
                        st.caption("📋 质量智能体")

                    st.markdown(answer)
                    add_to_history("assistant", answer)
                else:
                    error_msg = f"请求失败: HTTP {resp.status_code}"
                    st.error(error_msg)
                    add_to_history("assistant", error_msg)
            except requests.exceptions.ConnectionError:
                err = "无法连接到后端服务，请确保 API 服务已启动 (python api.py)"
                st.error(err)
                add_to_history("assistant", err)
            except Exception as e:
                err = f"请求出错: {e}"
                st.error(err)
                add_to_history("assistant", err)

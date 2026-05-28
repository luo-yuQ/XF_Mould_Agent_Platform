import type { Session } from "../types";

const STORAGE_KEY = "xf_mould_sessions";
const CURRENT_KEY = "xf_mould_current";

/** 加载所有会话 */
export function loadSessions(): Record<string, Session> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

/** 保存所有会话 */
export function saveSessions(sessions: Record<string, Session>): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

/** 获取当前会话 ID */
export function getCurrentSessionId(): string | null {
  return localStorage.getItem(CURRENT_KEY);
}

/** 设置当前会话 ID */
export function setCurrentSessionId(id: string | null): void {
  if (id) {
    localStorage.setItem(CURRENT_KEY, id);
  } else {
    localStorage.removeItem(CURRENT_KEY);
  }
}

/** 生成会话 ID */
export function generateSessionId(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  );
}

/** 创建新会话 */
export function createSession(title?: string): Session {
  return {
    id: generateSessionId(),
    title: title || "新对话",
    createdAt: Date.now(),
    messages: [],
  };
}

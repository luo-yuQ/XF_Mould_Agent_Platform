import type { Session } from "../types";

const SESSIONS_KEY = (userId: number | string) => `xf_mould_sessions_${userId}`;
const CURRENT_KEY = (userId: number | string) => `xf_mould_current_${userId}`;

export function loadSessions(userId: number | string): Record<string, Session> {
  try {
    const raw = localStorage.getItem(SESSIONS_KEY(userId));
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function saveSessions(
  userId: number | string,
  sessions: Record<string, Session>
): void {
  localStorage.setItem(SESSIONS_KEY(userId), JSON.stringify(sessions));
}

export function getCurrentSessionId(
  userId: number | string
): string | null {
  return localStorage.getItem(CURRENT_KEY(userId));
}

export function setCurrentSessionId(
  userId: number | string,
  id: string | null
): void {
  const key = CURRENT_KEY(userId);
  if (id) {
    localStorage.setItem(key, id);
  } else {
    localStorage.removeItem(key);
  }
}

export function clearUserData(userId: number | string): void {
  localStorage.removeItem(SESSIONS_KEY(userId));
  localStorage.removeItem(CURRENT_KEY(userId));
}

export function generateSessionId(): string {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  );
}

export function createSession(title?: string): Session {
  return {
    id: generateSessionId(),
    title: title || "新对话",
    createdAt: Date.now(),
    messages: [],
  };
}

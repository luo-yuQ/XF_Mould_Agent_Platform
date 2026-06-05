import { useState, useCallback, useRef, useEffect } from "react";
import type { Session, Message } from "./types";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import FMEAGenerator from "./components/FMEAGenerator";
import AuditCheck from "./components/AuditCheck";
import ReportGenerator from "./components/ReportGenerator";
import AuthPage from "./pages/AuthPage";

export default function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [currentUser, setCurrentUser] = useState<{ id: number; username: string } | null>(null);
  const [sessions, setSessions] = useState<Record<string, Session>>({});
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState("");
  const [status, setStatus] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeView, setActiveView] = useState<"chat" | "fmea" | "audit" | "report">("chat");
  const abortRef = useRef<AbortController | null>(null);
  // LRU 缓存：保留最近 3 个会话的消息
  const LRU_CACHE_SIZE = 3;
  const loadedOrderRef = useRef<string[]>([]);

  // 加载当前登录用户（启动时 + 登录成功后都调一次）
  const loadCurrentUser = useCallback(async () => {
    try {
      const res = await fetch("/auth/me", {
        credentials: "include",
        cache: "no-store",
      });
      if (res.ok) {
        const data = await res.json();
        setCurrentUser({ id: data.id, username: data.username });
        setAuthenticated(true);
      } else {
        setCurrentUser(null);
        setAuthenticated(false);
      }
    } catch {
      setCurrentUser(null);
      setAuthenticated(false);
    } finally {
      setCheckingAuth(false);
    }
  }, []);

  useEffect(() => {
    loadCurrentUser();
  }, [loadCurrentUser]);

  // 登录后从后端拉会话列表
  useEffect(() => {
    if (!currentUser) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch("/chat/sessions", { credentials: "include" });
        if (!res.ok) return;
        const list: Array<{ id: string; title: string; created_at: string; updated_at: string }> =
          await res.json();
        if (cancelled) return;
        const map: Record<string, Session> = {};
        for (const s of list) {
          map[s.id] = {
            id: s.id,
            title: s.title,
            createdAt: new Date(s.created_at).getTime(),
            updatedAt: new Date(s.updated_at).getTime(),
            messages: [],
            loaded: false,
          };
        }
        setSessions(map);
        if (list.length > 0) {
          setCurrentId(list[0].id);
        } else {
          // 没有任何会话时自动开一个
          const created = await fetch("/chat/sessions", {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
          });
          if (created.ok) {
            const s = await created.json();
            if (!cancelled) {
              const newSession: Session = {
                id: s.id,
                title: s.title,
                createdAt: new Date(s.created_at).getTime(),
                updatedAt: new Date(s.updated_at).getTime(),
                messages: [],
                loaded: true,
              };
              setSessions({ [s.id]: newSession });
              setCurrentId(s.id);
            }
          }
        }
      } catch {
        // 静默失败
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentUser]);

  // 切换会话时拉取消息（3 条 LRU 缓存 + 分页首屏 20 条）
  useEffect(() => {
    if (!currentId) return;
    const session = sessions[currentId];
    if (session?.loaded) {
      // 缓存命中，移到 MRU 位置
      loadedOrderRef.current = [
        ...loadedOrderRef.current.filter((id) => id !== currentId),
        currentId,
      ];
      return;
    }

    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/chat/sessions/${currentId}/messages?limit=20`, {
          credentials: "include",
        });
        if (!res.ok) return;
        const list: Array<{
          id: number;
          role: string;
          content: string;
          agent_type: string | null;
          citations: any[] | null;
        }> = await res.json();
        if (cancelled) return;
        const msgs: Message[] = list.map((m) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          agentType: m.agent_type || "",
          citations: m.citations || [],
        }));
        setSessions((prev) => {
          const order = loadedOrderRef.current;
          const next = { ...prev };

          // LRU 淘汰最旧的非当前会话
          while (order.length >= LRU_CACHE_SIZE) {
            const evictId = order.shift();
            if (!evictId || evictId === currentId) continue;
            if (next[evictId]) {
              next[evictId] = {
                ...next[evictId],
                messages: [],
                loaded: false,
                hasMore: false,
                oldestLoadedId: undefined,
                loadingOlder: false,
              };
            }
          }
          if (!order.includes(currentId)) {
            order.push(currentId);
          }

          if (next[currentId]) {
            next[currentId] = {
              ...next[currentId],
              messages: msgs,
              loaded: true,
              hasMore: msgs.length === 20,
              oldestLoadedId: msgs[0]?.id,
              loadingOlder: false,
            };
          }
          return next;
        });
      } catch {
        // 静默失败
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [currentId, sessions]);

  // 加载更早的消息（向上滚动触发）
  const loadOlderMessages = useCallback(async () => {
    if (!currentId) return;
    const session = sessions[currentId];
    if (!session || !session.hasMore || session.loadingOlder || !session.oldestLoadedId) return;

    setSessions((prev) => ({
      ...prev,
      [currentId]: { ...prev[currentId], loadingOlder: true },
    }));

    try {
      const res = await fetch(
        `/chat/sessions/${currentId}/messages?limit=20&before_id=${session.oldestLoadedId}`,
        { credentials: "include" }
      );
      if (!res.ok) {
        setSessions((prev) => ({
          ...prev,
          [currentId]: { ...prev[currentId], loadingOlder: false },
        }));
        return;
      }
      const list: Array<{
        id: number;
        role: string;
        content: string;
        agent_type: string | null;
        citations: any[] | null;
      }> = await res.json();
      const olderMsgs: Message[] = list.map((m) => ({
        id: m.id,
        role: m.role as "user" | "assistant",
        content: m.content,
        agentType: m.agent_type || "",
        citations: m.citations || [],
      }));
      setSessions((prev) => {
        const s = prev[currentId];
        if (!s) return prev;
        return {
          ...prev,
          [currentId]: {
            ...s,
            messages: [...olderMsgs, ...s.messages],
            hasMore: olderMsgs.length === 20,
            oldestLoadedId: olderMsgs[0]?.id ?? s.oldestLoadedId,
            loadingOlder: false,
          },
        };
      });
    } catch {
      setSessions((prev) => ({
        ...prev,
        [currentId]: { ...prev[currentId], loadingOlder: false },
      }));
    }
  }, [currentId, sessions]);

  const currentSession = currentId ? sessions[currentId] : null;

  const handleLogout = useCallback(async () => {
    abortRef.current?.abort();
    abortRef.current = null;
    try {
      await fetch("/auth/logout", { method: "POST", credentials: "include" });
    } catch {
      // 忽略网络错误
    }
    setCurrentUser(null);
    setAuthenticated(false);
    setSessions({});
    setCurrentId(null);
    setStreamingContent("");
    setStatus("");
    setIsStreaming(false);
  }, []);

  const handleUpdateTitle = useCallback(
    async (id: string, title: string): Promise<boolean> => {
      try {
        const res = await fetch(`/chat/sessions/${id}`, {
          method: "PATCH",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ title }),
        });
        if (!res.ok) return false;
        const updated = await res.json();
        setSessions((prev) => ({
          ...prev,
          [id]: { ...prev[id], title: updated.title },
        }));
        return true;
      } catch {
        return false;
      }
    },
    []
  );

  const handleNewSession = useCallback(async () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setStreamingContent("");
    setStatus("");
    setIsStreaming(false);
    try {
      const res = await fetch("/chat/sessions", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) return;
      const s = await res.json();
      const newSession: Session = {
        id: s.id,
        title: s.title,
        createdAt: new Date(s.created_at).getTime(),
        updatedAt: new Date(s.updated_at).getTime(),
        messages: [],
        loaded: true,
      };
      setSessions((prev) => ({ ...prev, [s.id]: newSession }));
      setCurrentId(s.id);
      setStreamingContent("");
      setIsStreaming(false);
    } catch {
      // 静默失败
    }
  }, []);

  const handleDeleteSession = useCallback(
    async (id: string) => {
      try {
        await fetch(`/chat/sessions/${id}`, {
          method: "DELETE",
          credentials: "include",
        });
      } catch {
        // 即便后端失败也清理本地，避免出现鬼影会话
      }
      loadedOrderRef.current = loadedOrderRef.current.filter((x) => x !== id);
      setSessions((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      if (currentId === id) {
        const remaining = Object.keys(sessions)
          .filter((k) => k !== id)
          .sort(
            (a, b) =>
              (sessions[b]?.createdAt || 0) - (sessions[a]?.createdAt || 0)
          );
        if (remaining.length > 0) {
          setCurrentId(remaining[0]);
        } else {
          handleNewSession();
        }
      }
    },
    [currentId, sessions, handleNewSession]
  );

  const handleSend = useCallback(
    async (text: string, agentOverride: string = "") => {
      if (!currentId || isStreaming) return;

      const session = sessions[currentId];
      if (!session) return;

      const userMsg: Message = { role: "user", content: text };
      setSessions((prev) => ({
        ...prev,
        [currentId]: {
          ...prev[currentId],
          messages: [...(prev[currentId]?.messages || []), userMsg],
        },
      }));
      setStreamingContent("");
      setStatus("");
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await fetch("/api/ask/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ session_id: currentId, question: text, agent_override: agentOverride }),
          signal: controller.signal,
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const reader = response.body?.getReader();
        if (!reader) throw new Error("无法读取响应流");

        const decoder = new TextDecoder();
        let buffer = "";
        let fullAnswer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          let currentEvent = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) {
              currentEvent = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));

                if (currentEvent === "status") {
                  setStatus(data.message || "");
                } else if (currentEvent === "token" && data.content) {
                  fullAnswer += data.content;
                  setStreamingContent(fullAnswer);
                } else if (currentEvent === "done") {
                  fullAnswer = data.full_answer || fullAnswer;
                  setStreamingContent("");
                  setStatus("");
                  setIsStreaming(false);

                  setSessions((prev) => {
                    if (!prev[currentId]) return prev;
                    const s = prev[currentId];
                    const newTitle = data.title ?? null;
                    return {
                      ...prev,
                      [currentId]: {
                        ...s,
                        title: newTitle ?? s.title,
                        messages: [
                          ...s.messages,
                          {
                            role: "assistant",
                            content: fullAnswer,
                            agentType: data.agent_type || "",
                            citations: data.citations || [],
                          },
                        ],
                      },
                    };
                  });
                } else if (currentEvent === "error") {
                  throw new Error(data.message || "未知错误");
                }
              } catch (e: any) {
                if (e.name === "SyntaxError") continue;
                throw e;
              }
            }
          }
        }
      } catch (err: any) {
        if (err.name !== "AbortError") {
          setStreamingContent("");
          setStatus("");
          setIsStreaming(false);
          setSessions((prev) => {
            if (!prev[currentId]) return prev;
            const s = prev[currentId];
            return {
              ...prev,
              [currentId]: {
                ...s,
                messages: [
                  ...s.messages,
                  {
                    role: "assistant",
                    content: `请求出错: ${err.message}`,
                  },
                ],
              },
            };
          });
        }
      } finally {
        abortRef.current = null;
        setIsStreaming(false);
      }
    },
    [currentId, isStreaming, sessions]
  );

  if (checkingAuth) {
    return (
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100vh" }}>
        <div style={{ color: "#6b7280" }}>加载中...</div>
      </div>
    );
  }

  if (!authenticated) {
    return <AuthPage onLogin={loadCurrentUser} />;
  }

  return (
    <div className="app-layout">
      <Sidebar
        sessions={Object.values(sessions)}
        currentId={currentId}
        activeView={activeView}
        username={currentUser?.username ?? null}
        isStreaming={isStreaming}
        onSelect={(id) => {
          // 流式响应时禁止切换（双重保护）
          if (isStreaming) return;
          setCurrentId(id);
          setStreamingContent("");
          setStatus("");
          setActiveView("chat");
        }}
        onOpenChat={() => setActiveView("chat")}
        onOpenFMEA={() => setActiveView("fmea")}
        onOpenAudit={() => setActiveView("audit")}
        onOpenReport={() => setActiveView("report")}
        onNew={handleNewSession}
        onDelete={handleDeleteSession}
        onUpdateTitle={handleUpdateTitle}
        onLogout={handleLogout}
      />
      {activeView === "fmea" ? (
        <FMEAGenerator sessionId={currentId} />
      ) : activeView === "audit" ? (
        <AuditCheck sessionId={currentId} />
      ) : activeView === "report" ? (
        <ReportGenerator />
      ) : (
        <ChatWindow
          session={currentSession ?? null}
          streamingContent={streamingContent}
          status={status}
          isStreaming={isStreaming}
          onSend={handleSend}
          onLoadOlder={loadOlderMessages}
        />
      )}
    </div>
  );
}

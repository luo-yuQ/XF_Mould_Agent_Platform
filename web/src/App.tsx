import { useState, useCallback, useRef, useEffect } from "react";
import type { Session, Message } from "./types";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import {
  loadSessions,
  saveSessions,
  getCurrentSessionId,
  setCurrentSessionId,
  createSession,
} from "./utils/storage";

export default function App() {
  const [sessions, setSessions] = useState<Record<string, Session>>(() =>
    loadSessions()
  );
  const [currentId, setCurrentId] = useState<string | null>(() =>
    getCurrentSessionId()
  );
  const [streamingContent, setStreamingContent] = useState("");
  const [status, setStatus] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const streamSessionRef = useRef<string | null>(null);

  // 确保至少有一个会话
  useEffect(() => {
    const ids = Object.keys(sessions);
    if (ids.length === 0) {
      const s = createSession();
      setSessions({ [s.id]: s });
      setCurrentId(s.id);
      setCurrentSessionId(s.id);
    } else if (!currentId || !sessions[currentId]) {
      const latestId = ids.sort(
        (a, b) => (sessions[b]?.createdAt || 0) - (sessions[a]?.createdAt || 0)
      )[0];
      setCurrentId(latestId);
      setCurrentSessionId(latestId);
    }
  }, []);

  // 持久化
  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  useEffect(() => {
    setCurrentSessionId(currentId);
  }, [currentId]);

  const currentSession = currentId ? sessions[currentId] : null;

  const handleNewSession = useCallback(() => {
    abortRef.current?.abort();
    const s = createSession();
    setSessions((prev) => ({ ...prev, [s.id]: s }));
    setCurrentId(s.id);
    setStreamingContent("");
    setIsStreaming(false);
  }, []);

  const handleDeleteSession = useCallback(
    (id: string) => {
      setSessions((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
      if (currentId === id) {
        const remaining = Object.keys(sessions).filter((k) => k !== id);
        if (remaining.length > 0) {
          const latestId = remaining.sort(
            (a, b) =>
              (sessions[b]?.createdAt || 0) - (sessions[a]?.createdAt || 0)
          )[0];
          setCurrentId(latestId);
        } else {
          const s = createSession();
          setSessions((prev) => ({ ...prev, [s.id]: s }));
          setCurrentId(s.id);
        }
      }
    },
    [currentId, sessions]
  );

  const handleSend = useCallback(
    async (text: string) => {
      if (!currentId || isStreaming) return;

      const session = sessions[currentId];
      if (!session) return;

      const userMsg: Message = { role: "user", content: text };
      const updatedSession = {
        ...session,
        title:
          session.messages.length === 0
            ? text.slice(0, 30) + (text.length > 30 ? "..." : "")
            : session.title,
        messages: [...session.messages, userMsg],
      };
      setSessions((prev) => ({ ...prev, [currentId]: updatedSession }));
      setStreamingContent("");
      setStatus("");
      setIsStreaming(true);
      streamSessionRef.current = currentId;

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const history = updatedSession.messages.slice(
          0,
          updatedSession.messages.length - 1
        );

        const chatHistory = history.map((m) => ({
          role: m.role,
          content: m.content,
        }));

        const response = await fetch("/api/ask/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: text, chat_history: chatHistory }),
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
                    const sid = streamSessionRef.current;
                    if (!sid || !prev[sid]) return prev;
                    const s = prev[sid];
                    return {
                      ...prev,
                      [sid]: {
                        ...s,
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
            const sid = streamSessionRef.current;
            if (!sid || !prev[sid]) return prev;
            const s = prev[sid];
            return {
              ...prev,
              [sid]: {
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
        if (streamingContent) {
          setIsStreaming(false);
        }
      }
    },
    [currentId, isStreaming, sessions, streamingContent]
  );

  return (
    <div className="app-layout">
      <Sidebar
        sessions={Object.values(sessions)}
        currentId={currentId}
        onSelect={(id) => {
          abortRef.current?.abort();
          setCurrentId(id);
          setStreamingContent("");
          setIsStreaming(false);
        }}
        onNew={handleNewSession}
        onDelete={handleDeleteSession}
      />
      <ChatWindow
        session={currentSession ?? null}
        streamingContent={streamingContent}
        status={status}
        isStreaming={isStreaming}
        onSend={handleSend}
      />
    </div>
  );
}

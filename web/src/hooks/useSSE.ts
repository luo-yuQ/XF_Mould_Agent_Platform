import { useState, useRef, useCallback } from "react";
import type { Message, SSEEvent } from "../types";

interface UseSSEReturn {
  status: string;
  isStreaming: boolean;
  sendMessage: (question: string, history: Message[]) => Promise<string>;
  abort: () => void;
}

export function useSSE(): UseSSEReturn {
  const [status, setStatus] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (question: string, history: Message[]): Promise<string> => {
      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);
      setStatus("");

      let fullAnswer = "";

      try {
        const chatHistory = history.map((m) => ({
          role: m.role,
          content: m.content,
        }));

        const response = await fetch("/api/ask/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question, chat_history: chatHistory }),
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error("无法读取响应流");
        }

        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Parse SSE events from buffer
          const lines = buffer.split("\n");
          buffer = lines.pop() || ""; // keep incomplete line in buffer

          let currentEvent = "";
          for (const line of lines) {
            if (line.startsWith("event: ")) {
              currentEvent = line.slice(7).trim();
            } else if (line.startsWith("data: ")) {
              const dataStr = line.slice(6);
              try {
                const data = JSON.parse(dataStr) as SSEEvent;
                if (currentEvent === "status" && data.type === "status") {
                  setStatus(data.message);
                } else if (currentEvent === "token" && data.type === "token") {
                  fullAnswer += data.content;
                } else if (currentEvent === "done" && data.type === "done") {
                  fullAnswer = data.full_answer || fullAnswer;
                }
              } catch {
                // ignore parse errors for incomplete JSON
              }
            }
          }
        }

        return fullAnswer;
      } catch (error: unknown) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return fullAnswer;
        }
        throw error;
      } finally {
        setIsStreaming(false);
        setStatus("");
        abortRef.current = null;
      }
    },
    []
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { status, isStreaming, sendMessage, abort };
}

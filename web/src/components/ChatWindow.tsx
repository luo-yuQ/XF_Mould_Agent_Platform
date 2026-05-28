import { useEffect, useRef } from "react";
import type { Session } from "../types";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";

interface Props {
  session: Session | null;
  streamingContent: string;
  status: string;
  isStreaming: boolean;
  onSend: (text: string) => void;
}

export default function ChatWindow({
  session,
  streamingContent,
  status,
  isStreaming,
  onSend,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages, streamingContent, status]);

  const messages = session?.messages ?? [];

  return (
    <div className="chat-window">
      <div className="chat-messages">
        {messages.length === 0 && !isStreaming && (
          <div className="chat-empty">
            <h2>XF 模具智能体平台</h2>
            <p>基于 AI 的研发 & 质量管理助手</p>
            <div className="chat-empty-hints">
              <span>试试问：</span>
              <button onClick={() => onSend("什么是 DFMEA？")}>
                什么是 DFMEA？
              </button>
              <button onClick={() => onSend("VDA6.4 质量体系包含哪些内容？")}>
                VDA6.4 质量体系包含哪些内容？
              </button>
              <button onClick={() => onSend("帮我生成一份 PFMEA 报告")}>
                帮我生成一份 PFMEA 报告
              </button>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <MessageBubble key={i} message={msg} />
        ))}

        {/* 流式输出中的临时消息 */}
        {(streamingContent || status) && (
          <div className="message-row message-assistant">
            <div className="message-avatar">🤖</div>
            <div className="message-bubble">
              {status && (
                <div className="message-status">{status}</div>
              )}
              {streamingContent && (
                <div className="message-content">{streamingContent}</div>
              )}
              {isStreaming && !streamingContent && !status && (
                <div className="message-loading">
                  <span className="dot-pulse" />
                </div>
              )}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <ChatInput onSend={onSend} disabled={isStreaming} />
    </div>
  );
}

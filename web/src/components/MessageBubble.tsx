import type { Message as MessageType } from "../types";
import ReactMarkdown from "./Markdown";

interface Props {
  message: MessageType;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";
  const citations = message.citations ?? [];

  return (
    <div className={`message-row ${isUser ? "message-user" : "message-assistant"}`}>
      <div className="message-avatar">
        {isUser ? "👤" : "🤖"}
      </div>
      <div className="message-bubble">
        {!isUser && message.agentType && (
          <div className="message-agent-tag">
            {message.agentType === "rd" ? "研发智能体" : "质量智能体"}
          </div>
        )}
        <div className="message-content">
          <ReactMarkdown content={message.content} citations={citations} />
        </div>

        {/* Citation 卡片 */}
        {!isUser && citations.length > 0 && (
          <div className="citations-block">
            <div className="citations-title">参考资料</div>
            {citations.map((cit) => (
              <div key={cit.id} className="citation-item">
                <span className="citation-id">[{cit.id}]</span>
                <span className="citation-detail">
                  {cit.source}
                  {cit.heading_path ? ` · ${cit.heading_path}` : cit.chapter ? ` · 第${cit.chapter}章 ${cit.section_title}` : ""}
                  {cit.row_range ? ` · 行${cit.row_range}` : ""}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

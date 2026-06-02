import { useState, useRef, useEffect } from "react";

interface Props {
  onSend: (text: string, agentOverride: string) => void;
  disabled: boolean;
}

const AGENT_OPTIONS = [
  { value: "", label: "自动" },
  { value: "rd", label: "研发" },
  { value: "quality", label: "质量" },
] as const;

export default function ChatInput({ onSend, disabled }: Props) {
  const [text, setText] = useState("");
  const [agent, setAgent] = useState<string>("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!disabled && textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [disabled]);

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, agent);
    setText("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="chat-input-container">
      <div className="agent-selector">
        {AGENT_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            className={`agent-option ${agent === opt.value ? "active" : ""}`}
            onClick={() => setAgent(opt.value)}
            disabled={disabled}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <div className="chat-input-wrapper">
        <textarea
          ref={textareaRef}
          className="chat-input"
          rows={1}
          placeholder="请输入您的问题... (Enter 发送, Shift+Enter 换行)"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
        />
        <button
          className="btn-send"
          onClick={handleSubmit}
          disabled={disabled || !text.trim()}
        >
          发送
        </button>
      </div>
    </div>
  );
}

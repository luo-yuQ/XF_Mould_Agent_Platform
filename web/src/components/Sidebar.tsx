import { useState } from "react";
import type { Session } from "../types";

interface Props {
  sessions: Session[];
  currentId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

export default function Sidebar({
  sessions,
  currentId,
  onSelect,
  onNew,
  onDelete,
}: Props) {
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const sorted = [...sessions].sort(
    (a, b) => b.createdAt - a.createdAt
  );

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1 className="sidebar-logo">XF 模具智能体</h1>
        <p className="sidebar-subtitle">研发 & 质量双智能体平台</p>
      </div>

      <button className="btn-new-chat" onClick={onNew}>
        + 新建对话
      </button>

      <div className="sidebar-section">
        <h3 className="sidebar-section-title">对话历史</h3>
        <div className="session-list">
          {sorted.length === 0 && (
            <p className="session-empty">暂无对话</p>
          )}
          {sorted.map((s) => (
            <div
              key={s.id}
              className={`session-item ${s.id === currentId ? "active" : ""}`}
              onClick={() => onSelect(s.id)}
            >
              <span className="session-title">{s.title}</span>
              {confirmDelete === s.id ? (
                <div className="session-delete-confirm">
                  <button
                    className="btn-confirm"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(s.id);
                      setConfirmDelete(null);
                    }}
                  >
                    确认
                  </button>
                  <button
                    className="btn-cancel"
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmDelete(null);
                    }}
                  >
                    取消
                  </button>
                </div>
              ) : (
                <button
                  className="btn-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    setConfirmDelete(s.id);
                  }}
                  title="删除对话"
                >
                  ×
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="sidebar-footer">
        <p>知识源：FMEA 手册 · VDA6.4 质量手册</p>
      </div>
    </aside>
  );
}

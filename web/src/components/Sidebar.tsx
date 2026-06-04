import { useState } from "react";
import type { Session } from "../types";

interface Props {
  sessions: Session[];
  currentId: string | null;
  activeView: "chat" | "fmea" | "audit";
  username: string | null;
  isStreaming: boolean;
  onSelect: (id: string) => void;
  onOpenChat: () => void;
  onOpenFMEA: () => void;
  onOpenAudit: () => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onUpdateTitle: (id: string, title: string) => Promise<boolean>;
  onLogout: () => void;
}

export default function Sidebar({
  sessions,
  currentId,
  activeView,
  username,
  isStreaming,
  onSelect,
  onOpenChat,
  onOpenFMEA,
  onOpenAudit,
  onNew,
  onDelete,
  onUpdateTitle,
  onLogout,
}: Props) {
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  const sorted = [...sessions].sort(
    (a, b) => (b.updatedAt ?? b.createdAt) - (a.updatedAt ?? a.createdAt)
  );

  const startEdit = (s: Session) => {
    setEditingId(s.id);
    setEditingTitle(s.title);
    setConfirmDelete(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditingTitle("");
  };

  const commitEdit = async (id: string) => {
    const trimmed = editingTitle.trim();
    if (!trimmed) {
      cancelEdit();
      return;
    }
    const original = sessions.find((s) => s.id === id)?.title ?? "";
    if (trimmed === original) {
      cancelEdit();
      return;
    }
    const ok = await onUpdateTitle(id, trimmed);
    if (!ok) {
      // 失败保留编辑状态让用户看到
      return;
    }
    cancelEdit();
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h1 className="sidebar-logo">XF 模具智能体</h1>
        <p className="sidebar-subtitle">研发 & 质量双智能体平台</p>
      </div>

      <button
        className="btn-new-chat"
        onClick={onNew}
        disabled={isStreaming}
        title={isStreaming ? "请等待当前对话完成" : ""}
      >
        + 新建对话
      </button>

      <div className="sidebar-section sidebar-module-section">
        <h3 className="sidebar-section-title">XF质量</h3>
        <button
          className={`module-entry ${activeView === "chat" ? "active" : ""}`}
          onClick={onOpenChat}
          disabled={isStreaming}
        >
          质量问答
        </button>
        <button
          className={`module-entry ${activeView === "fmea" ? "active" : ""}`}
          onClick={onOpenFMEA}
          disabled={isStreaming}
        >
          FMEA生成
        </button>
        <button
          className={`module-entry ${activeView === "audit" ? "active" : ""}`}
          onClick={onOpenAudit}
          disabled={isStreaming}
        >
          审核检查
        </button>
      </div>

      <div className="sidebar-section">
        <h3 className="sidebar-section-title">对话历史</h3>
        <div className="session-list">
          {sorted.length === 0 && (
            <p className="session-empty">暂无对话</p>
          )}
          {sorted.map((s) => {
            const isEditing = editingId === s.id;
            return (
              <div
                key={s.id}
                className={`session-item ${s.id === currentId ? "active" : ""} ${isStreaming && s.id !== currentId ? "disabled" : ""}`}
                onClick={() => {
                  if (isStreaming) return; // 流式响应时禁止切换
                  if (!isEditing) onSelect(s.id);
                }}
                onDoubleClick={() => {
                  if (isStreaming) return;
                  if (!isEditing) startEdit(s);
                }}
              >
                {isEditing ? (
                  <input
                    className="session-title-input"
                    value={editingTitle}
                    autoFocus
                    maxLength={200}
                    onChange={(e) => setEditingTitle(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        commitEdit(s.id);
                      } else if (e.key === "Escape") {
                        e.preventDefault();
                        cancelEdit();
                      }
                    }}
                    onBlur={() => commitEdit(s.id)}
                  />
                ) : (
                  <span className="session-title" title={s.title}>
                    {s.title}
                  </span>
                )}

                {!isEditing && confirmDelete === s.id ? (
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
                ) : !isEditing ? (
                  <div className="session-actions">
                    <button
                      className="btn-edit"
                      onClick={(e) => {
                        e.stopPropagation();
                        startEdit(s);
                      }}
                      disabled={isStreaming}
                      title={isStreaming ? "请等待当前对话完成" : "编辑标题（双击也可）"}
                    >
                      ✎
                    </button>
                    <button
                      className="btn-delete"
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmDelete(s.id);
                      }}
                      disabled={isStreaming}
                      title={isStreaming ? "请等待当前对话完成" : "删除对话"}
                    >
                      ×
                    </button>
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>

      <div className="sidebar-footer">
        <p>知识源：FMEA 手册 · VDA6.4 质量手册</p>
        {username && (
          <div className="sidebar-user">
            <span className="sidebar-user-name">{username}</span>
            <button className="btn-logout" onClick={onLogout}>
              退出
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}

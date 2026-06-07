import { useState, type FormEvent } from "react";
import Markdown from "./Markdown";

interface Props {
  sessionId: string | null;
}

type AuditType = "quality_issue" | "pfmea" | "audit_record" | "general";

interface AuditResponse {
  final_answer: string;
  audit_run_id: string | null;
  findings: Array<Record<string, unknown>>;
  verify_result: Record<string, unknown>;
  references: Array<Record<string, unknown>>;
}

const AUDIT_TYPE_OPTIONS: Array<{ value: AuditType; label: string }> = [
  { value: "quality_issue", label: "质量问题描述" },
  { value: "pfmea", label: "PFMEA内容" },
  { value: "audit_record", label: "审核记录" },
  { value: "general", label: "其他" },
];

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export default function AuditCheck({ sessionId }: Props) {
  const [auditType, setAuditType] = useState<AuditType>("quality_issue");
  const [content, setContent] = useState("");
  const [focus, setFocus] = useState("");
  const [background, setBackground] = useState("");
  const [answer, setAnswer] = useState("");
  const [auditRunId, setAuditRunId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const canSubmit = Boolean(sessionId) && content.trim() && !submitting;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!sessionId || !canSubmit) return;

    setSubmitting(true);
    setError("");
    setAnswer("");
    setAuditRunId(null);

    try {
      const res = await fetch("/quality/audit/check", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          audit_type: auditType,
          content: content.trim(),
          focus: focus.trim(),
          background: background.trim(),
        }),
      });

      if (!res.ok) {
        let message = `HTTP ${res.status}`;
        try {
          const data = await res.json();
          message = data.detail || message;
        } catch {
          // Keep the HTTP status fallback.
        }
        throw new Error(message);
      }

      const data: AuditResponse = await res.json();
      setAnswer(data.final_answer || "");
      setAuditRunId(data.audit_run_id || null);
    } catch (err: unknown) {
      setError(errorMessage(err, "审核检查失败"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fmea-page">
      <div className="fmea-header">
        <div>
          <h2>审核检查</h2>
          <p>XF质量 · 审核发现检查</p>
        </div>
      </div>

      <form className="fmea-form" onSubmit={handleSubmit}>
        <div className="fmea-form-grid">
          <label className="fmea-field">
            <span>审核对象类型</span>
            <select
              value={auditType}
              onChange={(event) => setAuditType(event.target.value as AuditType)}
              disabled={submitting}
            >
              {AUDIT_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="fmea-field">
            <span>审核重点</span>
            <input
              value={focus}
              onChange={(event) => setFocus(event.target.value)}
              placeholder="可选，例如：整改闭环、原因分析、探测控制"
              disabled={submitting}
            />
          </label>

          <label className="fmea-field fmea-field-wide">
            <span>待审核内容</span>
            <textarea
              value={content}
              onChange={(event) => setContent(event.target.value)}
              placeholder="粘贴质量问题描述、PFMEA内容或审核记录"
              disabled={submitting}
              rows={10}
            />
          </label>

          <label className="fmea-field fmea-field-wide">
            <span>补充背景</span>
            <textarea
              value={background}
              onChange={(event) => setBackground(event.target.value)}
              placeholder="可选，例如：产品、工序、客户要求、现场情况"
              disabled={submitting}
              rows={4}
            />
          </label>
        </div>

        <div className="fmea-actions">
          <button className="fmea-submit" type="submit" disabled={!canSubmit}>
            {submitting ? "检查中..." : "开始审核检查"}
          </button>
          {!sessionId && <span className="fmea-note">请先创建或选择一个会话</span>}
        </div>
      </form>

      {error && <div className="fmea-error">{error}</div>}

      {answer && (
        <div className="fmea-result">
          <div className="fmea-result-title">审核检查结果</div>
          {auditRunId && (
            <div className="artifact-run-id">
              已保存为 Audit 业务产物：<strong>{auditRunId}</strong>
            </div>
          )}
          <div className="message-content">
            <Markdown content={answer} citations={[]} />
          </div>
        </div>
      )}
    </div>
  );
}

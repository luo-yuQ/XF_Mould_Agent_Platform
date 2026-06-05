import { useEffect, useState, type FormEvent } from "react";
import Markdown from "./Markdown";

interface ReportSourceItem {
  id: string;
  title: string;
  summary: string;
  created_at: string;
}

interface ReportSourcesResponse {
  fmea_runs: ReportSourceItem[];
  audit_runs: ReportSourceItem[];
}

interface ReportGenerateResponse {
  final_markdown: string;
  report_run_id?: string | null;
  verify_result: Record<string, any>;
  references: Array<Record<string, any>>;
  manual_check_items: string[];
}

function formatTime(value: string) {
  const time = new Date(value);
  if (Number.isNaN(time.getTime())) return "";
  return time.toLocaleString();
}

function sourceLabel(item: ReportSourceItem) {
  const time = formatTime(item.created_at);
  return time ? `${item.title} | ${time}` : item.title;
}

export default function ReportGenerator() {
  const [fmeaRuns, setFmeaRuns] = useState<ReportSourceItem[]>([]);
  const [auditRuns, setAuditRuns] = useState<ReportSourceItem[]>([]);
  const [selectedFmeaId, setSelectedFmeaId] = useState("");
  const [selectedAuditId, setSelectedAuditId] = useState("");
  const [title, setTitle] = useState("");
  const [extraBackground, setExtraBackground] = useState("");
  const [answer, setAnswer] = useState("");
  const [reportRunId, setReportRunId] = useState<string | null>(null);
  const [verifyResult, setVerifyResult] = useState<Record<string, any> | null>(null);
  const [manualCheckItems, setManualCheckItems] = useState<string[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const missingSourceNotice =
    !selectedFmeaId || !selectedAuditId ? "缺少分析产物，报告需要人工确认" : "";

  const canSubmit =
    !submitting &&
    (Boolean(selectedFmeaId) || Boolean(selectedAuditId) || Boolean(extraBackground.trim()));

  const loadSources = async () => {
    setSourcesLoading(true);
    setError("");
    try {
      const res = await fetch("/quality/report/sources", {
        credentials: "include",
      });
      if (!res.ok) {
        let message = `HTTP ${res.status}`;
        try {
          const data = await res.json();
          message = data.detail || message;
        } catch {
          // 保留 HTTP 状态兜底
        }
        throw new Error(message);
      }
      const data: ReportSourcesResponse = await res.json();
      setFmeaRuns(data.fmea_runs || []);
      setAuditRuns(data.audit_runs || []);
    } catch (err: any) {
      setError(err.message || "报告来源加载失败");
    } finally {
      setSourcesLoading(false);
    }
  };

  useEffect(() => {
    loadSources();
  }, []);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;

    setSubmitting(true);
    setError("");
    setAnswer("");
    setReportRunId(null);
    setVerifyResult(null);
    setManualCheckItems([]);

    try {
      const res = await fetch("/quality/report/generate", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          report_type: "quality_issue_report",
          title: title.trim() || null,
          fmea_run_id: selectedFmeaId || null,
          audit_run_id: selectedAuditId || null,
          extra_background: extraBackground.trim() || null,
          include_chat_summary: false,
        }),
      });

      if (!res.ok) {
        let message = `HTTP ${res.status}`;
        try {
          const data = await res.json();
          message = data.detail || message;
        } catch {
          // 保留 HTTP 状态兜底
        }
        throw new Error(message);
      }

      const data: ReportGenerateResponse = await res.json();
      setAnswer(data.final_markdown || "");
      setReportRunId(data.report_run_id || null);
      setVerifyResult(data.verify_result || {});
      setManualCheckItems(data.manual_check_items || []);
    } catch (err: any) {
      setError(err.message || "报告生成失败");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fmea-page">
      <div className="fmea-header">
        <div>
          <h2>报告生成</h2>
          <p>XF质量 · 质量问题分析报告</p>
        </div>
        <button className="report-refresh" type="button" onClick={loadSources} disabled={sourcesLoading || submitting}>
          刷新来源
        </button>
      </div>

      <form className="fmea-form" onSubmit={handleSubmit}>
        <div className="fmea-form-grid">
          <label className="fmea-field fmea-field-wide">
            <span>FMEA生成结果</span>
            <select
              value={selectedFmeaId}
              onChange={(event) => setSelectedFmeaId(event.target.value)}
              disabled={sourcesLoading || submitting}
            >
              <option value="">不选择 FMEA，生成草稿报告</option>
              {fmeaRuns.map((item) => (
                <option key={item.id} value={item.id}>
                  {sourceLabel(item)}
                </option>
              ))}
            </select>
            {selectedFmeaId && (
              <p className="report-source-summary">
                {fmeaRuns.find((item) => item.id === selectedFmeaId)?.summary}
              </p>
            )}
          </label>

          <label className="fmea-field fmea-field-wide">
            <span>Audit审核结果</span>
            <select
              value={selectedAuditId}
              onChange={(event) => setSelectedAuditId(event.target.value)}
              disabled={sourcesLoading || submitting}
            >
              <option value="">不选择 Audit，生成草稿报告</option>
              {auditRuns.map((item) => (
                <option key={item.id} value={item.id}>
                  {sourceLabel(item)}
                </option>
              ))}
            </select>
            {selectedAuditId && (
              <p className="report-source-summary">
                {auditRuns.find((item) => item.id === selectedAuditId)?.summary}
              </p>
            )}
          </label>

          <label className="fmea-field fmea-field-wide">
            <span>报告标题</span>
            <input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="例如：座椅滑轨冲压裂纹质量问题分析报告"
              disabled={submitting}
            />
          </label>

          <label className="fmea-field fmea-field-wide">
            <span>补充背景</span>
            <textarea
              value={extraBackground}
              onChange={(event) => setExtraBackground(event.target.value)}
              placeholder="补充质量问题背景、客户反馈、批次、现场信息或分析范围"
              disabled={submitting}
              rows={6}
            />
          </label>
        </div>

        {missingSourceNotice && <div className="report-warning">{missingSourceNotice}</div>}

        <div className="fmea-actions">
          <button className="fmea-submit" type="submit" disabled={!canSubmit}>
            {submitting ? "生成中..." : "生成报告"}
          </button>
          {sourcesLoading && <span className="fmea-note">正在加载可选分析产物...</span>}
          {!canSubmit && !sourcesLoading && (
            <span className="fmea-note">请选择分析产物或填写补充背景</span>
          )}
        </div>
      </form>

      {error && <div className="fmea-error">{error}</div>}

      {answer && (
        <div className="fmea-result">
          <div className="fmea-result-title">
            生成结果{reportRunId ? ` · #${reportRunId}` : ""}
          </div>
          <div className="message-content">
            <Markdown content={answer} citations={[]} />
          </div>
        </div>
      )}

      {verifyResult && (
        <div className="fmea-result report-meta">
          <div className="fmea-result-title">Verifier结果</div>
          <div className={verifyResult.passed ? "report-verify-pass" : "report-verify-fail"}>
            {verifyResult.passed ? "通过" : "需人工确认"}
          </div>
          {Array.isArray(verifyResult.issues) && verifyResult.issues.length > 0 && (
            <ul className="report-list">
              {verifyResult.issues.map((item: string, index: number) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {manualCheckItems.length > 0 && (
        <div className="fmea-result report-meta">
          <div className="fmea-result-title">需人工确认事项</div>
          <ul className="report-list">
            {manualCheckItems.map((item, index) => (
              <li key={`${item}-${index}`}>{item}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

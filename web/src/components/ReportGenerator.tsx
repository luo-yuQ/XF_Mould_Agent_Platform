import { useEffect, useState, type FormEvent } from "react";
import Markdown from "./Markdown";

interface ReportSourceItem {
  id: string;
  title: string | null;
  summary: string | null;
  keywords_json: unknown;
  artifact_type: string | null;
  created_at: string;
  updated_at: string | null;
}

interface ReportSourcesResponse {
  fmea_runs: ReportSourceItem[];
  audit_runs: ReportSourceItem[];
}

interface ReportGenerateResponse {
  final_markdown: string;
  report_run_id?: string | null;
  verify_result: Record<string, unknown>;
  references: Array<Record<string, unknown>>;
  manual_check_items: string[];
  source_match_result?: SourceMatchResult | null;
}

interface SourceMatchResult {
  matched?: "yes" | "no" | "uncertain";
  score?: number;
  common_keywords?: string[];
  manual_check_required?: boolean;
  warning_message?: string;
}

function formatTime(value?: string | null) {
  if (!value) return "";
  const time = new Date(value);
  if (Number.isNaN(time.getTime())) return "";
  return time.toLocaleString();
}

function sourceLabel(item: ReportSourceItem) {
  const title = item.title?.trim() || `业务产物 #${item.id}`;
  const time = formatTime(item.updated_at || item.created_at);
  return time ? `${title} | ${time}` : title;
}

function formatKeywords(value: unknown) {
  if (Array.isArray(value)) {
    const keywords = value.map(String).filter(Boolean);
    return keywords.length > 0 ? keywords.join("、") : "暂无关键词";
  }
  if (value && typeof value === "object") {
    const keywords = Object.values(value).flatMap((item) =>
      Array.isArray(item) ? item.map(String) : [String(item)],
    );
    return keywords.length > 0 ? keywords.join("、") : "暂无关键词";
  }
  if (typeof value === "string" && value.trim()) return value.trim();
  return "暂无关键词";
}

function SourceDetails({
  item,
  defaultArtifactType,
}: {
  item?: ReportSourceItem;
  defaultArtifactType: string;
}) {
  if (!item) return null;

  return (
    <div className="report-source-details">
      <div className="report-source-details-header">
        <strong>{item.title?.trim() || `业务产物 #${item.id}`}</strong>
        <span>{formatTime(item.updated_at || item.created_at)}</span>
      </div>
      <p>{item.summary?.trim() || "未生成摘要"}</p>
      <dl>
        <div>
          <dt>关键词</dt>
          <dd>{formatKeywords(item.keywords_json)}</dd>
        </div>
        <div>
          <dt>产物类型</dt>
          <dd>{item.artifact_type?.trim() || defaultArtifactType}</dd>
        </div>
      </dl>
    </div>
  );
}

async function fetchReportSources() {
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
  return res.json() as Promise<ReportSourcesResponse>;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
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
  const [verifyResult, setVerifyResult] = useState<Record<string, unknown> | null>(null);
  const [manualCheckItems, setManualCheckItems] = useState<string[]>([]);
  const [sourceMatchResult, setSourceMatchResult] = useState<SourceMatchResult | null>(null);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const hasReportInput =
    Boolean(selectedFmeaId) ||
    Boolean(selectedAuditId) ||
    Boolean(title.trim()) ||
    Boolean(extraBackground.trim());
  const missingSourceNotice =
    hasReportInput && (!selectedFmeaId || !selectedAuditId)
      ? "缺少分析产物，报告需要人工确认"
      : "";

  const canSubmit =
    !submitting &&
    (Boolean(selectedFmeaId) || Boolean(selectedAuditId) || Boolean(extraBackground.trim()));

  const loadSources = async () => {
    setSourcesLoading(true);
    setError("");
    try {
      const data = await fetchReportSources();
      setFmeaRuns(data.fmea_runs || []);
      setAuditRuns(data.audit_runs || []);
    } catch (err: unknown) {
      setError(errorMessage(err, "报告来源加载失败"));
    } finally {
      setSourcesLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    fetchReportSources()
      .then((data) => {
        if (!active) return;
        setFmeaRuns(data.fmea_runs || []);
        setAuditRuns(data.audit_runs || []);
      })
      .catch((err: unknown) => {
        if (active) setError(errorMessage(err, "报告来源加载失败"));
      })
      .finally(() => {
        if (active) setSourcesLoading(false);
      });
    return () => {
      active = false;
    };
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
    setSourceMatchResult(null);

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
      setSourceMatchResult(data.source_match_result || null);
    } catch (err: unknown) {
      setError(errorMessage(err, "报告生成失败"));
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
            <SourceDetails
              item={fmeaRuns.find((item) => item.id === selectedFmeaId)}
              defaultArtifactType="FMEA 来源"
            />
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
            <SourceDetails
              item={auditRuns.find((item) => item.id === selectedAuditId)}
              defaultArtifactType="Audit 来源"
            />
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

      {sourceMatchResult && (
        <div className="fmea-result report-meta">
          <div className="fmea-result-title">来源匹配结果</div>
          {sourceMatchResult.manual_check_required && (
            <div className="report-manual-check-alert">
              当前选择的 FMEA 与 Audit 可能不是同一质量问题，报告需人工确认。
            </div>
          )}
          <dl className="report-match-grid">
            <div>
              <dt>匹配结果</dt>
              <dd className={`report-match-status report-match-${sourceMatchResult.matched || "uncertain"}`}>
                {sourceMatchResult.matched || "uncertain"}
              </dd>
            </div>
            <div>
              <dt>匹配分数</dt>
              <dd>{sourceMatchResult.score ?? 0}</dd>
            </div>
            <div>
              <dt>共同关键词</dt>
              <dd>
                {sourceMatchResult.common_keywords?.length
                  ? sourceMatchResult.common_keywords.join("、")
                  : "暂无共同关键词"}
              </dd>
            </div>
            <div>
              <dt>提示信息</dt>
              <dd>{sourceMatchResult.warning_message || "暂无提示"}</dd>
            </div>
          </dl>
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

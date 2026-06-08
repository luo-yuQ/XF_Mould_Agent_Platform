import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import Markdown from "./Markdown";

interface Props {
  sessionId: string | null;
}

interface FMEAResponse {
  final_answer: string;
  fmea_run_id: string | null;
  artifact_id: string | null;
  current_version_id: string | null;
  current_version_no: number | null;
  fmea_rows: Array<Record<string, unknown>>;
  verify_result: Record<string, unknown>;
}

interface ArtifactHistoryItem {
  artifact_id: string;
  artifact_type: "fmea";
  title: string;
  latest_version_id: string | null;
  latest_version_no: number | null;
  created_at: string;
  updated_at: string;
  summary: string;
}

interface ArtifactVersionSummary {
  version_id: string;
  version_no: number;
  parent_version_id: string | null;
  operation_type: "create" | "revise" | "repair";
  revision_instruction: string | null;
  created_at: string;
  diff_summary: Array<Record<string, unknown>>;
}

interface ArtifactVersionsResponse {
  artifact_id: string;
  artifact_type: "fmea";
  versions: ArtifactVersionSummary[];
}

interface ArtifactVersionDetail {
  artifact_id: string;
  version_id: string;
  version_no: number;
  parent_version_id: string | null;
  artifact_type: "fmea";
  output_json: Record<string, unknown>;
  final_markdown: string;
  diff_summary: Array<Record<string, unknown>>;
  verify_result: Record<string, unknown>;
  references: unknown[];
  created_at: string;
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

async function responseError(res: Response) {
  let message = `HTTP ${res.status}`;
  try {
    const data = await res.json();
    if (typeof data.detail === "string") {
      message = data.detail;
    } else if (data.detail?.message) {
      message = data.detail.message;
    }
  } catch {
    // 保持 HTTP 状态兜底
  }
  return message;
}

function formatVersionTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

export default function FMEAGenerator({ sessionId }: Props) {
  const [product, setProduct] = useState("");
  const [process, setProcess] = useState("");
  const [failurePhenomenon, setFailurePhenomenon] = useState("");
  const [background, setBackground] = useState("");
  const [answer, setAnswer] = useState("");
  const [fmeaRunId, setFmeaRunId] = useState<string | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactHistoryItem[]>([]);
  const [versions, setVersions] = useState<ArtifactVersionSummary[]>([]);
  const [currentVersion, setCurrentVersion] =
    useState<ArtifactVersionDetail | null>(null);
  const [currentVersionId, setCurrentVersionId] = useState<string | null>(null);
  const [revisionInstruction, setRevisionInstruction] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [revising, setRevising] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [artifactLoading, setArtifactLoading] = useState(false);
  const artifactRequestRef = useRef(0);

  const canSubmit =
    Boolean(sessionId) &&
    product.trim() &&
    process.trim() &&
    failurePhenomenon.trim() &&
    !submitting;

  const fetchHistory = useCallback(async (targetSessionId: string) => {
    const res = await fetch(
      `/quality/sessions/${targetSessionId}/artifacts?artifact_type=fmea&limit=50`,
      { credentials: "include" },
    );
    if (!res.ok) {
      throw new Error(await responseError(res));
    }
    return (await res.json()) as ArtifactHistoryItem[];
  }, []);

  const loadArtifact = useCallback(async (artifact: ArtifactHistoryItem) => {
    const requestId = ++artifactRequestRef.current;
    setArtifactLoading(true);
    setError("");
    try {
      const versionsRes = await fetch(
        `/quality/artifacts/${artifact.artifact_id}/versions?artifact_type=fmea`,
        { credentials: "include" },
      );
      if (!versionsRes.ok) {
        throw new Error(await responseError(versionsRes));
      }
      const versionData: ArtifactVersionsResponse = await versionsRes.json();
      const selected =
        versionData.versions.find(
          (version) => version.version_id === artifact.latest_version_id,
        ) || versionData.versions.at(-1);
      if (!selected) {
        throw new Error("该 FMEA 暂无可读取版本");
      }

      const detailRes = await fetch(
        `/quality/artifacts/${artifact.artifact_id}/versions/${selected.version_id}?artifact_type=fmea`,
        { credentials: "include" },
      );
      if (!detailRes.ok) {
        throw new Error(await responseError(detailRes));
      }
      const detail: ArtifactVersionDetail = await detailRes.json();
      if (artifactRequestRef.current !== requestId) return;

      setFmeaRunId(artifact.artifact_id);
      setVersions(versionData.versions);
      setCurrentVersionId(detail.version_id);
      setCurrentVersion(detail);
      setAnswer(detail.final_markdown);
      setRevisionInstruction("");
    } catch (err: unknown) {
      if (artifactRequestRef.current === requestId) {
        setError(errorMessage(err, "FMEA 历史加载失败"));
      }
    } finally {
      if (artifactRequestRef.current === requestId) {
        setArtifactLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const requestId = ++artifactRequestRef.current;
    void (async () => {
      await Promise.resolve();
      if (artifactRequestRef.current !== requestId) return;

      setArtifacts([]);
      setFmeaRunId(null);
      setVersions([]);
      setCurrentVersionId(null);
      setCurrentVersion(null);
      setAnswer("");
      setRevisionInstruction("");
      setError("");

      if (!sessionId) {
        setHistoryLoading(false);
        return;
      }

      setHistoryLoading(true);
      try {
        const loadedArtifacts = await fetchHistory(sessionId);
        if (artifactRequestRef.current !== requestId) return;
        setArtifacts(loadedArtifacts);
        setHistoryLoading(false);
        if (loadedArtifacts[0]) {
          await loadArtifact(loadedArtifacts[0]);
        }
      } catch (err: unknown) {
        if (artifactRequestRef.current === requestId) {
          setError(errorMessage(err, "FMEA 历史加载失败"));
          setHistoryLoading(false);
        }
      }
    })();

    return () => {
      artifactRequestRef.current += 1;
    };
  }, [fetchHistory, loadArtifact, sessionId]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!sessionId || !canSubmit) return;

    setSubmitting(true);
    setError("");
    setAnswer("");
    setFmeaRunId(null);
    setVersions([]);
    setCurrentVersionId(null);
    setCurrentVersion(null);
    setRevisionInstruction("");

    try {
      const res = await fetch("/quality/fmea/generate", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          product: product.trim(),
          process: process.trim(),
          failure_phenomenon: failurePhenomenon.trim(),
          background: background.trim(),
        }),
      });

      if (!res.ok) {
        throw new Error(await responseError(res));
      }

      const data: FMEAResponse = await res.json();
      setAnswer(data.final_answer || "");
      const artifactId = data.artifact_id || data.fmea_run_id || null;
      setFmeaRunId(artifactId);
      if (artifactId && sessionId) {
        const loadedArtifacts = await fetchHistory(sessionId);
        setArtifacts(loadedArtifacts);
        const artifact = loadedArtifacts.find((item) => item.artifact_id === artifactId);
        if (artifact) {
          await loadArtifact(artifact);
        }
      }
    } catch (err: unknown) {
      setError(errorMessage(err, "FMEA 生成失败"));
    } finally {
      setSubmitting(false);
    }
  };

  const handleRevision = async (event: FormEvent) => {
    event.preventDefault();
    const instruction = revisionInstruction.trim();
    if (!fmeaRunId || !currentVersion || !instruction || revising) return;

    setRevising(true);
    setError("");
    try {
      const res = await fetch(`/quality/artifacts/${fmeaRunId}/revise`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          artifact_type: "fmea",
          base_version_id: currentVersion.version_id,
          revision_instruction: instruction,
        }),
      });
      if (!res.ok) {
        throw new Error(await responseError(res));
      }

      const newVersion: ArtifactVersionDetail = await res.json();
      const versionSummary: ArtifactVersionSummary = {
        version_id: newVersion.version_id,
        version_no: newVersion.version_no,
        parent_version_id: newVersion.parent_version_id,
        operation_type: "revise",
        revision_instruction: instruction,
        created_at: newVersion.created_at,
        diff_summary: newVersion.diff_summary,
      };
      setVersions((items) => [...items, versionSummary]);
      setCurrentVersionId(newVersion.version_id);
      setCurrentVersion(newVersion);
      setAnswer(newVersion.final_markdown);
      setRevisionInstruction("");
      if (sessionId) {
        setArtifacts(await fetchHistory(sessionId));
      }
    } catch (err: unknown) {
      setError(errorMessage(err, "FMEA 追改失败"));
    } finally {
      setRevising(false);
    }
  };

  const selectVersion = async (version: ArtifactVersionSummary) => {
    if (revising || artifactLoading || !fmeaRunId) return;
    const requestId = ++artifactRequestRef.current;
    setArtifactLoading(true);
    setError("");
    try {
      const res = await fetch(
        `/quality/artifacts/${fmeaRunId}/versions/${version.version_id}?artifact_type=fmea`,
        { credentials: "include" },
      );
      if (!res.ok) {
        throw new Error(await responseError(res));
      }
      const detail: ArtifactVersionDetail = await res.json();
      if (artifactRequestRef.current !== requestId) return;
      setCurrentVersionId(detail.version_id);
      setCurrentVersion(detail);
      setAnswer(detail.final_markdown);
      setRevisionInstruction("");
    } catch (err: unknown) {
      if (artifactRequestRef.current === requestId) {
        setError(errorMessage(err, "FMEA 版本加载失败"));
      }
    } finally {
      if (artifactRequestRef.current === requestId) {
        setArtifactLoading(false);
      }
    }
  };

  return (
    <div className="fmea-page">
      <div className="fmea-header">
        <div>
          <h2>FMEA生成</h2>
          <p>XF质量 · PFMEA 生成</p>
        </div>
      </div>

      <form className="fmea-form" onSubmit={handleSubmit}>
        <div className="fmea-form-grid">
          <label className="fmea-field">
            <span>产品/对象</span>
            <input
              value={product}
              onChange={(e) => setProduct(e.target.value)}
              placeholder="例如：汽车座椅滑轨冲压件"
              disabled={submitting}
            />
          </label>

          <label className="fmea-field">
            <span>工序</span>
            <input
              value={process}
              onChange={(e) => setProcess(e.target.value)}
              placeholder="例如：拉伸、翻边、落料"
              disabled={submitting}
            />
          </label>

          <label className="fmea-field">
            <span>问题现象</span>
            <input
              value={failurePhenomenon}
              onChange={(e) => setFailurePhenomenon(e.target.value)}
              placeholder="例如：开裂、毛刺、尺寸超差"
              disabled={submitting}
            />
          </label>

          <label className="fmea-field fmea-field-wide">
            <span>补充背景</span>
            <textarea
              value={background}
              onChange={(e) => setBackground(e.target.value)}
              placeholder="材料、批量、设备、客户要求等，可选"
              disabled={submitting}
              rows={4}
            />
          </label>
        </div>

        <div className="fmea-actions">
          <button className="fmea-submit" type="submit" disabled={!canSubmit}>
            {submitting ? "生成中..." : "生成 FMEA"}
          </button>
          {!sessionId && <span className="fmea-note">请先创建或选择一个会话</span>}
        </div>
      </form>

      <section className="artifact-history">
        <div className="artifact-history-heading">
          <div>
            <div className="fmea-result-title">当前会话 FMEA 历史</div>
            <div className="artifact-version-time">数据来自业务产物与版本记录</div>
          </div>
          {historyLoading && <span className="fmea-note">加载中...</span>}
        </div>
        {!historyLoading && artifacts.length === 0 ? (
          <div className="artifact-history-empty">当前会话暂无 FMEA 产物</div>
        ) : (
          <div className="artifact-history-list">
            {artifacts.map((artifact) => (
              <button
                key={artifact.artifact_id}
                type="button"
                className={artifact.artifact_id === fmeaRunId ? "active" : ""}
                onClick={() => void loadArtifact(artifact)}
                disabled={artifactLoading || revising}
              >
                <strong>{artifact.title}</strong>
                <span>
                  {artifact.latest_version_no
                    ? `最新 V${artifact.latest_version_no}`
                    : "暂无版本"}
                  {" · "}
                  {formatVersionTime(artifact.updated_at)}
                </span>
                {artifact.summary && <small>{artifact.summary}</small>}
              </button>
            ))}
          </div>
        )}
      </section>

      {error && <div className="fmea-error">{error}</div>}

      {answer && (
        <div className="fmea-result">
          <div className="fmea-result-heading">
            <div>
              <div className="fmea-result-title">生成结果</div>
              {currentVersion && (
                <div className="artifact-version-time">
                  当前版本 V{currentVersion.version_no} ·{" "}
                  {formatVersionTime(currentVersion.created_at)}
                </div>
              )}
            </div>
            {versions.length > 0 && (
              <div className="artifact-version-list" aria-label="版本切换">
                {versions.map((version) => (
                  <button
                    key={version.version_id}
                    type="button"
                    className={
                      version.version_id === currentVersionId ? "active" : ""
                    }
                    onClick={() => selectVersion(version)}
                    disabled={revising || artifactLoading}
                    title={formatVersionTime(version.created_at)}
                  >
                    V{version.version_no}
                  </button>
                ))}
              </div>
            )}
          </div>
          {fmeaRunId && (
            <div className="artifact-run-id">
              已保存为 FMEA 业务产物：<strong>{fmeaRunId}</strong>
            </div>
          )}
          <div className="message-content">
            <Markdown content={answer} citations={[]} />
          </div>

          {currentVersion && currentVersion.diff_summary.length > 0 && (
            <div className="artifact-diff-summary">
              <strong>本次修改摘要</strong>
              <ul>
                {currentVersion.diff_summary.map((item, index) => (
                  <li key={`${String(item.section || "change")}-${index}`}>
                    {String(item.summary || item.section || "已更新")}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {currentVersion && (
            <form className="artifact-revision-form" onSubmit={handleRevision}>
              <label className="fmea-field">
                <span>继续修改（基于 V{currentVersion.version_no}）</span>
                <textarea
                  value={revisionInstruction}
                  onChange={(event) => setRevisionInstruction(event.target.value)}
                  placeholder="例如：把建议措施写得更具体，不能只写加强检查"
                  disabled={revising}
                  rows={3}
                />
              </label>
              <div className="fmea-actions">
                <button
                  className="fmea-submit"
                  type="submit"
                  disabled={!revisionInstruction.trim() || revising}
                >
                  {revising ? "生成新版本中..." : "生成新版本"}
                </button>
                <span className="fmea-note">
                  新版本不会覆盖 V{currentVersion.version_no}
                </span>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  );
}

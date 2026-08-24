import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  createSalesProposal,
  getSalesProposalWithSteps,
  SalesProposalRequestError,
  SalesProposalStepsError,
  type CollaborationRunWithSteps,
} from "../api/salesProposal";
import type {
  CollaborationStep,
  JsonValue,
} from "../types/salesProposal";
import {
  getTaskStatusDescription,
  getTaskStatusLabel,
  isCompletedStatus,
  isFailedStatus,
  isRunningStatus,
  isTerminalStatus,
} from "../utils/taskStatus";

type PageState = "idle" | "submitting" | "loading" | "success" | "error";

const POLL_INTERVAL_MS = 2000;

interface Props {
  runId: string | null;
  onRunIdChange: (runId: string) => void;
  onNewProposal: () => void;
}

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

function errorMessage(error: unknown) {
  if (
    error instanceof SalesProposalRequestError &&
    error.status === 404
  ) {
    return "任务不存在或无权限访问";
  }
  return error instanceof Error ? error.message : "售前方案请求失败";
}

function jsonText(value: JsonValue | Record<string, JsonValue>) {
  return JSON.stringify(value, null, 2);
}

function stringList(value: JsonValue | undefined): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}

function StepItem({ step }: { step: CollaborationStep }) {
  return (
    <article className="sales-step">
      <div className="sales-step-heading">
        <div>
          <strong>{step.step_name}</strong>
          <span>{step.agent}</span>
        </div>
        <span className={`sales-status sales-status-${step.status}`}>
          {step.status}
        </span>
      </div>

      {step.error && <div className="sales-step-error">{step.error}</div>}

      {step.output_json !== null && (
        <details className="sales-json-details">
          <summary>查看输出</summary>
          <pre>{jsonText(step.output_json)}</pre>
        </details>
      )}
    </article>
  );
}

export default function SalesProposalPage({
  runId,
  onRunIdChange,
  onNewProposal,
}: Props) {
  const [userRequest, setUserRequest] = useState("");
  const [pageState, setPageState] = useState<PageState>("idle");
  const [run, setRun] = useState<CollaborationRunWithSteps | null>(null);
  const [error, setError] = useState("");
  const [copyMessage, setCopyMessage] = useState("");
  const loadRequestRef = useRef(0);
  const mountedRef = useRef(true);
  const pollTimerRef = useRef<number | null>(null);

  const taskRunning = Boolean(run && isRunningStatus(run.status));
  const busy =
    pageState === "submitting" || pageState === "loading" || taskRunning;
  const manualCheckItems = run
    ? run.manual_check_items ??
      stringList(run.review_result.manual_check_items)
    : [];
  const failedMessage =
    run && isFailedStatus(run.status)
      ? run.error || "任务执行失败，但未返回具体错误"
      : "";

  const clearPollTimer = useCallback(() => {
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const requestId = ++loadRequestRef.current;
    let cancelled = false;

    const loadRun = async (targetRunId: string) => {
      try {
        const loadedRun = await getSalesProposalWithSteps(targetRunId);
        if (cancelled || loadRequestRef.current !== requestId) return;

        setRun(loadedRun);
        setUserRequest(loadedRun.user_request);
        setError("");
        setPageState("success");

        if (!isTerminalStatus(loadedRun.status)) {
          clearPollTimer();
          pollTimerRef.current = window.setTimeout(() => {
            pollTimerRef.current = null;
            void loadRun(targetRunId);
          }, POLL_INTERVAL_MS);
        }
      } catch (loadError: unknown) {
        if (cancelled || loadRequestRef.current !== requestId) return;
        clearPollTimer();
        if (loadError instanceof SalesProposalStepsError) {
          setRun({ ...loadError.run, steps: [] });
          setUserRequest(loadError.run.user_request);
        }
        setError(errorMessage(loadError));
        setPageState("error");
      }
    };

    void (async () => {
      await Promise.resolve();
      if (cancelled || loadRequestRef.current !== requestId) return;

      if (!runId) {
        clearPollTimer();
        setRun(null);
        setError("");
        setCopyMessage("");
        setPageState("idle");
        return;
      }

      setRun(null);
      setError("");
      setCopyMessage("");
      setPageState("loading");

      await loadRun(runId);
    })();

    return () => {
      cancelled = true;
      clearPollTimer();
      if (loadRequestRef.current === requestId) {
        loadRequestRef.current += 1;
      }
    };
  }, [clearPollTimer, runId]);

  const handleNewProposal = () => {
    clearPollTimer();
    loadRequestRef.current += 1;
    setUserRequest("");
    setRun(null);
    setError("");
    setCopyMessage("");
    setPageState("idle");
    onNewProposal();
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopyMessage("任务链接已复制");
    } catch {
      setCopyMessage("复制失败，请手动复制浏览器地址");
    }
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;

    const request = userRequest.trim();

    if (!request) {
      setError("请输入客户综合售前需求");
      setPageState("error");
      return;
    }

    setRun(null);
    setError("");
    setPageState("submitting");

    try {
      const created = await createSalesProposal({ user_request: request });
      if (!mountedRef.current) return;
      onRunIdChange(created.run_id);
    } catch (requestError: unknown) {
      if (!mountedRef.current) return;
      setError(errorMessage(requestError));
      setPageState("error");
    }
  };

  return (
    <main className="fmea-page sales-proposal-page">
      <header className="fmea-header">
        <div>
          <h2>售前方案</h2>
          <p>综合售前需求协作分析与方案生成</p>
        </div>
        <div className="sales-header-actions">
          {runId && (
            <button
              className="report-refresh"
              type="button"
              onClick={handleCopyLink}
            >
              复制任务链接
            </button>
          )}
          <button
            className="report-refresh"
            type="button"
            onClick={handleNewProposal}
          >
            新建方案
          </button>
          {copyMessage && (
            <span className="sales-copy-message">{copyMessage}</span>
          )}
        </div>
      </header>

      <form className="fmea-form" onSubmit={handleSubmit}>
        <div className="fmea-form-grid">
          <label className="fmea-field fmea-field-wide">
            <span>客户综合售前需求</span>
            <textarea
              value={userRequest}
              onChange={(event) => setUserRequest(event.target.value)}
              placeholder="请输入客户背景、产品需求、技术约束、质量目标和交付要求等信息"
              disabled={busy}
              rows={8}
            />
          </label>
        </div>

        <div className="fmea-actions">
          <button className="fmea-submit" type="submit" disabled={busy}>
            {pageState === "submitting"
              ? "正在生成..."
              : pageState === "loading"
                ? "正在读取任务..."
                : "生成售前方案"}
          </button>
          {busy && pageState !== "error" && (
            <span className="fmea-note">
              {pageState === "submitting"
                ? "协作任务执行中，请稍候"
                : pageState === "loading"
                  ? "正在读取任务详情和步骤"
                  : "任务执行中，状态将自动刷新"}
            </span>
          )}
        </div>
      </form>

      {error && <div className="fmea-error">{error}</div>}
      {failedMessage && (
        <div className="fmea-error">{failedMessage}</div>
      )}

      {run && (
        <div className="sales-results">
          <section className="fmea-result">
            <div className="fmea-result-title">当前任务信息</div>
            <dl className="sales-meta-grid">
              <div>
                <dt>run_id</dt>
                <dd>{run.run_id}</dd>
              </div>
              <div>
                <dt>status</dt>
                <dd>
                  <span className={`sales-status sales-status-${run.status}`}>
                    {getTaskStatusLabel(run.status)}
                  </span>
                  <div className="sales-status-description">
                    {getTaskStatusDescription(run.status)}
                  </div>
                </dd>
              </div>
              <div>
                <dt>created_at</dt>
                <dd>{formatTime(run.created_at)}</dd>
              </div>
              <div>
                <dt>updated_at</dt>
                <dd>{formatTime(run.updated_at)}</dd>
              </div>
              <div className="sales-meta-wide">
                <dt>error</dt>
                <dd>{failedMessage || run.error || "无"}</dd>
              </div>
            </dl>
          </section>

          <section className="fmea-result">
            <div className="fmea-result-title">Agent 步骤</div>
            {run.steps.length > 0 ? (
              <div className="sales-step-list">
                {run.steps.map((step) => (
                  <StepItem key={step.step_id} step={step} />
                ))}
              </div>
            ) : (
              <p className="sales-empty">暂无步骤记录</p>
            )}
          </section>

          <section className="fmea-result">
            <div className="fmea-result-title">最终报告</div>
            {run.final_report ? (
              <pre className="sales-report">{run.final_report}</pre>
            ) : (
              <p className="sales-empty">
                {isCompletedStatus(run.status)
                  ? "任务已完成，但未返回最终报告"
                  : "暂无最终报告"}
              </p>
            )}
          </section>

          <section className="fmea-result">
            <div className="fmea-result-title">引用依据</div>
            {run.citations.length > 0 ? (
              <div className="sales-citation-list">
                {run.citations.map((citation, index) => (
                  <pre key={index}>{jsonText(citation)}</pre>
                ))}
              </div>
            ) : (
              <p className="sales-empty">暂无引用依据</p>
            )}
          </section>

          <section className="fmea-result">
            <div className="fmea-result-title">人工确认项</div>
            {manualCheckItems.length > 0 ? (
              <ul className="report-list">
                {manualCheckItems.map((item, index) => (
                  <li key={`${index}-${item}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="sales-empty">暂无人工确认项</p>
            )}
          </section>
        </div>
      )}
    </main>
  );
}

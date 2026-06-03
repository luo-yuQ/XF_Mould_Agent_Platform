import { useState, type FormEvent } from "react";
import Markdown from "./Markdown";

interface Props {
  sessionId: string | null;
}

interface FMEAResponse {
  final_answer: string;
  fmea_rows: Array<Record<string, unknown>>;
  verify_result: Record<string, unknown>;
}

export default function FMEAGenerator({ sessionId }: Props) {
  const [product, setProduct] = useState("");
  const [process, setProcess] = useState("");
  const [failurePhenomenon, setFailurePhenomenon] = useState("");
  const [background, setBackground] = useState("");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const canSubmit =
    Boolean(sessionId) &&
    product.trim() &&
    process.trim() &&
    failurePhenomenon.trim() &&
    !submitting;

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!sessionId || !canSubmit) return;

    setSubmitting(true);
    setError("");
    setAnswer("");

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
        let message = `HTTP ${res.status}`;
        try {
          const data = await res.json();
          message = data.detail || message;
        } catch {
          // 保持 HTTP 状态兜底
        }
        throw new Error(message);
      }

      const data: FMEAResponse = await res.json();
      setAnswer(data.final_answer || "");
    } catch (err: any) {
      setError(err.message || "FMEA 生成失败");
    } finally {
      setSubmitting(false);
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

      {error && <div className="fmea-error">{error}</div>}

      {answer && (
        <div className="fmea-result">
          <div className="fmea-result-title">生成结果</div>
          <div className="message-content">
            <Markdown content={answer} citations={[]} />
          </div>
        </div>
      )}
    </div>
  );
}

import type { Citation } from "../types";

interface Props {
  content: string;
  citations: Citation[];
}

/** 简易 Markdown 渲染（含引用标记 [N] 渲染为可悬停锚点） */
export default function Markdown({ content, citations }: Props) {
  if (!content) return null;

  const escapeHtml = (text: string) =>
    text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

  const humanizeSource = (raw: string) => {
    const parts = raw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => {
        const audit = item.match(/^Audit\s+Finding\s+(\d+)$/i);
        if (audit) return "审核发现";

        const fmea = item.match(/^FMEA\s+(?:Row|Finding)\s+(\d+)$/i);
        if (fmea) return "FMEA 分析结果";

        const rag = item.match(/^RAG\s+(.+)$/i);
        if (rag) {
          const sourceId = rag[1];
          return sourceId.toLowerCase().includes("vda")
            ? "VDA6.4 检索依据"
            : sourceId.toLowerCase().includes("fmea")
              ? "FMEA 检索依据"
              : "检索依据";
        }

        return item;
      });

    return parts.join("、");
  };

  // 清洗 LLM 输出的字面量 <br> 和被转义的 Markdown 粗体标记。
  let result = escapeHtml(content.replace(/\\\*/g, "*"))
    .replace(/&lt;br\s*\/?&gt;/gi, "<br/>");

  // 代码块 ```...```
  result = result.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) => {
    return `<pre><code class="language-${lang}">${escapeHtml(code.trim())}</code></pre>`;
  });

  // 行内代码 `...`
  result = result.replace(/`([^`]+)`/g, "<code>$1</code>");

  // 粗体 **...**
  result = result.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // 报告来源标记：[来源: Audit Finding 1, RAG vda6.4_table_000534]
  result = result.replace(/\[来源[:：]\s*([^\]]+)\]/g, (_m, raw) => {
    const label = humanizeSource(raw);
    const title = `原始来源：${raw}`;
    return `<span class="source-ref" title="${escapeHtml(title)}">${escapeHtml(label)}</span>`;
  });

  // 标题 ### ...
  result = result.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  result = result.replace(/^## (.+)$/gm, "<h2>$1</h2>");

  // 引用标记 [N] → <sup> 脚注锚点（含悬停 tooltip）
  result = result.replace(/\[(\d+)\]/g, (_m, idStr) => {
    const id = parseInt(idStr);
    const cit = citations.find((c) => c.id === id);
    const title = cit
      ? `${cit.source}${cit.heading_path ? " · " + cit.heading_path : cit.chapter ? " · 第" + cit.chapter + "章 " + cit.section_title : ""}${cit.row_range ? " (行" + cit.row_range + ")" : ""}`
      : `引用文献 ${id}`;
    return `<sup class="citation-ref" title="${escapeHtml(title)}">[${id}]</sup>`;
  });

  // 表格简译：| ... | 转为 HTML 表格（支持多个表格）
  if (result.includes("|")) {
    const lines = result.split("\n");
    const segments: string[] = [];
    const tableLines: string[] = [];

    for (const line of lines) {
      if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
        tableLines.push(line);
      } else {
        if (tableLines.length >= 2) {
          segments.push(_renderTable(tableLines));
          tableLines.length = 0;
        }
        segments.push(line);
      }
    }
    if (tableLines.length >= 2) {
      segments.push(_renderTable(tableLines));
    }

    result = segments.join("\n");
  }

  // 换行
  result = result.replace(/\n/g, "<br/>");

  // 水平线
  result = result.replace(/^---$/gm, "<hr/>");

  return <div dangerouslySetInnerHTML={{ __html: result }} />;
}

function _renderTable(lines: string[]): string {
  if (lines.length < 2) return lines.join("\n");

  const parseRow = (line: string) =>
    line
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((c) => c.trim());

  const headerLine = lines[0];
  const dataLines = lines.slice(
    lines[1].replace(/\|/g, "").replace(/\s/g, "").match(/^[-:]+$/) ? 2 : 1
  );

  const headers = parseRow(headerLine);
  let html = "<table><thead><tr>";
  for (const h of headers) {
    html += `<th>${h}</th>`;
  }
  html += "</tr></thead><tbody>";
  for (const line of dataLines) {
    html += "<tr>";
    const cells = parseRow(line);
    for (const c of cells) {
      html += `<td>${c}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  return `<div class="markdown-table-wrapper">${html}</div>`;
}

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

  let result = escapeHtml(content);

  // 代码块 ```...```
  result = result.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) => {
    return `<pre><code class="language-${lang}">${escapeHtml(code.trim())}</code></pre>`;
  });

  // 行内代码 `...`
  result = result.replace(/`([^`]+)`/g, "<code>$1</code>");

  // 粗体 **...**
  result = result.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

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

  // 表格简译：| ... | 转为 HTML 表格
  if (result.includes("|")) {
    const lines = result.split("\n");
    const tableLines: string[] = [];
    let tableHtml = "";

    for (const line of lines) {
      if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
        tableLines.push(line);
      } else {
        if (tableLines.length >= 2) {
          tableHtml += _renderTable(tableLines);
        }
        tableLines.length = 0;
      }
    }
    if (tableLines.length >= 2) {
      tableHtml += _renderTable(tableLines);
    }

    if (tableHtml) {
      const firstTableStart = lines.findIndex(
        (l) => l.trim().startsWith("|") && l.trim().endsWith("|")
      );
      const firstTableEnd =
        lines
          .slice(firstTableStart)
          .findIndex(
            (l, i) =>
              i > 0 &&
              !l.trim().startsWith("|") &&
              !lines[firstTableStart + i + 1]?.trim().startsWith("|")
          ) + firstTableStart;

      if (firstTableStart >= 0 && firstTableEnd > firstTableStart) {
        const before = lines.slice(0, firstTableStart).join("\n");
        const after = lines.slice(firstTableEnd + 1).join("\n");
        result = before + "\n" + tableHtml + "\n" + after;
      }
    }
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
    lines[1].replace(/\|/g, "").trim().match(/^[-:]+$/) ? 2 : 1
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
  return html;
}

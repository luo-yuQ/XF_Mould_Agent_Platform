"""
PDF 文档解析器
- 按页读取 PDF 文字层（默认不 OCR）
- 两轮扫描去除跨页重复的页眉页脚
- 正则识别章节标题（含 M/C/S 过程编号）
- 表格检测（验真后保留，不强信）
- 输出与 DOCX 解析器兼容的 block 序列
"""
import re
from collections import defaultdict
from typing import Optional

import fitz


def _clean_text(text: str) -> str:
    """合并多余空白字符"""
    return re.sub(r'\s+', ' ', text).strip()


def _is_heading(text: str) -> Optional[tuple[int, str, str]]:
    """
    检测是否为标题，返回 (level, number, title) 或 None
    level: 1=章级, 2=节级, 3=子节级
    """
    stripped = text.strip()
    if not stripped:
        return None

    # 1.0 / 2.0 → level 1（章）
    m = re.match(r'^(\d+\.0)\s+(.+)$', stripped)
    if m:
        return (1, m.group(1), m.group(2))

    # 1.1 / 8.5 → level 2（节）
    m = re.match(r'^(\d+\.\d+)\s+(.+)$', stripped)
    if m:
        return (2, m.group(1), m.group(2))

    # 1.1.1 → level 3（子节）
    m = re.match(r'^(\d+\.\d+\.\d+)\s+(.+)$', stripped)
    if m:
        return (3, m.group(1), m.group(2))

    # 纯数字 "2 失效模式分析" → level 1
    m = re.match(r'^(\d+)\s+(.+)$', stripped)
    if m and len(m.group(1)) <= 2:
        return (1, m.group(1), m.group(2))

    # M1 / C1 / S12 → level 2（过程级，不当作一级章节硬切）
    m = re.match(r'^([MCS]\d+)\s+(.+)$', stripped)
    if m:
        return (2, m.group(1), m.group(2))

    # M1.1 / C1.1 / S12.1 → level 3
    m = re.match(r'^([MCS]\d+\.\d+)\s+(.+)$', stripped)
    if m:
        return (3, m.group(1), m.group(2))

    return None


# =============================================================================
# 页眉页脚检测：基于跨页重复，不做位置硬切
# =============================================================================

def _is_page_number(text: str) -> bool:
    """纯页码类（逐页变化，不属于内容）"""
    t = text.strip()
    if re.match(r'^\d+$', t):
        return True
    if re.match(r'^第\s*\d+\s*页', t):
        return True
    if re.match(r'^\d+\s*/\s*\d+$', t):
        return True
    if re.match(r'^-\s*\d+\s*-$', t):
        return True
    return False


def _detect_repeated_lines(doc: fitz.Document,
                           min_repeat_pct: float = 0.75) -> set:
    """
    扫描所有页，找出在 >min_repeat_pct 页面中「相同文本 + 相同 y 位置」
    重复出现的行。这些行极大概率是页眉页脚。
    返回 set of (text, y_bucket) 。
    """
    total = len(doc)
    if total <= 3:
        return set()

    pos_map: dict[tuple[str, int], set] = defaultdict(set)

    for pg in range(total):
        page = doc[pg]
        text_dict = page.get_text("dict")
        seen = set()
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                raw = "".join(s.get("text", "") for s in line.get("spans", []))
                text = _clean_text(raw)
                if not text or len(text) <= 3:
                    continue
                y_bucket = round(line["bbox"][1] / 15) * 15
                key = (text, y_bucket)
                if key not in seen:
                    seen.add(key)
                    pos_map[key].add(pg)

    threshold = total * min_repeat_pct
    return {k for k, v in pos_map.items() if len(v) >= threshold}


# =============================================================================
# 表格处理
# =============================================================================

def _is_valid_table(table_data: list[list]) -> bool:
    """轻量验真：真正的表至少 ≥2 行 2 列，且填充率 >30%"""
    if not table_data or len(table_data) < 2:
        return False
    if not table_data[0] or len(table_data[0]) < 2:
        return False

    filled = 0
    total = 0
    for row in table_data:
        for cell in row:
            total += 1
            if cell and cell.strip():
                filled += 1
    if total == 0:
        return False
    return filled / total > 0.3


def _table_to_markdown(table_data: list[list]) -> str:
    """将 PyMuPDF 表格数据转为 Markdown"""
    if not table_data:
        return ""
    rows = []
    for row in table_data:
        cells = []
        for cell in row:
            if cell is None:
                cells.append("")
            else:
                cells.append(cell.strip().replace("\n", " ").replace("|", "\\|"))
        rows.append(cells)

    max_cols = max((len(r) for r in rows), default=0)
    if max_cols == 0:
        return ""
    for r in rows:
        while len(r) < max_cols:
            r.append("")

    lines = []
    for i, row in enumerate(rows):
        lines.append("| " + " | ".join(row) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    return "\n".join(lines)


# =============================================================================
# 标题栈
# =============================================================================

def _build_path(stack: list) -> dict:
    """从标题栈构建 path 字典（与 DOCX HeadingTracker 兼容）"""
    if not stack:
        return {"chapter": "", "section_title": "", "heading_path": ""}
    return {
        "chapter": stack[-1]["number"],
        "section_title": stack[-1]["title"],
        "heading_path": " > ".join(
            f"{s['number']} {s['title']}" for s in stack
        ),
    }


# =============================================================================
# 主入口
# =============================================================================

def parse_pdf_blocks(filepath: str) -> list[dict]:
    """
    解析 PDF 文档，输出 block 序列。

    两轮扫描：
      1. 检测跨页重复的页眉页脚
      2. 提取正文、标题、表格

    返回的 block 格式与 parse_docx_blocks 完全兼容：
      - type: heading / paragraph / table
      - path: { chapter, section_title, heading_path }
      - page / page_start / page_end
    """
    blocks: list[dict] = []
    stack: list[dict] = []

    doc = fitz.open(filepath)

    # ============ Phase 1: 检测页眉页脚 ============
    repeated_lines = _detect_repeated_lines(doc)

    # ============ Phase 2: 逐页构建 blocks ============
    for page_num, page in enumerate(doc, 1):
        # ---- 2a. 提取文字行（过滤 h/f 和页码） ----
        text_dict = page.get_text("dict")
        content_lines: list[tuple[str, float]] = []  # (text, top)

        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:  # 跳过图片块
                continue
            for line in block.get("lines", []):
                raw = "".join(s.get("text", "") for s in line.get("spans", []))
                text = _clean_text(raw)
                if not text:
                    continue

                y_bucket = round(line["bbox"][1] / 15) * 15

                # 跨页重复 → 页眉页脚
                if (text, y_bucket) in repeated_lines:
                    continue
                # 纯页码
                if _is_page_number(text):
                    continue

                content_lines.append((text, line["bbox"][1]))

        # ---- 2b. 组 block：连续非标题行合为一个段落 ----
        para_buffer: list[str] = []

        def flush_para():
            if para_buffer:
                joined = "".join(para_buffer)
                blocks.append({
                    "type": "paragraph",
                    "text": joined,
                    "path": _build_path(stack),
                    "page_start": page_num,
                    "page_end": page_num,
                })
                para_buffer.clear()

        for line_text, _ in content_lines:
            heading_info = _is_heading(line_text)
            if heading_info:
                flush_para()
                level, number, title = heading_info

                while stack and stack[-1]["level"] >= level:
                    stack.pop()
                stack.append({"level": level, "number": number, "title": title})

                blocks.append({
                    "type": "heading",
                    "level": level,
                    "number": number,
                    "title": title,
                    "text": line_text,
                    "page": page_num,
                    "path": _build_path(stack),
                })
            else:
                para_buffer.append(line_text)

        flush_para()

        # ---- 2c. 表格（双轨：不覆盖文字，验真后单独追加） ----
        try:
            tables = page.find_tables()
            for table in tables:
                raw = table.extract()
                if _is_valid_table(raw):
                    md = _table_to_markdown(raw)
                    if md.strip():
                        blocks.append({
                            "type": "table",
                            "markdown": md,
                            "path": _build_path(stack),
                            "page_start": page_num,
                            "page_end": page_num,
                        })
        except Exception:
            pass  # 表格识别失败不丢内容，文字已保留

    doc.close()
    return blocks

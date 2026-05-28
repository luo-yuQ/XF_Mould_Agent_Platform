"""
PDF 解析器分块测试 —— 决策树报文分类算法.pdf

用法:
    python tests/test_pdf_chunking.py

输出:
    test_output/chunks.jsonl      — 每条 chunk 一行 JSON
    test_output/parse_report.json — 解析报告（含逐页统计、验证结果）

依赖:
    pip install PyMuPDF
"""

import sys
import os
import json
import random
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from knowledge.pdf_parser import parse_pdf_blocks
import fitz

# ============================================================
# 配置
# ============================================================
import argparse
import re

# 默认 PDF
DEFAULT_PDF = os.path.join(PROJECT_ROOT, "papers", "决策树报文分类算法.pdf")
OUTPUT_BASE = os.path.join(PROJECT_ROOT, "test_output")

parser = argparse.ArgumentParser(description="PDF 分块测试")
parser.add_argument("pdf_path", nargs="?", default=DEFAULT_PDF, help="PDF 文件路径")
args = parser.parse_args()
PDF_PATH = args.pdf_path

# 按文件名生成输出子目录
pdf_stem = os.path.splitext(os.path.basename(PDF_PATH))[0]
pdf_slug = re.sub(r'[^\w一-鿿]+', '_', pdf_stem).strip('_')[:40]
OUTPUT_DIR = os.path.join(OUTPUT_BASE, pdf_slug)

LOW_TEXT_THRESHOLD = 50  # 字符数低于此值视为"低文字页"


# ============================================================
# 1. 逐页原始统计（与 parse_pdf_blocks 独立，用于交叉验证）
# ============================================================
def collect_page_stats(filepath: str) -> dict:
    """打开 PDF 逐页采集原始文本和表格数，用于报告和残留检测。"""
    doc = fitz.open(filepath)
    stats = {}
    for pg in range(len(doc)):
        page = doc[pg]
        text = page.get_text("text")
        try:
            tables = page.find_tables()
            tbl_count = len(tables.tables) if hasattr(tables, "tables") else len(list(tables))
        except Exception:
            tbl_count = 0
        stats[pg + 1] = {
            "raw_chars": len(text),
            "raw_text": text,
            "raw_table_count": tbl_count,
        }
    doc.close()
    return stats


# ============================================================
# 2. 块 → chunk 转换
# ============================================================
def blocks_to_chunks(blocks: list[dict]) -> list[dict]:
    """将 parser 输出的 block 序列转为统一 chunk 格式。"""
    chunks: list[dict] = []
    current_heading = ""

    for block in blocks:
        if block["type"] == "heading":
            current_heading = block["path"].get("heading_path", "")
            continue

        page_start = block.get("page_start", 1)
        page_end = block.get("page_end", 1)

        if block["type"] == "paragraph":
            text = block["text"]
            if not text.strip():
                continue
            chunks.append({
                "text": text,
                "page_start": page_start,
                "page_end": page_end,
                "heading": current_heading,
                "chunk_type": "text",
            })

        elif block["type"] == "table":
            md = block.get("markdown", "")
            if not md.strip():
                continue
            chunks.append({
                "text": md,
                "page_start": page_start,
                "page_end": page_end,
                "heading": current_heading,
                "chunk_type": "table",
            })

    return chunks


# ============================================================
# 3. 验证
# ============================================================
def check_header_footer_leakage(page_stats: dict, chunks: list[dict]) -> list[str]:
    """
    从原始文本提取跨 >75% 页面重复的行（页眉页脚特征），
    检查 chunks 中是否仍有残留。返回残留文本列表。
    """
    total = len(page_stats)
    if total <= 3:
        return []

    pos_map: dict[str, set] = defaultdict(set)
    for pg, info in page_stats.items():
        seen = set()
        for line in info["raw_text"].split("\n"):
            t = line.strip()
            if not t or len(t) <= 3:
                continue
            if t not in seen:
                seen.add(t)
                pos_map[t].add(pg)

    threshold = total * 0.75
    repeated = {k for k, v in pos_map.items() if len(v) >= threshold}

    leaks: list[str] = []
    for line in repeated:
        for chunk in chunks:
            if line in chunk["text"]:
                leaks.append(line)
                break
    return leaks


def run_validation(chunks: list[dict], blocks: list[dict],
                   page_stats: dict, leaks: list[str]) -> dict:
    """运行全部验证项，返回结果字典。"""
    results = {}

    # 4a. chunk 数量
    assert len(chunks) > 0, "chunk 数量应为正"
    results["chunk_count_ok"] = len(chunks) > 0

    # 4b. 页面范围合理
    pages = set()
    for c in chunks:
        pages.add(c["page_start"])
        pages.add(c["page_end"])
    doc_page_count = len(page_stats)
    page_min = min(pages) if pages else 0
    page_max = max(pages) if pages else 0
    results["page_range"] = f"{page_min}-{page_max}"
    results["page_range_ok"] = (
        page_min >= 1 and page_max <= doc_page_count and page_min <= page_max
    )

    # 4c. 标题识别
    headings = [b for b in blocks if b["type"] == "heading"]
    results["heading_count"] = len(headings)
    results["heading_numbers"] = [h["number"] for h in headings]

    # 4d. 表格捕获
    tables = [b for b in blocks if b["type"] == "table"]
    results["table_count"] = len(tables)
    results["tables_captured"] = len(tables) > 0

    # 4e. 页眉页脚残留
    results["header_footer_leakage"] = len(leaks)
    results["no_header_footer_leakage"] = len(leaks) == 0

    # 4f. 无效页面范围
    bad_range = [c for c in chunks if c["page_start"] > c["page_end"]]
    results["invalid_page_range_chunks"] = len(bad_range)

    return results


# ============================================================
# 4. 主流程
# ============================================================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("PDF 分块测试")
    print(f"文件: {PDF_PATH}")
    print("=" * 60)

    # ---- 1. 逐页统计 ----
    print("\n[1/4] 逐页统计...")
    page_stats = collect_page_stats(PDF_PATH)
    print(f"  总页数: {len(page_stats)}")

    # ---- 2. 解析 blocks ----
    print("\n[2/4] 解析文档结构...")
    blocks = parse_pdf_blocks(PDF_PATH)
    headings = [b for b in blocks if b["type"] == "heading"]
    tables = [b for b in blocks if b["type"] == "table"]
    paras = [b for b in blocks if b["type"] == "paragraph"]
    print(f"  {len(blocks)} blocks: {len(headings)} 标题, {len(tables)} 表格, {len(paras)} 段落")

    for h in headings:
        print(f"    [{h['level']}] {h['number']} {h['title']}")

    # ---- 3. 生成 chunks ----
    print("\n[3/4] 生成 chunks...")
    chunks = blocks_to_chunks(blocks)
    text_chunks = [c for c in chunks if c["chunk_type"] == "text"]
    table_chunks = [c for c in chunks if c["chunk_type"] == "table"]
    print(f"  {len(chunks)} chunks: {len(text_chunks)} 文本, {len(table_chunks)} 表格")

    # ---- 4. 验证 ----
    print("\n[4/4] 验证...")
    leaks = check_header_footer_leakage(page_stats, chunks)
    validation = run_validation(chunks, blocks, page_stats, leaks)

    for key, val in validation.items():
        if isinstance(val, bool):
            mark = "[OK]" if val else "[FAIL]"
            print(f"  {mark} {key}")
        else:
            print(f"  .   {key}: {val}")

    if leaks:
        print(f"  [WARN] 页眉页脚疑似残留 ({len(leaks)} 处):")
        for l in leaks[:5]:
            print(f"      -> '{l[:80]}'")

    # ---- 构建报告 ----
    print("\n构建报告...")
    low_text_pages: list[int] = []
    per_page: dict[str, dict] = {}
    for pg in range(1, len(page_stats) + 1):
        s = page_stats[pg]
        page_chars = sum(
            len(c["text"])
            for c in chunks
            if c["page_start"] <= pg <= c["page_end"]
        )
        page_tables = sum(
            1 for c in chunks
            if c["chunk_type"] == "table"
            and c["page_start"] <= pg <= c["page_end"]
        )
        per_page[str(pg)] = {
            "raw_chars": s["raw_chars"],
            "effective_chars": page_chars,
            "table_count": page_tables,
            "raw_table_count": s["raw_table_count"],
        }
        if page_chars < LOW_TEXT_THRESHOLD and page_tables == 0:
            low_text_pages.append(pg)

    report = {
        "source_file": os.path.basename(PDF_PATH),
        "total_pages": len(page_stats),
        "total_blocks": len(blocks),
        "total_chunks": len(chunks),
        "headings": len(headings),
        "tables": len(tables),
        "paragraphs": len(paras),
        "chunks_by_type": {"text": len(text_chunks), "table": len(table_chunks)},
        "page_range": validation["page_range"],
        "heading_numbers": validation["heading_numbers"],
        "header_footer_leak_count": len(leaks),
        "header_footer_leak_samples": leaks[:10],
        "low_text_pages": low_text_pages,
        "low_text_threshold_chars": LOW_TEXT_THRESHOLD,
        "per_page_stats": per_page,
        "validation": validation,
    }

    # ---- 保存 ----
    chunks_path = os.path.join(OUTPUT_DIR, "chunks.jsonl")
    with open(chunks_path, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"  chunks 已保存: {chunks_path}")

    report_path = os.path.join(OUTPUT_DIR, "parse_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  report 已保存: {report_path}")

    # ---- 随机抽样 ----
    if chunks:
        samples = random.sample(chunks, min(5, len(chunks)))
        print(f"\n[抽样] {len(samples)} 个 chunk:")
        print("-" * 60)
        for i, c in enumerate(samples, 1):
            heading = c.get("heading", "") or "(无)"
            text = c["text"][:150].replace("\n", " ")
            print(f"  [{i}] {c['chunk_type']} | p{c['page_start']}-{c['page_end']}")
            print(f"      heading: {heading}")
            print(f"      text: {text}...")
            print()

    print("✓ 测试完成")


if __name__ == "__main__":
    main()

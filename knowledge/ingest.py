"""
XF 模具智能体平台 - 知识库入库脚本
结构感知切块：识别 docx 标题层级 / 表格 → 打章节元数据 → 写入 Milvus
ID 体系：自生成稳定 chunk_uid；table_parent（完整表/回溯）+ table_summary（宽泛召回）+ table_row_block（精确检索）
"""
import zipfile
import xml.etree.ElementTree as ET
import os
import sys
import re
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymilvus import MilvusClient, DataType

# PDF 解析器（仅在需要时导入，避免缺少依赖报错）
try:
    from knowledge.pdf_parser import parse_pdf_blocks
except ImportError:
    parse_pdf_blocks = None
from config import (
    MILVUS_URI, MILVUS_COLLECTION_FMEA, MILVUS_COLLECTION_QUALITY,
    EMBEDDING_DIM,
    FMEA_DOC_PATH, QUALITY_DOC_PATH,
    RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP,
    TABLE_MAX_ROWS_FOR_INLINE, TABLE_SUMMARY_CHUNK_SIZE,
)
from tools.rag import _emb

DOCX_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# source_name → ASCII slug（用于 chunk_uid，避免空格/中文）
SOURCE_SLUG = {
    "FMEA 手册": "fmea",
    "VDA6.4 质量手册": "vda6.4",
}


# =============================================================================
# docx XML 文本提取
# =============================================================================

def _extract_para_text(elem) -> str:
    """提取段落纯文本"""
    parts = []
    for t in elem.iter(f"{{{DOCX_NS}}}t"):
        if t.text:
            parts.append(t.text)
    return "".join(parts)


def _get_para_style_id(elem) -> Optional[str]:
    """获取段落样式 ID"""
    style = elem.find(f"{{{DOCX_NS}}}pPr/{{{DOCX_NS}}}pStyle")
    if style is not None:
        return style.get(f"{{{DOCX_NS}}}val")
    return None


def _get_outline_level(elem) -> Optional[int]:
    """获取段落大纲级别（FMEA 文档用 w:outlineLvl 标记标题）"""
    ol = elem.find(f"{{{DOCX_NS}}}pPr/{{{DOCX_NS}}}outlineLvl")
    if ol is not None:
        return int(ol.get(f"{{{DOCX_NS}}}val"))
    return None


def _build_style_heading_map(zipfile_obj) -> dict:
    """从 styles.xml 构建 styleId → headingLevel 映射（VDA6.4 文档用）"""
    heading_map = {}
    try:
        styles_xml = zipfile_obj.read("word/styles.xml")
        root = ET.fromstring(styles_xml)
        for style in root.iter(f"{{{DOCX_NS}}}style"):
            style_id = style.get(f"{{{DOCX_NS}}}styleId")
            style_name = ""
            name_elem = style.find(f"{{{DOCX_NS}}}name")
            if name_elem is not None:
                style_name = (name_elem.get(f"{{{DOCX_NS}}}val") or "").lower()

            # 检查是否为 heading 样式
            if style_name.startswith("heading") or style_name.startswith("heading "):
                # heading 1 → level 0, heading 2 → level 1, ...
                try:
                    num = int(style_name.split()[-1])
                    heading_map[style_id] = num - 1  # convert to 0-based
                except ValueError:
                    pass
    except Exception:
        pass
    return heading_map


# =============================================================================
# 表格 → Markdown
# =============================================================================

def _extract_table_markdown(tbl_elem) -> str:
    """将 docx table 元素转为 Markdown 表格，处理合并单元格"""
    rows = tbl_elem.findall(f"{{{DOCX_NS}}}tr")
    if not rows:
        return ""

    md_rows: list[list[str]] = []
    merge_state: dict[int, str] = {}  # col → continuation text for vMerge

    for row_elem in rows:
        cells = row_elem.findall(f"{{{DOCX_NS}}}tc")
        md_cells: list[str] = []
        col_idx = 0

        for cell in cells:
            tc_pr = cell.find(f"{{{DOCX_NS}}}tcPr")
            grid_span = 1
            v_merge = None  # None=no merge, "restart"=start, "continue"=continue

            if tc_pr is not None:
                gs = tc_pr.find(f"{{{DOCX_NS}}}gridSpan")
                if gs is not None:
                    grid_span = int(gs.get(f"{{{DOCX_NS}}}val", "1"))
                vm = tc_pr.find(f"{{{DOCX_NS}}}vMerge")
                if vm is not None:
                    v_merge = vm.get(f"{{{DOCX_NS}}}val", "continue")

            # 提取单元格文本
            cell_text = _extract_para_text(cell).replace("\n", " ").replace("|", "\\|").strip()

            if v_merge == "continue":
                # 使用上一行的同列内容（从 merge_state 取）
                cell_text = merge_state.get(col_idx, "")
            elif v_merge == "restart":
                merge_state[col_idx] = cell_text

            if v_merge != "continue":
                # 非 continue 行，更新或清除合并状态
                merge_state[col_idx] = cell_text

            # grid_span 扩展
            md_cells.append(cell_text)
            for _ in range(grid_span - 1):
                md_cells.append("")

            col_idx += grid_span

        md_rows.append(md_cells)

    # 确定列数
    max_cols = max((len(r) for r in md_rows), default=0)
    if max_cols == 0:
        return ""

    # 对齐列
    for r in md_rows:
        while len(r) < max_cols:
            r.append("")

    # 输出 Markdown
    lines = []
    for i, row in enumerate(md_rows):
        lines.append("| " + " | ".join(row) + " |")
        if i == 0:
            lines.append("| " + " | ".join(["---"] * max_cols) + " |")

    return "\n".join(lines)


# =============================================================================
# 文档结构解析：返回带 heading 路径的 block 序列
# =============================================================================

class HeadingTracker:
    """追踪当前标题路径栈"""

    def __init__(self):
        self.stack: list[dict] = []  # [{level: 0, number: "2", title: "潜在FMEA..."}, ...]
        self.counters: list[int] = []  # 每层计数器 [chapter_num, section_num, ...]

    def push(self, level: int, title: str) -> str:
        """压入新标题，返回编号字符串如 "2.1" """
        # 弹出所有 >= 当前 level 的旧标题
        while self.stack and self.stack[-1]["level"] >= level:
            self.stack.pop()
            self.counters.pop()

        # 当前层计数+1
        while len(self.counters) <= level:
            self.counters.append(0)
        self.counters[level] += 1

        # 剔除多余的高层计数器
        self.counters = self.counters[:level + 1]

        # 构建编号
        number = ".".join(str(c) for c in self.counters)

        title_clean = title.strip()
        # 去掉标题中已有的编号前缀（如 "1  引言" → "引言"）
        title_clean = re.sub(r'^[\d.]+\s+', '', title_clean)

        self.stack.append({"level": level, "number": number, "title": title_clean})
        return number

    def current_path(self) -> dict:
        """返回当前路径信息"""
        if not self.stack:
            return {"chapter": "", "section_title": "", "heading_path": ""}
        return {
            "chapter": self.stack[-1]["number"],
            "section_title": self.stack[-1]["title"],
            "heading_path": " > ".join(
                f"{s['number']} {s['title']}" for s in self.stack
            ),
        }

    def full_path(self) -> str:
        """返回完整标题路径，如 '2 失效模式分析 > 2.1 七步法 > 2.1.1 定义范围'"""
        if not self.stack:
            return ""
        return " > ".join(f"{s['number']} {s['title']}" for s in self.stack)


def parse_docx_blocks(filepath: str) -> list[dict]:
    """
    解析 docx 文档，输出 block 序列。
    兼容两种标题标识方式：
    - FMEA 手册: w:outlineLvl
    - VDA6.4 手册: w:pStyle → heading N
    """
    with zipfile.ZipFile(filepath) as z:
        heading_styles = _build_style_heading_map(z)
        doc_xml = z.read("word/document.xml")
        root = ET.fromstring(doc_xml)
        body = root.find(f"{{{DOCX_NS}}}body")
        if body is None:
            return []

    tracker = HeadingTracker()
    blocks: list[dict] = []

    for elem in body:
        tag = elem.tag.split("}")[-1]

        if tag == "p":
            # 判断是否为标题
            outline_lvl = _get_outline_level(elem)
            style_id = _get_para_style_id(elem)
            text = _extract_para_text(elem).strip()

            if not text:
                continue

            heading_level = None
            if outline_lvl is not None:
                heading_level = outline_lvl  # 0-based from Word
            elif style_id and style_id in heading_styles:
                heading_level = heading_styles[style_id]

            if heading_level is not None:
                number = tracker.push(heading_level, text)
                blocks.append({
                    "type": "heading",
                    "level": heading_level,
                    "number": number,
                    "title": tracker.current_path()["section_title"],
                    "text": text,
                    "path": tracker.current_path(),
                })
            else:
                blocks.append({
                    "type": "paragraph",
                    "text": text,
                    "path": tracker.current_path(),
                })

        elif tag == "tbl":
            table_md = _extract_table_markdown(elem)
            if table_md.strip():
                blocks.append({
                    "type": "table",
                    "markdown": table_md,
                    "path": tracker.current_path(),
                })

    return blocks


# =============================================================================
# 结构感知切块
# =============================================================================

def _split_long_text(text: str, max_len: int, overlap: int) -> list[str]:
    """将长文本按句子边界切分为多个块"""
    if len(text) <= max_len:
        return [text]

    chunks = []
    sentences = re.split(r'(?<=[。！？；\n])', text)
    current = ""
    for sent in sentences:
        if len(current) + len(sent) > max_len and current:
            chunks.append(current.strip())
            # overlap: 保留最后 overlap 字符
            if overlap > 0 and len(current) > overlap:
                current = current[-overlap:]
            else:
                current = ""
        current += sent
    if current.strip():
        chunks.append(current.strip())
    return chunks


def chunk_blocks(blocks: list[dict], chunk_size: int, chunk_overlap: int,
                 source_name: str, source_type_param: str = "docx",
                 source_file_param: str = "") -> list[dict]:
    """
    将 blocks 按 heading 边界切分为带元数据的 chunk。
    大型表格额外生成摘要嵌入 chunk（Multi-Vector）。
    """
    chunks: list[dict] = []
    chunk_id_counter = [0]  # 用于生成唯一 chunk_uid
    table_counter = [0]     # 用于分配 table_id

    def emit_chunk(path: dict, text: str, chunk_type: str = "text",
                   parent_chunk_uid: str = "", table_id: str = "",
                   heading_path: str = "", row_range: str = "",
                   page_start: int = None, page_end: int = None):
        chunk_id_counter[0] += 1
        slug = SOURCE_SLUG.get(source_name, source_name.replace(" ", "_"))
        chunk_uid = f"{slug}_{chunk_type}_{chunk_id_counter[0]:06d}"
        chunk = {
            "chunk_uid": chunk_uid,
            "text": text,
            "source": source_name,
            "chapter": path.get("chapter", ""),
            "section_title": path.get("section_title", ""),
            "chunk_type": chunk_type,
            "parent_chunk_uid": parent_chunk_uid,
            "table_id": table_id,
            "heading_path": heading_path,
            "row_range": row_range,
            "source_type": source_type_param,
            "source_file": source_file_param,
        }
        if page_start is not None:
            chunk["page_start"] = page_start
            chunk["page_end"] = page_end
        chunks.append(chunk)
        return chunk_uid

    # 按 heading 边界分组
    current_sections: list[dict] = []  # 当前 heading section 下的 blocks
    current_heading_path: dict = {"chapter": "", "section_title": "", "heading_path": ""}

    for block in blocks:
        if block["type"] == "heading":
            # 先处理上一个章节的内容
            _flush_section(current_sections, current_heading_path,
                          chunk_size, chunk_overlap, emit_chunk,
                          table_counter, source_name)
            current_sections = []
            current_heading_path = block["path"]
            current_sections.append(block)
        else:
            current_sections.append(block)

    # 处理最后一个章节
    _flush_section(current_sections, current_heading_path,
                  chunk_size, chunk_overlap, emit_chunk,
                  table_counter, source_name)

    return chunks


def _flush_section(sections: list[dict], heading_path: dict,
                   chunk_size: int, chunk_overlap: int, emit_chunk,
                   table_counter: list = None, source_name: str = ""):
    """将一个章节的 blocks 转为 chunk 并写入 chunks 列表"""
    if not sections:
        return

    if table_counter is None:
        table_counter = [0]

    full_hpath = heading_path.get("heading_path", "")
    if not full_hpath:
        ch = heading_path.get("chapter", "")
        sec = heading_path.get("section_title", "")
        full_hpath = f"{ch} {sec}".strip() if ch or sec else ""

    for block in sections:
        if block["type"] == "heading":
            continue  # heading 信息已通过 heading_path 携带

        if block["type"] == "paragraph":
            text = block["text"]
            _ps = block.get("page_start")
            _pe = block.get("page_end")
            if len(text) <= chunk_size:
                emit_chunk(heading_path, text, "text", heading_path=full_hpath,
                           page_start=_ps, page_end=_pe)
            else:
                for sub in _split_long_text(text, chunk_size, chunk_overlap):
                    emit_chunk(heading_path, sub, "text", heading_path=full_hpath,
                               page_start=_ps, page_end=_pe)

        elif block["type"] == "table":
            md = block["markdown"]
            _ps = block.get("page_start")
            _pe = block.get("page_end")
            lines = md.split("\n")
            # 数据行数：跳过表头行和分隔行
            data_lines = [l for l in lines if l.startswith("|") and not l.startswith("| ---")]
            header_line = data_lines[0] if data_lines else ""
            header_count = 1 if header_line else 0
            row_count = max(0, len(data_lines) - header_count)

            # 分配 table_id
            table_counter[0] += 1
            slug = SOURCE_SLUG.get(source_name, source_name.replace(" ", "_"))
            tid = f"{slug}_table_{table_counter[0]:04d}"
            r_range = f"1-{row_count}"

            if row_count <= TABLE_MAX_ROWS_FOR_INLINE:
                # 小表格：直接存为 "table"，参与检索
                if len(md) <= chunk_size:
                    emit_chunk(heading_path, md, "table",
                               table_id=tid, heading_path=full_hpath,
                               row_range=r_range,
                               page_start=_ps, page_end=_pe)
                else:
                    for sub in _split_long_text(md, chunk_size, 0):
                        emit_chunk(heading_path, sub, "table",
                                   table_id=tid, heading_path=full_hpath,
                                   row_range=r_range,
                                   page_start=_ps, page_end=_pe)
            else:
                # 超大表格：Multi-Vector（table_parent + summary + row_block）
                # 1. 存完整 Markdown 表格（parent，不参与检索，仅用于回溯）
                table_chunk_uid = emit_chunk(heading_path, md, "table_parent",
                                            table_id=tid, heading_path=full_hpath,
                                            row_range=r_range,
                                            page_start=_ps, page_end=_pe)

                # 提取表头行和分隔行
                sep_line = lines[1] if len(lines) > 1 and "---" in lines[1] else ""

                # 2. 生成增强摘要（宽泛召回用）
                col_names: list[str] = []
                if header_line:
                    cols = [c.strip() for c in header_line.split("|") if c.strip()]
                    col_names = cols

                sample_head = data_lines[1:6] if len(data_lines) > 1 else []
                sample_tail = data_lines[-5:] if len(data_lines) > 6 else []
                if sample_tail and sample_head:
                    overlap_start = max(0, len(data_lines) - 10)
                    sample_tail = data_lines[overlap_start:]

                keyword_freq: dict[str, int] = {}
                for dl in data_lines[1:]:
                    cells = [c.strip() for c in dl.split("|") if c.strip()]
                    for cell in cells:
                        tokens = re.findall(r'[一-鿿]{2,}|[A-Za-z]{2,}', cell)
                        for t in tokens:
                            keyword_freq[t] = keyword_freq.get(t, 0) + 1
                high_kw = sorted(
                    [(k, v) for k, v in keyword_freq.items() if v >= 2],
                    key=lambda x: -x[1]
                )[:10]

                summary = (
                    f"表格摘要：{heading_path.get('chapter', '')} {heading_path.get('section_title', '')}\n"
                    f"共 {row_count} 行数据\n"
                )
                if col_names:
                    summary += f"列名：{' | '.join(col_names[:15])}\n"
                if sample_head:
                    summary += "前 5 行数据：\n" + "\n".join(sample_head) + "\n"
                if sample_tail:
                    summary += "后 5 行数据：\n" + "\n".join(sample_tail) + "\n"
                if high_kw:
                    summary += f"高频关键词：{', '.join(f'{k}({v}次)' for k, v in high_kw)}\n"

                summary = summary[:TABLE_SUMMARY_CHUNK_SIZE]
                emit_chunk(heading_path, summary, "table_summary",
                           parent_chunk_uid=table_chunk_uid,
                           table_id=tid, heading_path=full_hpath,
                           row_range=r_range,
                           page_start=_ps, page_end=_pe)

                # 3. 行块切分：每 ROW_BLOCK_SIZE 行为一组，带表头，关联同一个 parent
                ROW_BLOCK_SIZE = 20
                data_rows = data_lines[1:]  # 跳过表头行
                for row_start in range(0, len(data_rows), ROW_BLOCK_SIZE):
                    group_rows = data_rows[row_start:row_start + ROW_BLOCK_SIZE]
                    row_end = min(row_start + ROW_BLOCK_SIZE, len(data_rows))
                    block_r_range = f"{row_start + 1}-{row_end}"

                    # 拼接：表头 + 分隔行 + 数据行组
                    block_lines = []
                    if header_line:
                        block_lines.append(header_line)
                    if sep_line:
                        block_lines.append(sep_line)
                    block_lines.extend(group_rows)
                    block_md = "\n".join(block_lines)

                    emit_chunk(heading_path, block_md, "table_row_block",
                               parent_chunk_uid=table_chunk_uid,
                               table_id=tid, heading_path=full_hpath,
                               row_range=block_r_range,
                               page_start=_ps, page_end=_pe)


# =============================================================================
# Milvus 集合管理
# =============================================================================

def _ensure_collection(client: MilvusClient, collection_name: str):
    """确保集合存在，不存在则创建（含元数据字段）"""
    if client.has_collection(collection_name):
        print(f"[Milvus] 集合已存在: {collection_name}")
        info = client.describe_collection(collection_name)
        print(f"  现有文档数: {info.get('row_count', 'unknown')}")
        return

    schema = client.create_schema(
        auto_id=True,
        enable_dynamic_field=True,
    )
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
    schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=8192, enable_analyzer=True)

    # 元数据硬字段
    schema.add_field(field_name="chunk_uid", datatype=DataType.VARCHAR, max_length=128)
    schema.add_field(field_name="doc_source", datatype=DataType.VARCHAR, max_length=128)
    schema.add_field(field_name="doc_chapter", datatype=DataType.VARCHAR, max_length=64)
    schema.add_field(field_name="doc_section", datatype=DataType.VARCHAR, max_length=256)
    schema.add_field(field_name="chunk_type", datatype=DataType.VARCHAR, max_length=32)
    schema.add_field(field_name="parent_chunk_uid", datatype=DataType.VARCHAR, max_length=128)
    schema.add_field(field_name="table_id", datatype=DataType.VARCHAR, max_length=128)
    schema.add_field(field_name="heading_path", datatype=DataType.VARCHAR, max_length=512)
    schema.add_field(field_name="row_range", datatype=DataType.VARCHAR, max_length=32)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        metric_type="COSINE",
        index_type="IVF_FLAT",
        params={"nlist": 128},
    )

    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )
    print(f"[Milvus] 集合创建成功: {collection_name}")


def _validate_schema(client: MilvusClient, collection_name: str):
    """
    验证集合 schema 可用，插入一条测试数据并回滚。
    必须在调用 embedding 之前执行，避免浪费 token。
    """
    # 插入一条空测试数据验证 schema
    test_row = {
        "embedding": [0.0] * EMBEDDING_DIM,
        "text": "__test_validation__",
        "chunk_uid": "__test__",
        "doc_source": "__test__",
        "doc_chapter": "",
        "doc_section": "",
        "chunk_type": "text",
        "parent_chunk_uid": "",
        "table_id": "",
        "heading_path": "",
        "row_range": "",
    }
    try:
        res = client.insert(collection_name=collection_name, data=[test_row])
        inserted_pk = res.get("ids", [None])[0] if isinstance(res, dict) else None
        if inserted_pk is not None:
            client.delete(collection_name=collection_name, ids=[inserted_pk])
        print("  [验证] schema 测试写入成功")
    except Exception as e:
        print(f"  [验证] schema 测试写入失败: {e}")
        # 尝试用 describe_collection 输出完整 schema 辅助诊断
        try:
            desc = client.describe_collection(collection_name)
            print(f"  [诊断] 集合字段: {[f['name'] for f in desc.get('fields', [])]}")
        except Exception:
            pass
        raise RuntimeError(
            f"Milvus schema 验证失败，请检查集合 '{collection_name}' 的 schema 定义。"
            f" 错误: {e}"
        ) from e


def _ingest_document(filepath: str, collection_name: str, label: str,
                     debug_dir: str = ""):
    """将单个文档结构解析、切块、向量化、写入 Milvus"""
    print(f"\n{'='*60}")
    print(f"处理文档: {label}")
    print(f"文件路径: {filepath}")
    print(f"目标集合: {collection_name}")
    print(f"{'='*60}")

    ext = os.path.splitext(filepath)[1].lower()

    # ---- 1. 结构解析 ----
    print("\n[1/5] 解析文档结构...")

    if ext == ".docx":
        source_type = "docx"
        blocks = parse_docx_blocks(filepath)
    elif ext == ".pdf":
        source_type = "pdf"
        if parse_pdf_blocks is None:
            raise ImportError("PDF 解析器不可用，请安装依赖: pip install PyMuPDF")
        blocks = parse_pdf_blocks(filepath)
    else:
        raise ValueError(f"不支持的文件格式: {ext}，仅支持 .docx 和 .pdf")

    headings = [b for b in blocks if b["type"] == "heading"]
    tables = [b for b in blocks if b["type"] == "table"]
    print(f"  解析完成: {len(blocks)} 块（{len(headings)} 个标题，{len(tables)} 个表格）")

    # ---- 2. 结构感知切块 ----
    print("\n[2/5] 结构感知切块...")
    source_file = os.path.basename(filepath)
    chunks = chunk_blocks(blocks, RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP, label,
                          source_type_param=source_type,
                          source_file_param=source_file)
    text_chunks = [c for c in chunks if c["chunk_type"] == "text"]
    table_chunks = [c for c in chunks if c["chunk_type"] == "table"]
    table_parent_chunks = [c for c in chunks if c["chunk_type"] == "table_parent"]
    summary_chunks = [c for c in chunks if c["chunk_type"] == "table_summary"]
    row_block_chunks = [c for c in chunks if c["chunk_type"] == "table_row_block"]
    print(f"  切块结果: {len(chunks)} 个chunk（文本:{len(text_chunks)}, 小表:{len(table_chunks)}, 大表父:{len(table_parent_chunks)}, 摘要:{len(summary_chunks)}, 行块:{len(row_block_chunks)}）")
    for heading in headings:
        if heading.get("number"):
            print(f"    {heading['number']} {heading.get('title', '')}")

    # ---- 调试输出 ----
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        import json
        chunks_path = os.path.join(debug_dir, "chunks.jsonl")
        with open(chunks_path, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"  [debug] chunks 已保存: {chunks_path}")

        report = {
            "source_file": source_file,
            "source_type": source_type,
            "total_blocks": len(blocks),
            "total_chunks": len(chunks),
            "headings": len(headings),
            "tables": len(tables),
            "chunks_by_type": {
                "text": len(text_chunks),
                "table": len(table_chunks),
                "table_parent": len(table_parent_chunks),
                "table_summary": len(summary_chunks),
                "table_row_block": len(row_block_chunks),
            },
            "has_page_info": any("page_start" in c for c in chunks),
            "empty_chunks": sum(1 for c in chunks if not c.get("text", "").strip()),
        }
        if chunks:
            page_starts = [c.get("page_start") for c in chunks if c.get("page_start") is not None]
            if page_starts:
                report["page_range"] = f"{min(page_starts)}-{max(page_starts)}"
        report_path = os.path.join(debug_dir, "parse_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  [debug] 报告已保存: {report_path}")

        # 最小检查
        print(f"\n  [检查] chunk 数量: {len(chunks)} {'OK' if len(chunks) > 0 else 'FAIL'}")
        no_page = sum(1 for c in chunks if "page_start" not in c and "page_end" not in c)
        if no_page:
            print(f"  [检查] 缺少页码的 chunk: {no_page}")
        else:
            print("  [检查] 页码完整性: OK")
        empty_chunks = report["empty_chunks"]
        if empty_chunks:
            print(f"  [检查] 空 chunk: {empty_chunks} {'WARN' if empty_chunks > 0 else 'OK'}")
        else:
            print("  [检查] 空 chunk: OK")

        # 随机抽样 5 个 chunk 打印详情
        if chunks:
            import random
            samples = random.sample(chunks, min(5, len(chunks)))
            print(f"\n  [抽样] {len(samples)} 个 chunk 详情:")
            print(f"  {'─'*60}")
            for i, c in enumerate(samples, 1):
                cid = c.get("chunk_uid", "?")
                hpath = c.get("heading_path", c.get("section_title", ""))
                ps = c.get("page_start", "?")
                pe = c.get("page_end", "?")
                text_preview = c.get("text", "")[:200].replace("\n", " ")
                print(f"  [{i}] chunk_id: {cid}")
                print(f"      heading:  {hpath or '(无)'}")
                print(f"      page:     {ps}-{pe}")
                print(f"      text:     {text_preview}...")
                print()

    # ---- 3. Milvus schema 预检（在调用 embedding 之前执行，避免浪费 token） ----
    print("\n[3/5] 连接 Milvus 并验证 schema...")
    client = MilvusClient(uri=MILVUS_URI, token="")
    _ensure_collection(client, collection_name)
    _validate_schema(client, collection_name)

    # ---- 4. 向量化 ----
    print("\n[4/5] 生成向量...")
    texts = [c["text"] for c in chunks]
    embeddings = _emb.embed_documents(texts)
    print(f"  生成 {len(embeddings)} 个向量，维度 {len(embeddings[0]) if embeddings else 0}")

    # ---- 5. 写入 Milvus ----
    print("\n[5/5] 写入 Milvus...")
    data = []
    for chunk, emb in zip(chunks, embeddings):
        row = {
            "embedding": emb,
            "text": chunk["text"],
            "chunk_uid": chunk["chunk_uid"],
            "doc_source": chunk["source"],
            "doc_chapter": chunk["chapter"],
            "doc_section": chunk["section_title"],
            "chunk_type": chunk["chunk_type"],
            "parent_chunk_uid": chunk.get("parent_chunk_uid", ""),
            "table_id": chunk.get("table_id", ""),
            "heading_path": chunk.get("heading_path", ""),
            "row_range": chunk.get("row_range", ""),
            "source_type": chunk.get("source_type", "docx"),
            "source_file": chunk.get("source_file", ""),
        }
        if "page_start" in chunk:
            row["page_start"] = chunk["page_start"]
            row["page_end"] = chunk["page_end"]
        data.append(row)

    client.insert(
        collection_name=collection_name,
        data=data,
    )
    print(f"  写入完成: {len(data)} 条记录")


def ingest_all(debug_dir: str = ""):
    """入库全部文档"""
    _ingest_document(FMEA_DOC_PATH, MILVUS_COLLECTION_FMEA, "FMEA 手册", debug_dir=debug_dir)
    _ingest_document(QUALITY_DOC_PATH, MILVUS_COLLECTION_QUALITY, "VDA6.4 质量手册", debug_dir=debug_dir)
    print("\n" + "=" * 60)
    print("全部知识库入库完成！")
    print("=" * 60)


if __name__ == "__main__":
    # 传 debug_dir="debug_output" 即可在开发阶段保存调试文件
    ingest_all()

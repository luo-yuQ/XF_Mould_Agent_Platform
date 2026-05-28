"""
XF 模具智能体平台 - 共享 RAG 工具
支持两个知识库：FMEA 手册 / VDA6.4 质量手册
返回结构化对象，包含元数据（来源、章节）用于引文系统
"""
from typing import List, Optional
from langchain_core.tools import tool
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import MilvusClient, AnnSearchRequest, RRFRanker
from openai import OpenAI
from config import (
    DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL,
    EMBEDDING_MODEL, EMBEDDING_DIM,
    MILVUS_URI, MILVUS_COLLECTION_FMEA, MILVUS_COLLECTION_QUALITY,
    RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP, RAG_TOP_K,
)

# =============================================================================
# 文本分块器
# =============================================================================
TEXT_SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=RAG_CHUNK_SIZE,
    chunk_overlap=RAG_CHUNK_OVERLAP,
    separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
)

# =============================================================================
# Embedding 封装
# =============================================================================
class DashScopeEmbeddings:
    def __init__(self):
        self.client = OpenAI(
            api_key=DASHSCOPE_API_KEY,
            base_url=DASHSCOPE_BASE_URL,
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        results: List[List[float]] = []
        for i in range(0, len(texts), 10):
            batch = texts[i:i + 10]
            response = self.client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=batch,
            )
            results.extend([item.embedding for item in response.data])
        return results

    def embed_query(self, text: str) -> List[float]:
        response = self.client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[text],
        )
        return response.data[0].embedding


_emb = DashScopeEmbeddings()
_milvus_client: Optional[MilvusClient] = None


def _get_milvus_client() -> MilvusClient:
    global _milvus_client
    if _milvus_client is None:
        _milvus_client = MilvusClient(uri=MILVUS_URI, token="")
    return _milvus_client


def _check_collection(collection_name: str) -> bool:
    """检查集合是否存在"""
    try:
        client = _get_milvus_client()
        return client.has_collection(collection_name)
    except Exception:
        return False


OUTPUT_FIELDS = ["text", "doc_source", "doc_chapter", "doc_section", "chunk_type",
                  "parent_chunk_uid", "table_id", "heading_path", "row_range", "chunk_uid",
                  "source_type", "source_file", "page_start", "page_end"]


def _hit_to_chunk(entity: dict) -> dict:
    """将 Milvus 返回的 entity 转为统一的 chunk dict"""
    return {
        "text": entity.get("text", "").strip(),
        "doc_source": entity.get("doc_source", ""),
        "doc_chapter": entity.get("doc_chapter", ""),
        "doc_section": entity.get("doc_section", ""),
        "chunk_type": entity.get("chunk_type", "text"),
        "parent_chunk_uid": entity.get("parent_chunk_uid", ""),
        "table_id": entity.get("table_id", ""),
        "heading_path": entity.get("heading_path", ""),
        "row_range": entity.get("row_range", ""),
        "chunk_uid": entity.get("chunk_uid", ""),
        "source_type": entity.get("source_type", ""),
        "source_file": entity.get("source_file", ""),
        "page_start": entity.get("page_start"),
        "page_end": entity.get("page_end"),
    }


def _empty_result(msg: str = "[RAG] 未检索到相关内容") -> dict:
    return {"text": msg, "doc_source": "", "doc_chapter": "", "doc_section": "",
            "chunk_type": "empty", "parent_chunk_uid": "", "table_id": "",
            "heading_path": "", "row_range": "", "chunk_uid": "",
            "source_type": "", "source_file": "", "page_start": None, "page_end": None}


def _expand_table_chunks(client: MilvusClient, collection_name: str, chunks: list[dict]) -> list[dict]:
    """
    检索后处理：
    - table_summary 命中 → 按 table_id 拉取关联的 table_row_block（每个 table_id 最多 3 个）
    - 去重（按 chunk_uid）
    """
    table_ids_to_expand: set[str] = set()
    for c in chunks:
        if c["chunk_type"] == "table_summary" and c.get("table_id"):
            table_ids_to_expand.add(c["table_id"])

    if not table_ids_to_expand:
        return chunks

    MAX_ROW_BLOCKS_PER_TABLE = 3
    for tid in table_ids_to_expand:
        filter_expr = f'table_id == "{tid}" and chunk_type == "table_row_block"'
        try:
            row_blocks = client.query(
                collection_name=collection_name,
                filter=filter_expr,
                output_fields=OUTPUT_FIELDS,
                limit=MAX_ROW_BLOCKS_PER_TABLE,
            )
            for rb in row_blocks:
                chunks.append(_hit_to_chunk(rb))
        except Exception:
            pass

    # 去重
    seen: set[str] = set()
    unique: list[dict] = []
    for c in chunks:
        uid = c.get("chunk_uid", "")
        if uid and uid in seen:
            continue
        if uid:
            seen.add(uid)
        unique.append(c)
    return unique


def retrieve_structured(query: str, collection_name: str, top_k: int = RAG_TOP_K) -> list[dict]:
    """
    从指定知识库检索相关内容，返回结构化列表。

    检索策略：
    1. hybrid search 搜 table_summary / table_row_block / text（排除 table_parent）
    2. table_summary 命中 → 按 table_id 拉取关联的 table_row_block
    3. table_row_block 命中 → 直接用于回答
    4. 必要时通过 parent_chunk_uid 回溯 table_parent 获取完整表
    """
    if not _check_collection(collection_name):
        return [_empty_result(f"[RAG] 知识库 '{collection_name}' 未初始化")]

    try:
        client = _get_milvus_client()
        query_vec = _emb.embed_query(query)

        dense_req = AnnSearchRequest(
            data=[query_vec],
            anns_field="embedding",
            param={"metric_type": "COSINE"},
            limit=top_k * 10,
        )

        # table_parent 不参与检索，仅用于回溯
        results = client.hybrid_search(
            collection_name=collection_name,
            reqs=[dense_req],
            ranker=RRFRanker(k=60),
            limit=top_k,
            output_fields=OUTPUT_FIELDS,
            filter='chunk_type != "table_parent"',
        )

        if not results or not results[0]:
            return [_empty_result()]

        chunks = []
        for hit in results[0]:
            entity = hit.get("entity", {})
            text = entity.get("text", "")
            if text.strip():
                chunks.append(_hit_to_chunk(entity))

        if not chunks:
            return [_empty_result()]

        # 展开 table_summary → table_row_block
        chunks = _expand_table_chunks(client, collection_name, chunks)

        return chunks

    except Exception as e:
        return [_empty_result(f"[RAG] 检索出错: {e}")]


def chunks_to_text(chunks: list[dict]) -> str:
    """将结构化 chunks 转为旧协议的纯文本（兼容用）"""
    parts = []
    for c in chunks:
        src = c.get("doc_source", "")
        ch = c.get("doc_chapter", "")
        sec = c.get("doc_section", "")
        meta = f"【来源: {src}】" if src else ""
        if ch:
            meta = f"【来源: {src} 第{ch}章 {sec}】" if sec else f"【来源: {src} 第{ch}章】"
        parts.append(f"{meta}\n{c['text']}")
    return "\n\n---\n\n".join(parts)


# =============================================================================
# 注册为 LangChain Tool（保持兼容，返回文本）
# =============================================================================

@tool
def fmea_rag_search(query: str) -> str:
    """从 FMEA 手册知识库中检索与失效模式分析、DFMEA、PFMEA、风险评级等相关的信息。"""
    chunks = retrieve_structured(query, MILVUS_COLLECTION_FMEA)
    return chunks_to_text(chunks)


@tool
def quality_rag_search(query: str) -> str:
    """从 VDA6.4 质量手册知识库中检索与质量管理体系、公司资质、流程职责等相关的信息。"""
    chunks = retrieve_structured(query, MILVUS_COLLECTION_QUALITY)
    return chunks_to_text(chunks)

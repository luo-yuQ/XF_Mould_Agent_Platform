"""
XF 模具智能体平台 - 全局配置
"""
import os
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# LLM 配置（阿里百炼 DashScope）
# =============================================================================
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5-27b")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

# =============================================================================
# Embedding 配置
# =============================================================================
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-v4")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "1024"))

# =============================================================================
# Milvus 向量库配置
# =============================================================================
MILVUS_URI = os.getenv("MILVUS_URI", "http://127.0.0.1:19530")
MILVUS_COLLECTION_FMEA = "xf_fmea_kb"
MILVUS_COLLECTION_QUALITY = "xf_quality_kb"

# =============================================================================
# 文档路径
# =============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "papers")
FMEA_DOC_PATH = os.path.join(DOCS_DIR, "FMEA手册-2019年6月5版(1).docx")
QUALITY_DOC_PATH = os.path.join(DOCS_DIR, "XF模具VDA6.4质量手册.pdf")

# =============================================================================
# RAG 参数
# =============================================================================
RAG_CHUNK_SIZE = 1000
RAG_CHUNK_OVERLAP = 100
RAG_TOP_K = 8

# =============================================================================
# 表格处理
# =============================================================================
TABLE_MAX_ROWS_FOR_INLINE = 20       # 超过此行数的表格生成摘要嵌入
TABLE_SUMMARY_CHUNK_SIZE = 200       # 摘要嵌入的文本长度

# =============================================================================
# Redis 配置（会话持久化）
# =============================================================================
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_SESSION_TTL = int(os.getenv("REDIS_SESSION_TTL", "86400"))  # 默认 1 天

# =============================================================================
# PostgreSQL 配置
# =============================================================================
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://mould:mould123@127.0.0.1:5432/mould"
)

# =============================================================================
# JWT 认证配置
# =============================================================================
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 2

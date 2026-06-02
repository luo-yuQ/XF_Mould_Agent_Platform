# XF 模具智能体平台

> 基于多智能体架构的冷冲压模具行业 AI 售前客服系统

## 项目简介

XF 模具智能体平台是为先锋模具（XF Mould）打造的 AI 售前咨询系统。系统内置两个专业知识智能体，能够回答客户关于 **FMEA 失效模式分析** 和 **VDA6.4 质量管理体系** 的专业问题，面向采购、技术及质量人员提供 7x24 小时智能问答服务。

### 核心能力

- **研发智能体（R&D Agent）** — 基于 FMEA 手册的 RAG 检索问答，支持 DFMEA/PFMEA 报告生成
- **质量智能体（Quality Agent）** — 基于 VDA6.4 质量手册的 RAG 检索问答，涵盖认证、审核、体系流程
- **意图路由（Supervisor）** — 自动识别用户意图，智能分派至对应专业智能体
- **对话智能体（Chat Agent）** — 处理日常闲聊及天气查询等非专业问题

## 技术栈

| 层级 | 技术 |
|------|------|
| **LLM** | 通义千问（Qwen）via 阿里云 DashScope |
| **AI 框架** | LangGraph + LangChain |
| **向量数据库** | Milvus 2.4 |
| **后端** | FastAPI + SSE 流式响应 |
| **前端** | React 19 + TypeScript + Vite |
| **关系数据库** | PostgreSQL 16 |
| **缓存/会话** | Redis 7 |
| **部署** | Docker Compose（7 个服务） |

## 系统架构

```
用户 → React 前端 (Nginx) → FastAPI 后端
                                  │
                          ┌───────┴───────┐
                          │   Supervisor   │  意图分类
                          └───┬───┬───┬───┘
                              │   │   │
                    ┌─────────┘   │   └─────────┐
                    ▼             ▼             ▼
               R&D Agent    Quality Agent   Chat Agent
               (FMEA RAG)   (VDA6.4 RAG)   (闲聊/天气)
                    │             │             │
                    └──────┬──────┘             │
                           ▼                    ▼
                        Writer              Writer
                           │                    │
                           └────────┬───────────┘
                                    ▼
                              SSE 流式输出 → 用户
```

## 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/<your-username>/XF_Mould_Agent_Platform.git
cd XF_Mould_Agent_Platform
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入必填项：

```env
# 必填：阿里云 DashScope API Key
DASHSCOPE_API_KEY=sk-your-api-key-here

# 以下为可选配置（已有默认值）
LLM_MODEL=qwen3.5-27b
LLM_TEMPERATURE=0.1
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIM=1024
```

### 3. 准备知识库文档

将以下文件放入 `papers/` 目录：

- `FMEA手册-2019年6月5版(1).docx` — FMEA 知识库源文档
- `XF模具VDA6.4质量手册.pdf` — VDA6.4 质量手册

### 4. 启动服务

```bash
docker compose up --build
```

首次启动后，需要在后端容器内执行知识库导入：

```bash
# 等待 Milvus 就绪后执行
docker exec mould-backend python knowledge/ingest.py
```

### 5. 访问应用

打开浏览器访问 **http://localhost:8501**，注册账号即可开始使用。

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API Key（必填） | — |
| `LLM_MODEL` | LLM 模型名称 | `qwen3.5-27b` |
| `LLM_TEMPERATURE` | 模型温度参数 | `0.1` |
| `EMBEDDING_MODEL` | 向量化模型 | `text-embedding-v4` |
| `EMBEDDING_DIM` | 向量维度 | `1024` |
| `MILVUS_URI` | Milvus 连接地址 | `http://127.0.0.1:19530` |
| `REDIS_HOST` | Redis 地址 | `127.0.0.1` |
| `REDIS_PORT` | Redis 端口 | `6379` |
| `DATABASE_URL` | PostgreSQL 连接串 | `postgresql://mould:mould123@127.0.0.1:5432/mould` |

## Docker Compose 服务

| 服务 | 端口 | 说明 |
|------|------|------|
| `frontend` | 8501 | React 前端（Nginx） |
| `backend` | 8000 | FastAPI 后端 API |
| `milvus` | 19530 | 向量数据库 |
| `postgres` | 5432 | 关系数据库 |
| `redis` | 6379 | 会话缓存 |
| `etcd` | 2379 | Milvus 元数据 |
| `minio` | 9000/9001 | Milvus 对象存储 |

## 本地开发

```bash
# 后端
pip install -r requirements.txt
alembic upgrade head                    # 数据库迁移
python knowledge/ingest.py              # 导入知识库
uvicorn api:app --host 0.0.0.0 --port 8000

# 前端
cd web
npm install
npm run dev                             # 开发服务器默认 5173 端口
```

本地开发时需自行启动 Milvus、Redis、PostgreSQL，或将 `.env` 中的连接地址指向 Docker 容器。

## 项目结构

```
├── api.py                  # FastAPI 入口
├── graph.py                # LangGraph 工作流定义
├── config.py               # 全局配置
├── chat_memory.py          # 对话记忆管理（滑动窗口 + 滚动摘要）
│
├── agents/                 # 智能体实现
│   ├── supervisor.py       # 意图分类与路由
│   ├── rd_agent.py         # 研发智能体（FMEA）
│   ├── quality_agent.py    # 质量智能体（VDA6.4）
│   └── chat_agent.py       # 闲聊智能体
│
├── tools/                  # 工具集
│   ├── rag.py              # RAG 检索（Milvus + DashScope Embedding）
│   └── weather.py          # 天气查询
│
├── knowledge/              # 文档处理
│   ├── ingest.py           # 文档解析、分块、入库
│   └── pdf_parser.py       # PDF 解析器
│
├── models/                 # 数据库模型
├── alembic/                # 数据库迁移
├── web/                    # React 前端
│   └── src/
│       ├── App.tsx         # 主应用
│       ├── pages/          # 页面
│       └── components/     # 组件
│
└── papers/                 # 知识库源文档（.gitignore）
```

## 功能特性

- **SSE 流式响应** — 逐 token 实时输出，打字机效果
- **结构化引用** — 回答中标注来源章节，前端悬浮展示引用详情
- **智能表格** — R&D 智能体可生成 DFMEA/PFMEA 格式化表格
- **会话管理** — 多会话切换、重命名、删除，分页加载历史消息
- **记忆管理** — 滑动窗口保留最近 20 条消息，超出部分 LLM 滚动摘要
- **用户认证** — JWT + HttpOnly Cookie，Argon2 密码哈希
- **知识库分块** — 结构感知分块，支持文本、表格（父块/摘要/行块）多种粒度

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/auth/register` | 用户注册 |
| POST | `/auth/login` | 用户登录 |
| GET | `/auth/me` | 获取当前用户 |
| GET | `/chat/sessions` | 会话列表 |
| POST | `/chat/sessions` | 创建会话 |
| DELETE | `/chat/sessions/{id}` | 删除会话 |
| GET | `/chat/sessions/{id}/messages` | 获取消息（分页） |
| POST | `/api/ask/stream` | SSE 流式问答 |
| GET | `/health` | 健康检查 |

## License

MIT

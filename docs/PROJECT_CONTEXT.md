# XF Mould Agent Platform 项目上下文

> 面向另一个 AI 或新开发者的仓库事实说明。本文基于 2026-08-28 的当前工作区代码、OpenSpec、SQLAlchemy 模型、Alembic migration、测试和配置整理；若本文与代码冲突，以当前代码和可复现测试为准。

> 快照注意：生成本文时，Runtime Core 相关模型、migration、service、tests 和 `add-agent-runtime-core` change 仍显示为未提交或已修改的 working-tree 内容。因此本文描述的是“当前工作区事实”，不保证这些内容已经进入 Git HEAD 或发布版本。

## 0. 阅读结论

这是一个面向冷冲压模具企业售前、研发风险分析和质量工程场景的 AI 应用平台。当前系统不是单一 Agent，而是四类可运行形态并存：

1. Supervisor 路由的主问答 LangGraph；
2. FMEA、Audit、Report 三个独立质量业务工作流；
3. Planner、双 Specialist、Reviewer、Writer 组成的固定串行销售协作 Graph；
4. 新增但尚未接入公开产品链路的同步 Agent Runtime Core。

最重要的架构事实是：**新的 Runtime Core 尚未替代现有 LangGraph，也没有接入 `api.py`、React、真实 LLM、RAG 或真实业务 capability。** 它目前是一个独立、可持久化、可测试的最小执行内核，用脚本化 Decision Provider 驱动 `demo.echo` capability，证明两步 Agent Loop 和五类 Runtime 记录能够闭环。

当前代码已经具备可用的业务 MVP，但离统一的自主 Agent Runtime 仍有明显距离。异步 worker、resume/checkpoint、ToolExecutor、Runtime 知识入库、公开 Run API、真实 Decision Provider 和业务 workflow adapter 都仍未实现。

---

## 1. 项目概览

### 1.1 项目名称与目标

- 项目名称：XF Mould Agent Platform / XF 模具智能体平台。
- 核心目标：为冷冲压模具企业提供售前咨询、FMEA/VDA 6.4 知识问答、PFMEA 辅助生成、质量审核、质量问题报告和综合售前方案生成能力。
- 主要用户场景：销售售前、研发/工艺风险分析、质量体系与审核、业务产物生成和追改。

### 1.2 主要技术栈

- LLM：通过 OpenAI-compatible API 调用阿里云 DashScope Qwen，默认模型见 `config.py`。
- Agent 编排：LangGraph、LangChain Core。
- 后端：FastAPI、Pydantic、SQLAlchemy、Alembic。
- 关系数据库：PostgreSQL 16。
- RAG：DashScope Embedding、Milvus 2.4、PyMuPDF、自定义 DOCX/PDF 解析与结构感知切块。
- 前端：React 19、TypeScript、Vite。
- 流式通信：SSE。
- 本地编排：Docker Compose；Milvus 依赖 etcd 和 MinIO。

### 1.3 当前能力成熟度

| 能力 | 状态 | 事实说明 |
| --- | --- | --- |
| 主聊天、Supervisor 路由、R&D/Quality RAG 问答 | 已实现 | 公开 SSE API 和 React UI 已接入，见 `graph.py`、`api.py`、`web/src/App.tsx`。 |
| FMEA、Audit、Report | 已实现 MVP | 均有独立 Graph、公开 API、持久化 run 和前端页面。 |
| FMEA 业务产物追改与版本链 | 已实现 MVP | 通用版本底座已建立，但实际只开放 FMEA；Audit/Report 仍为预留类型。 |
| 销售协作 Multi-Agent | 已实现串行 MVP | 固定 Graph 串行执行 Planner、两个 Specialist、Reviewer、Writer、Verifier，并保存 Run/Step。 |
| 业务产物统一元数据 | 已实现 | FMEA/Audit/Report run 已统一 `artifact_type`、title、summary、keywords、references 等字段。 |
| Agent Runtime Core | 独立 Core 已实现 | 两步同步 loop、五类持久化记录、tenant/idempotency/fail-closed 已实现；尚未产品化接入。 |
| 自主、异步、可恢复 Agent Runtime | 仅设计/部分地基 | 大型 OpenSpec 仍处于早期；没有 worker、tool、resume、upload 或 Runtime API。 |
| 长期 Memory / 业务产物向量记忆 | 仅设计 | 4.5/4.6 明确不做业务产物 embedding 和 Milvus 写入。 |

### 1.4 当前主要架构演进

项目先形成了多个固定拓扑 LangGraph 和各自的业务 run 表，随后增加固定串行销售协作 Graph。现在正在验证一个与业务领域解耦的 Agent Runtime Core，希望未来用统一的 Run、State、AgentStep、Capability、Trace、Audit 契约承载更通用的 Agent 执行。

本阶段只完成了 Runtime 的最小同步 Core。它与旧 Graph 并存，不应把“未来可包装为 capability”写成“已经接入 Runtime”。

---

## 2. 仓库结构

以下是经过筛选的结构，而非逐文件清单：

```text
XF_Mould_Agent_Platform/
├─ api.py                         # FastAPI 主入口、认证、会话、业务 API 与 SSE
├─ graph.py                       # Supervisor 路由型主问答 Graph
├─ fmea_graph.py                  # FMEA 独立业务 Graph
├─ audit_graph.py                 # Audit 独立业务 Graph
├─ report_graph.py                # Report 独立业务 Graph
├─ state.py                       # 现有 LangGraph 共享 State 契约
├─ chat_memory.py                 # PostgreSQL 对话滑动窗口与滚动摘要 Memory V1
├─ config.py                      # LLM、Embedding、Milvus、Redis、PostgreSQL 配置
├─ agents/                        # Supervisor、问答 Agent、业务生成器与销售协作角色
│  └─ agent_specs/                # 部分 Agent 的说明性规格
├─ graphs/                        # 销售协作等独立 Graph
├─ runtime/                       # 新 Agent Runtime Core
│  ├─ capabilities/               # Capability Registry、Runner 与 demo capability
│  ├─ loop/                       # Decision Provider 边界
│  ├─ repositories.py             # Runtime 五类记录的 tenant-scoped repository
│  ├─ service.py                  # 同步两步 Agent Loop 应用服务
│  ├─ state_machine.py            # Run 生命周期规则
│  └─ tenant_context.py           # Runtime tenant 边界验证
├─ schemas/                       # Pydantic API、业务和 Runtime 契约
├─ models/                        # SQLAlchemy 业务、聊天、协作和 Runtime 模型
├─ services/                      # 业务产物追改服务
├─ repositories/                  # 销售协作持久化 repository
├─ verifiers/                     # FMEA、Audit、产物追改规则校验
├─ tools/                         # RAG、检索 query 规划和天气工具
├─ knowledge/                     # DOCX/PDF 解析、切块、Embedding 与 Milvus 入库
├─ skills/                        # FMEA/Audit/Report 的业务规则与模板资源
├─ alembic/                       # PostgreSQL migration，当前到 revision 011
├─ tests/                         # 默认自动化回归与 Runtime focused tests
├─ eval_cases/                    # FMEA/Audit/Report 和销售协作案例数据/脚本
├─ web/                           # React + TypeScript + Vite 前端
├─ openspec/                      # 当前架构变更 proposal/design/spec/tasks
└─ docs/                          # 业务契约、路线图、技术债和项目说明
```

补充说明：

- `app.py` 是仍保留的旧 Streamlit + Redis 会话入口，不是当前 Docker Compose 的 React 主前端。
- `main.py` 是直接运行主问答 Graph 的 CLI 入口。
- `runtime/context/`、`runtime/events/`、`runtime/knowledge/`、`runtime/runs/`、`runtime/state/`、`runtime/tools/`、`runtime/workers/` 目前主要是模块边界占位，不代表对应能力已经实现。

---

## 3. 当前系统架构

### 3.1 已有业务 Agent / LangGraph 架构

```text
React Web
   │
   ▼
FastAPI (`api.py`) ── JWT/HttpOnly Cookie ── PostgreSQL 用户与会话
   │
   ├─ `/api/ask/stream`
   │      ▼
   │   Supervisor Graph (`graph.py`)
   │      ├─ rd_rag ──> rd_writer ──> SSE token/done
   │      ├─ qa_rag ──> qa_writer ──> SSE token/done
   │      └─ chat_chat ──> 可选 weather tool ──> SSE token/done
   │             │
   │             ├─ Milvus + Embedding（R&D/Quality）
   │             └─ PostgreSQL ChatMessage + ChatSessionSummary
   │
   ├─ `/quality/fmea/generate` ──> FMEA Graph ──> fmea_runs + artifact version V1
   ├─ `/quality/audit/check` ────> Audit Graph ──> audit_runs
   ├─ `/quality/report/generate` ─> Report Graph ─> report_runs
   ├─ `/quality/artifacts/...` ──> FMEA 追改/版本服务
   └─ `/sales/proposals/...`
          ▼
       固定串行 Sales Collaboration Graph
       Intake -> Planner -> R&D Specialist -> Quality Specialist
              -> Reviewer -> Proposal Writer -> Final Verifier -> Persist
          │
          └─ collaboration_runs + collaboration_steps
```

这些 Graph 是固定节点和固定/条件边的业务工作流。FMEA、Audit、Report 不接主 Supervisor；销售协作也有独立 API，不通过主聊天 Supervisor 自动触发。

### 3.2 新 Agent Runtime Core

```text
当前调用者：focused tests / 未来 adapter
   │
   ▼
RuntimeCoreService.execute()
   │
   ├─ 创建 Run + State v1 + initial Trace + initial Audit
   │
   ├─ AgentStep 1
   │    └─ Decision Provider -> invoke-capability
   │          └─ Capability Registry / Runner
   │                └─ demo.echo -> CapabilityResult
   │                      └─ State v2
   │
   └─ AgentStep 2
        └─ Decision Provider -> finish
              └─ State v3 -> Run completed

所有边界记录通过 RuntimeRepository 写入 PostgreSQL/SQLAlchemy。
```

当前接入状态：

- 公开 Run API：未接入；`api.py` 没有 Runtime create/status/cancel 等 endpoint。
- React：未接入；没有 Runtime Run/Trace 页面。
- 真实 LLM Decision Provider：未接入；只有 `ScriptedDecisionProvider`。
- 真实业务 capability：未接入；注册表中只有无副作用的 `demo.echo`。
- 现有 RAG、FMEA、Audit、Report、Chat、Sales Graph：均未包装为 Runtime capability。
- Redis、Celery、worker：Runtime Core 不依赖，也未实现。
- Runtime resume/checkpoint/replay：未实现。

因此，Runtime Core 是独立的 domain-neutral vertical slice，不是现有产品请求的执行引擎。

---

## 4. Runtime Core 当前真实状态

### 4.1 核心对象

- **Run**：一次 Runtime 执行的稳定身份与生命周期。保存 `runtime_run_id`、tenant、goal、状态、时间和终止原因。当前状态只有 `queued`、`running`、`completed`、`failed`。
- **StateSnapshot**：某个持久化边界上的不可变 canonical State。通过同一 Run 内递增的 version 形成历史；它不是给 LLM 的 prompt Context，也不是可恢复 worker checkpoint。
- **AgentStep**：一次有序决策迭代，保存输入/输出 State version、ActionDecision、CapabilityResult、状态、错误、耗时和 idempotency key。
- **ActionDecision**：Decision Provider 对“下一步做什么”的结构化输出。当前只接受 `invoke-capability` 和 `finish`。
- **CapabilityResult**：Capability Runner 归一化后的成功或失败结果，包含 capability、tenant、Run、execution id、idempotency key、输出/错误和耗时。
- **TraceEvent**：面向诊断和运行观察的追加式时间线，如 lifecycle、action decision、capability result、state updated、error。
- **AuditEvent**：面向责任归属的追加式操作记录，包含 actor、operation、target、outcome 等有限字段，不保存隐藏推理。
- **Decision Provider**：从当前 State 和 step index 产生下一条 ActionDecision 的可替换接口。现在只有确定性的脚本实现，没有真实 LLM adapter。
- **Capability Registry / Runner**：显式白名单式的 capability 注册、参数校验、tenant 校验、调用、异常归一化和结果复用边界。
- **Demo Capability**：`demo.echo`，接收一个字符串并原样返回；无外部调用和副作用，只用于证明 Core 闭环。

### 4.2 当前 Agent Loop

`RuntimeCoreService` 在当前进程同步执行，默认 `max_steps=2`：

```text
Run created
  -> State v1 (queued)
  -> AgentStep 1
  -> invoke-capability
  -> demo.echo
  -> CapabilityResult
  -> State v2 (running，包含结果)
  -> AgentStep 2
  -> finish
  -> State v3 (completed)
  -> Run completed
```

第二次 Decision Provider 调用会收到 State v2，因此 capability 输出确实进入了下一轮决策输入。

### 4.3 支持与不支持的 Action

已支持：

- `invoke-capability`
- `finish`

明确不支持：

- `respond`
- `ask-user`
- `retrieve-evidence`
- `call-tool`
- `wait-approval`
- cancel/wait/timeout 等异步生命周期动作
- 任意未注册 action 或 capability

非法决策、未知 capability、tenant 不匹配、capability 错误或步数耗尽都会 fail closed，并写入可观察的失败记录。

---

## 5. Runtime 持久化设计

Runtime Core 只使用五类记录：

| 表 | 回答的问题 |
| --- | --- |
| `runtime_runs` | 这次执行是谁、属于哪个 tenant、目标是什么、当前/最终状态是什么？ |
| `runtime_state_snapshots` | 每个持久化边界上的 canonical State 是什么？状态如何随 version 演进？ |
| `runtime_agent_steps` | 第几步作出了什么决策、消费/产生哪个 State version、结果和耗时是什么？ |
| `runtime_trace_events` | 运行时按顺序发生了什么，诊断时间线是什么？ |
| `runtime_audit_events` | 谁对什么目标执行了什么操作，结果如何？ |

关键设计：

- State 使用版本化 Snapshot，而不是覆盖一条 current-state 行。成功路径明确保留 v1、v2、v3，便于证明顺序和读取历史。
- 当前 `AgentStep` 取代了未发布草稿中的 `ActionRecord`；仓库中不存在并行保留的 Runtime ActionRecord 表。
- Trace 与 Audit 分开：Trace 服务于运行诊断，Audit 服务于归责、保留和安全查询，两者字段和生命周期需求不同。
- CapabilityResult 没有独立表。它保存在 `runtime_agent_steps.result_json`，并复制进后续 `runtime_state_snapshots.state_json` 的 `capability_results`。
- 每个 Runtime contract 和持久化记录都带 `tenant_id`。Repository 查询先验证 `TenantContext`，再按 Run 和 tenant 限定；跨 tenant 读写会被拒绝。
- 幂等边界由 `(runtime_run_id, idempotency_key)` 唯一约束体现。已完成结果存在时，Runner 返回持久化结果，不再次调用 capability。
- 每个持久化边界使用事务：初始化 bundle、capability step、finish step 分别保持内部原子性。

对应实现主要位于 `schemas/runtime.py`、`models/runtime.py`、`runtime/repositories.py`、`runtime/service.py` 和 migration `011_create_runtime_core.py`。

---

## 6. 现有业务能力

| 能力 | 实现状态与作用 | 已接入新 Runtime Core？ |
| --- | --- | --- |
| Chat | 已实现。主问答、会话管理、消息持久化、自动标题、闲聊和天气 tool。 | 否 |
| RAG | 已实现。FMEA/VDA 6.4 双 collection 文档检索和结构化引用。 | 否 |
| FMEA | 已实现 MVP。结构化 rows、S/O/D/AP 建议值、验证、最多一次修复、Markdown、run 保存。 | 否 |
| Audit | 已实现 MVP。结构化 findings、规则验证、最多一次修复、Markdown、run 保存。 | 否 |
| Report | 已实现 MVP。基于用户显式选择的 FMEA/Audit run、可选 RAG 和背景生成质量问题报告。 | 否 |
| Artifact Revision | 部分实现。通用版本模型/API 已有，实际只打通 FMEA 追改；Audit/Report 返回预留能力错误。 | 否 |
| Sales Multi-Agent / Collaboration | 已实现固定串行 MVP。多个角色共同生成售前方案，并保存 Run/Step。 | 否 |
| Verifier / Repair | 已实现于 FMEA/Audit/Report；FMEA/Audit/Report 最多 repair 一次。销售协作有 Reviewer 和 Final Verifier，但没有通用 Runtime repair loop。 | 否 |
| Memory V1 | 已实现。PostgreSQL 中 20 条滑动窗口、40 条触发滚动摘要、2 分钟孤儿 user 消息清理。 | 否 |
| PostgreSQL | 已实现主事实存储：用户、会话、业务 run、版本、协作和 Runtime Core。 | Runtime 自身使用 |
| Milvus | 已实现文档知识向量索引与检索。业务产物不写入 Milvus。 | 否 |
| SSE | 已实现主聊天 token/status/done/error 流；业务生成 API 主要是同步 JSON。 | 否 |
| React | 已实现认证、聊天、FMEA、Audit、Report、销售协作页面。 | 否 |
| Auth | 已实现 JWT + HttpOnly Cookie、Argon2 密码哈希和 user-scoped 资源访问。 | Runtime 尚无 auth adapter |

必须区分两个“Run”体系：FMEA/Audit/Report/Collaboration 的业务 run 是现有产品记录；`runtime_runs` 是新 Core 的执行身份。它们目前没有关联或转换关系。

---

## 7. Agent / Graph / Workflow 结构

### 7.1 主问答 Graph

`graph.py` 是固定 Graph：

- Supervisor 使用 LLM 结构化路由，也允许 `agent_override`。
- `rd` 路由执行 FMEA 知识 RAG，再由 R&D Writer 回答。
- `quality` 路由执行 VDA 6.4 知识 RAG，再由 Quality Writer 回答。
- `chat` 路由执行闲聊 Agent，必要时调用天气 tool。

它是“从多个 Agent 中选择一个”的路由型 Multi-Agent，不是多个 Agent 协作完成同一结果。

### 7.2 质量业务 Graph

- FMEA：Intake -> Retrieval Planner -> RAG -> Generate -> Verify -> 可选 Repair Once -> Writer -> Persist。
- Audit：Intake -> Retrieval Planner -> RAG -> Check -> Verify -> 可选 Repair Once -> Writer -> Persist。
- Report：Intake -> Load Sources -> Source Match -> Optional RAG -> Context Builder -> Writer -> Verify -> 可选 Repair Once -> Persist -> Final Response。

Writer 的职责是确定性包装/渲染，不应修改已校验的结构化业务事实。

### 7.3 销售协作 Graph

固定串行拓扑：

```text
Request Intake
 -> Planner
 -> R&D Specialist
 -> Quality Specialist
 -> Reviewer
 -> Proposal Writer
 -> Final Verifier
 -> Persist Run
```

- Planner 生成执行计划；识别到 FMEA/Audit 时只记录 optional artifact，占位但不自动调用专业 workflow。
- 两个 Specialist 分别检索 FMEA 和质量知识库，并输出统一结构。
- Reviewer 同时使用规则和可选 LLM 检查冲突、无依据强结论、角色越界和缺失内容。
- Proposal Writer 只能从已存在的结构化事实中选择内容，避免凭空新增关键事实。
- Final Verifier 做最小完整性检查。
- API 在 Graph 返回后统一保存 `collaboration_runs` 和 `collaboration_steps`。

### 7.4 与新 Runtime 的关系

上述全部仍是 LangGraph 固定工作流。新 Runtime 使用循环式 Decision Provider + Capability Runner 契约。两套机制当前并存；Runtime 没有取代旧 Graph，也没有把旧 Graph 注册为 capability。

---

## 8. RAG 与知识系统

### 8.1 当前真实流程

```text
DOCX / PDF
 -> 解析段落、标题、表格与页码
 -> 结构感知切块
 -> DashScope Embedding
 -> Milvus（FMEA / Quality 两个 collection）
 -> query embedding
 -> Milvus 检索
 -> table chunk 扩展、metadata、citation map
 -> R&D / Quality / FMEA / Audit / Report / Sales Specialist
```

已实现的细节：

- DOCX 和 PDF 解析；没有当前公开上传 API。
- 普通文本 chunk。
- 小表 chunk，以及大表的 `table_parent`、`table_summary`、`table_row_block` 多粒度表示。
- `table_summary` 命中后按 `table_id` 补取最多三个 row block。
- `chunk_uid`、source、chapter、section、heading path、table id、row range、source file、PDF page range 等 metadata。
- Milvus 使用 `hybrid_search` API 和 `RRFRanker`，但当前只构造一个 dense vector request；没有可确认的 sparse/BM25 分支或 cross-encoder reranker。
- FMEA/Audit 有规则词典式 query expansion；Report 和销售 Specialist 也会按业务上下文构造 query。没有通用的 LLM query-expansion service。
- R&D/Quality Writer 会把引用 ID 限定在真实 `citation_map` 中；销售 Writer 也只允许选择上游提供的 citation/事实 ID。

尚未实现或不能据代码确认的内容：

- tenant-scoped 用户文件上传、文件版本和 ingestion job。
- Runtime `retrieve-evidence` action、EvidenceSet 和 Knowledge Service。
- 业务产物向量化、业务产物相似召回、Memory V2。
- `table_parent` 的通用自动回溯路径；当前明确实现的是 summary 到 row block 的扩展。

Runtime Core 当前完全不调用 RAG。

---

## 9. Memory、State 与 Checkpoint

这些概念在当前仓库中不能混用：

| 概念 | 当前状态 | 说明 |
| --- | --- | --- |
| Runtime State | 已实现 | `StateSnapshot` 是新 Core 单次 Run 的 canonical、版本化状态。 |
| Chat Memory V1 | 已实现 | PostgreSQL `ChatMessage` + `ChatSessionSummary`；注入主问答 Graph。 |
| Long-term Memory / Memory V2 | 未实现 | 只有设计文档，不做业务产物 embedding 或长期召回。 |
| LangGraph Checkpoint | 未实现 | 现有 Graph 未配置 Redis/PostgreSQL checkpointer，中途退出不能从节点恢复。 |
| Runtime Checkpoint | 未实现 | Core 刻意排除 checkpoint/resume/replay；State Snapshot 不能被描述为已实现的 resume checkpoint。 |

Memory V1 只服务主聊天。FMEA、Audit、Report 的独立 API 明确不写 ChatMessage，也不触发该 Memory；Report 的来源以显式 `fmea_run_id` / `audit_run_id` 为主，不能用 `session_id` 假设同一质量案例。

---

## 10. API 与运行入口

### 10.1 主要 API 类别

- 认证：注册、登录、登出、当前用户。
- 会话：列表、创建、重命名、删除、分页读取消息。
- 主聊天：`POST /api/ask/stream`，返回 SSE。
- FMEA：独立生成入口。
- Audit：独立检查入口。
- Report：来源列表和生成入口。
- 业务产物：按会话列表、追改、版本列表和版本详情。
- 销售协作：生成方案、查询 Run、查询步骤。
- 健康检查。

当前没有：

- Runtime Run create/status/cancel/respond/approve API。
- Runtime Trace/Audit 查询 API。
- 文件上传、ingestion job 或通用 Knowledge retrieval API。
- FMEA/Audit/Report 的统一后台任务 API。

### 10.2 运行入口

- 生产形态入口：`uvicorn api:app` + React 静态前端。
- 本地容器：`docker compose up --build`。
- CLI：`python main.py`，直接执行主问答 Graph。
- 旧入口：`app.py` 使用 Streamlit + Redis，当前 compose/React 主链路不依赖它。
- 知识初始化：手动执行 `python knowledge/ingest.py`。

---

## 11. 数据库与基础设施

### 11.1 PostgreSQL

PostgreSQL 是当前主链路的关系事实存储，保存：

- 用户、聊天会话、消息、滚动摘要；
- FMEA、Audit、Report 业务 run；
- 业务产物不可变版本；
- 销售协作 Run/Step；
- 新 Runtime 的 Run/State/AgentStep/Trace/Audit。

Alembic migration 当前从 `001` 到 `011`，Runtime Core 位于 `011_create_runtime_core.py`。

### 11.2 Milvus、etcd、MinIO

- Milvus 实际用于 FMEA/VDA 6.4 文档知识向量索引和检索。
- etcd 和 MinIO 是 Milvus standalone 的依赖。
- MinIO 当前没有被实现为用户上传文件的产品级对象存储入口。

### 11.3 Redis

Redis 依赖、配置和 Compose 服务存在，旧 `app.py` 使用它保存 Streamlit 会话和消息。但当前 React + FastAPI 主链路的认证、聊天事实、Memory V1、业务 run 和 LangGraph 都不依赖 Redis；没有 Redis checkpointer、queue 或 event stream。

### 11.4 Celery

未实现，也不在 requirements 中。`runtime/workers/` 只是边界占位。大型自主 Runtime OpenSpec 中的异步 worker 是未来设计。

### 11.5 Docker

Compose 定义七个服务：frontend、backend、postgres、redis、milvus、etcd、minio。依赖被定义不等于每项都进入当前产品主链路；尤其 Redis/MinIO 的现状应按上述边界理解。

---

## 12. 测试与验证状态

### 12.1 本次仓库快照的可复现结果

2026-08-28 在当前工作区执行：

- Runtime Core focused tests：`37 passed in 0.82s`。
- 默认 `pytest -q`：`164 passed, 5 deselected, 1 warning in 4.70s`。
- OpenSpec：`openspec.cmd validate --all --strict`，`2 passed, 0 failed`。
- React：`npm.cmd run build` 成功，TypeScript 编译和 Vite production build 通过。

默认 pytest 配置明确：

- 排除 `real_llm` marker；5 个真实 LLM smoke tests因此 deselected。
- 忽略 `tests/test_pdf_chunking.py`。

### 12.2 Runtime tests 能证明什么

37 个 focused tests 覆盖：

- Pydantic contract 和只允许两种 action；
- tenant 边界、Run 状态机和跨 tenant 拒绝；
- 五类 SQLAlchemy metadata 和 migration 声明；
- Repository 新 session 读取、不可变 State、AgentStep finalize；
- Decision Provider 第二步观察 State v2；
- Capability 参数校验、未知 capability、失败归一化和结果复用；
- 两步 happy path、失败路径、max steps；
- SQLite 测试数据库中的 durable readback 和事务回滚行为。

### 12.3 测试不能证明什么

- 不能证明 Runtime 已接真实 LLM、真实业务 capability、FastAPI 或 React。
- 不能证明 Redis/Celery/MinIO/Milvus 与 Runtime 的端到端链路。
- 不能证明 worker restart、resume、checkpoint、cancel 或 approval。
- 默认回归不能证明真实 DashScope、Embedding、Milvus 和 PostgreSQL 服务集成质量；大量测试使用 Fake/Mock 和 SQLite。
- 不能证明真实 FMEA/Audit 输出质量稳定。`eval_cases/fmea` 和 `eval_cases/audit` 是调用实际 Graph/外部依赖的独立脚本，不属于默认 pytest。
- `tests/test_real_llm_smoke.py` 存在，但只有显式设置 `REAL_LLM_TESTS=1` 才执行；本次没有执行真实 LLM 测试。

### 12.4 PostgreSQL clean migration 的证据边界

`add-agent-runtime-core/tasks.md` 的 4.3 已勾选，记录为“已在干净 PostgreSQL 应用 migration”。当前仓库测试还对 upgrade/downgrade 声明做了静态/fake-op 验证。

但本次检查时 `docker compose ps` 没有运行中的服务，因此没有重新执行一遍真实 clean PostgreSQL migration，也没有独立 CI 日志可供本文引用。结论应表述为：**OpenSpec 验收记录声称已完成；本次只复现了 migration 声明测试，未复现真实 PostgreSQL clean migration。**

---

## 13. OpenSpec 当前状态

`openspec/changes/` 目前有两个 active change，archive 目录为空。

### 13.1 Active Changes

#### `add-agent-runtime-core`

- 目标：把大型自主 Runtime 拆小，先完成同步、单进程、两步、可持久化的最小 Core。
- 任务状态：15/15，100%。
- 验证状态：strict validation 通过；focused tests 和默认回归通过。
- 是否继续：不应继续向该 change 塞入 LLM、API、tool、worker 等新 scope。合理动作是完成评审、补齐所需的真实 PostgreSQL 验收证据后归档；后续能力另开较小 change。

#### `add-autonomous-agent-runtime`

- 目标：完整自主 Runtime，包括异步 worker、更多 action、Context、tool、文件上传、知识入库、业务 adapter、API、事件流和前端。
- 任务状态：3/41，约 7.3%。
- 当前已勾选项主要是早期模块边界、初版 schema 和旧持久化地基；其余绝大多数未完成。
- 是否继续：不能按“已完成 Core”理解，也不宜直接把 38 个剩余任务视为下一次必须一次完成。应先根据新 Core 的事实更新/拆分该 change，并消除旧 ActionRecord/Checkpoint 描述与当前 AgentStep/五表 Core 的冲突。

### 13.2 两个 Change 的关系

`add-agent-runtime-core` 明确 supersede `add-autonomous-agent-runtime` 的 **Runtime Core scope**，但没有完成、归档或取代后者的全部目标。

也就是说：

- 新 Core 的 Run/State/AgentStep/Trace/Audit 和两步 loop 是当前事实。
- 旧 change 中涉及 Core 的 ActionRecord/Checkpoint 初稿不再是当前 Core 设计。
- 旧 change 的 worker、tools、knowledge ingestion、business adapters、API、frontend 等剩余能力仍未实现。
- 旧 change 不能标为完成；归档区当前也没有已归档 change。

---

## 14. 当前技术债和未完成项

以下仅整理已能从代码、OpenSpec、TODO 和测试确认的事项。

### 14.1 高优先级

1. 完成 `add-agent-runtime-core` 的评审/验收闭环，保留可追溯的真实 PostgreSQL clean migration 结果，然后归档该 change。
2. 更新或拆分 `add-autonomous-agent-runtime`，删除被新 Core supersede 的旧 Core 假设，避免 OpenSpec 同时描述两套冲突模型。
3. 为下一阶段单独定义真实 Decision Provider 和公开 Runtime entry adapter；当前 Core 只有 scripted provider，产品无法创建 Run。
4. 明确首个真实业务 capability adapter 的边界并做兼容回归；当前任何旧 Graph 都未接 Runtime。

### 14.2 中优先级

1. 为 Runtime 增加安全的 Run 状态/记录查询 API 和 auth-to-tenant adapter。
2. 根据真实长任务需求设计异步化、取消、超时和任务事件；当前同步请求会占用调用线程。
3. 统一 FMEA、Audit、Report 和 Collaboration 的前端任务生命周期、页面切换保护和结果恢复。
4. 补充真实 PostgreSQL、Milvus、Embedding/LLM 的受控集成测试，并把结果和普通 Mock regression 分开报告。
5. 评估 LangGraph Checkpointer 或 Runtime resume 的职责边界，避免把 State Snapshot 误当 checkpoint。

### 14.3 更远方向

1. Tool Registry / ToolExecutor、权限、审批、shell/file 安全控制。
2. Celery/Redis worker、checkpoint/resume/replay 和多种等待状态。
3. tenant-scoped 文件上传、文件版本、ingestion job、对象存储和 EvidenceSet。
4. Runtime Context Builder、Memory 与 Evidence 分层。
5. 业务产物长期 Memory、混合相似匹配和 `quality_cases`；必须遵守先稳定元数据、后向量化的阶段约束。
6. 多 Agent 并发和更广的自动编排；当前销售协作串行实现应先通过质量评测证明价值。

---

## 15. 当前项目演进路线

```text
已完成
  ├─ React + FastAPI + PostgreSQL 产品主链路
  ├─ Supervisor 路由问答 + FMEA/VDA 6.4 RAG
  ├─ FMEA / Audit / Report 独立工作流
  ├─ FMEA 追改与业务产物版本底座
  ├─ 固定串行销售协作 Multi-Agent MVP
  └─ 独立同步 Runtime Core vertical slice
         Run -> State -> AgentStep -> Capability -> State -> finish

最合理的下一阶段
  ├─ 验收并归档 Runtime Core change
  ├─ 清理大型 Autonomous Runtime change 的重叠 scope
  ├─ 增加真实结构化 Decision Provider
  ├─ 增加最小、tenant-safe 的 Run API/查询入口
  └─ 选择一个现有业务 Graph 做 capability adapter 兼容验证

更远期
  ├─ 异步 worker、事件、取消、等待、resume/checkpoint
  ├─ ToolExecutor 与审批/沙箱
  ├─ 用户文件上传与 tenant-scoped Knowledge/Evidence
  ├─ 统一业务任务生命周期和前端 Runtime 视图
  └─ 长期 Memory、案例关联、并行 Agent 和生产化治理
```

这条路线不要求一次完成大型 `add-autonomous-agent-runtime` 的全部 41 项任务。当前最有价值的是先把已验证的 Core 变成稳定边界，再逐层接入真实决策、公开入口和一个业务 capability。

---

## 16. 关键文件索引

- `api.py` — 当前 FastAPI 主入口、认证、会话、业务 API 和 SSE。
- `graph.py` — Supervisor 路由型主问答 LangGraph。
- `fmea_graph.py` — FMEA 生成、验证、有限修复和持久化工作流。
- `audit_graph.py` — Audit 检查、验证、有限修复和持久化工作流。
- `report_graph.py` — Report 来源加载、匹配、生成、验证和持久化工作流。
- `graphs/sales_collaboration_graph.py` — 固定串行销售协作 Multi-Agent Graph。
- `state.py` — 现有业务 LangGraph State。
- `schemas/runtime.py` — Runtime Run、State、ActionDecision、CapabilityResult、AgentStep、Trace、Audit 契约。
- `runtime/service.py` — 同步两步 Runtime Agent Loop 和事务边界。
- `runtime/loop/decision.py` — Decision Provider protocol 与 scripted provider。
- `runtime/capabilities/core.py` — Capability Registry 和 Runner。
- `runtime/capabilities/demo.py` — `demo.echo` capability。
- `runtime/tenant_context.py` — Runtime tenant 可信上下文和隔离校验。
- `runtime/repositories.py` — 五类 Runtime 记录的持久化操作。
- `models/runtime.py` — Runtime SQLAlchemy 五表模型。
- `alembic/versions/011_create_runtime_core.py` — Runtime Core migration。
- `tools/rag.py` — Embedding、Milvus 检索、table chunk 扩展和统一 metadata。
- `knowledge/ingest.py` — DOCX/PDF 解析后切块、Embedding 和 Milvus 入库。
- `knowledge/pdf_parser.py` — PDF 标题、正文、表格和页码解析。
- `chat_memory.py` — Chat Memory V1 滑动窗口、摘要和孤儿清理。
- `models/fmea.py`、`models/audit.py`、`models/report.py` — 三类质量业务 run。
- `models/artifact_version.py` — 通用不可变业务产物版本链。
- `models/collaboration.py` — 销售协作 Run/Step。
- `services/artifact_revision_service.py` — 业务产物追改服务，当前实际开放 FMEA。
- `web/src/App.tsx` — React 主应用、会话、SSE 和业务页面切换。
- `web/src/pages/SalesProposalPage.tsx` — 销售协作任务展示和轮询恢复。
- `openspec/changes/add-agent-runtime-core/` — 当前已完成的最小 Runtime Core 变更。
- `openspec/changes/add-autonomous-agent-runtime/` — 尚未完成的大型自主 Runtime 规划。
- `docs/BUSINESS_ARTIFACT_CONTRACT.md` — 4.5 业务产物元数据事实契约。
- `docs/BUSINESS_ARTIFACT_REVISION_MVP.md` — 4.6 追改与版本边界。
- `docs/MVP_ROADMAP.md` — 业务产物阶段路线。
- `docs/TECH_DEBT_AND_NEXT_STEPS.md` — 已确认技术债和后续边界。

---

## 17. 后续 AI 的事实约束

后续修改本项目时，至少遵守以下事实：

1. 不要把 `session_id` 当成 `quality_case_id`。
2. run 级业务产物类型字段是 `artifact_type`，不是 `source_type`。
3. `retrieved_refs_json` 是检索原始引用，`references_json` 是统一引用摘要，不能混用。
4. 当前业务产物不做 embedding、不写 Milvus；Memory V2 尚未实现。
5. Runtime State、Chat Memory 和 Checkpoint 是不同概念。
6. 新 Runtime 没有接入现有 Graph、API、前端、真实 LLM 或 RAG。
7. `runtime_runs` 与 FMEA/Audit/Report/Collaboration run 不是同一套记录。
8. Runtime 当前只允许 `invoke-capability` 和 `finish`。
9. FMEA/Audit/Report repair 最多一次；不得编造标准条款。
10. README 和部分路线文档可能滞后；判断现状时优先看当前代码、migration 和可复现测试。

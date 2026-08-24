# Phase Implementation Tracker

## 1. 文档用途

本文档用于记录 Phase A-J 的实际执行进度、变更边界、验收状态和测试结果。

- 主路线来源：[`PROJECT_STATUS_AND_MULTI_AGENT_ROADMAP.md`](./PROJECT_STATUS_AND_MULTI_AGENT_ROADMAP.md)
- 本文档不替代主路线图，不重新定义架构目标。
- 主路线图发生调整时，应先更新主路线图，再同步本文档。
- 每次阶段开发完成后，应更新已完成事项、测试结果、遗留问题和 commit hash。

## 2. 状态说明

| 状态 | 含义 |
| --- | --- |
| `Completed` | 阶段任务与验收标准全部完成 |
| `In Progress` | 阶段正在实施 |
| `Next` | 下一阶段，尚未开始代码实施 |
| `Not Started` | 尚未开始 |
| `Blocked` | 存在明确阻塞条件 |

## 3. 总览

| Phase | 名称 | 当前状态 | 最近测试结果 | Commit |
| --- | --- | --- | --- | --- |
| A | 基线冻结与回归保护 | `In Progress` | `15 passed, 1 warning in 2.58s` | `TBD` |
| B | 协作数据契约 | `In Progress` | `85 passed in 2.02s` | `TBD` |
| C | 最小串行多智能体 MVP | `Completed` | `123 passed, 1 warning in 2.62s` | `TBD` |
| D | 协作前端与任务生命周期 | `Not Started` | 未运行 | `TBD` |
| E | 多智能体质量评估 | `Not Started` | 未运行 | `TBD` |
| F | Planner 路由与按需专业工作流 | `Not Started` | 未运行 | `TBD` |
| G | 并行化与可靠性 | `Not Started` | 未运行 | `TBD` |
| H | Memory V2 实现 | `Not Started` | 未运行 | `TBD` |
| I | 业务产物自动关联与案例系统 | `Not Started` | 未运行 | `TBD` |
| J | 生产化与后续优化 | `Not Started` | 未运行 | `TBD` |

## 4. Phase A：基线冻结与回归保护

### 目标

在多智能体改造前冻结当前 Supervisor、专业 Agent 引用和质量工作流 API 行为。

### 范围

- Supervisor 的 `rd`、`quality`、`chat` 路由回归。
- R&D、Quality Agent 引用输出契约。
- FMEA、Audit、Report 和 Report Sources API 快照。
- 当前端到端延迟、模型调用次数和成本基线。
- README 中当前功能与测试方式说明。

### 允许修改

- `tests/`
- 最小 pytest 配置和开发测试依赖。
- Phase A 相关文档与 README。
- 不改变运行行为的极小测试可注入调整，但必须单独说明。

### 禁止修改

- 不新增协作图或 Planner。
- 不实现 Phase B/C 数据结构或流程。
- 不修改 Memory V1。
- 不修改 Milvus 入库逻辑。
- 不重构前端。
- 不改变现有 API response 字段。
- 不改变 FMEA、Audit、Report graph 业务行为。

### 计划任务

- [x] 为 Supervisor 三类路由补回归测试。
- [x] 为 R&D、Quality 引用结构补契约测试。
- [x] 为 FMEA、Audit、Report API 补快照测试。
- [ ] 记录现有端到端延迟、模型调用次数和估算成本。
- [ ] 修订 README，使其反映当前 FMEA、Audit、Report 和版本追改状态。

### 已完成事项

- 新增 `tests/test_supervisor_routing.py`。
- 新增 `tests/test_agent_citation_contract.py`。
- 新增 `tests/test_quality_workflow_api_snapshots.py`。
- 新增最小 pytest 配置和开发测试依赖。
- 普通回归测试已隔离真实 LLM、Milvus、Embedding API 和 PostgreSQL。
- 已冻结 Supervisor 默认解析失败时路由到 `rd` 的当前行为。

### 验收标准

- [x] Phase A 最小回归测试全部通过。
- [x] 三个现有专业问答路由受到回归保护。
- [x] FMEA、Audit、Report 和 Report Sources API 返回契约受到保护。
- [ ] 形成可比较的质量、延迟、调用次数和成本基线。
- [ ] README 与当前实现状态一致。

### 测试命令

```powershell
pytest tests/test_supervisor_routing.py tests/test_agent_citation_contract.py tests/test_quality_workflow_api_snapshots.py -q
```

记录结果：

```text
15 passed, 1 warning in 2.58s
```

### 当前状态

`In Progress`

Phase A 最小回归测试已完成；性能、调用次数、成本基线和 README 更新尚未完成，因此阶段暂不标记为 `Completed`。

### 遗留问题

- 尚未记录 live eval 的端到端延迟。
- 尚未统计各工作流真实模型调用次数。
- 尚未形成估算成本基线。
- README 尚未按主路线要求完成现状修订。
- `tests/test_pdf_chunking.py` 是手工脚本，当前通过 pytest 配置排除自动收集。

### 相关 Commit Hash

`TBD`

## 5. Phase B：协作数据契约

### 目标

在实现协作图前确定 Agent 间结构化交接协议和可追溯状态契约。

### 范围

- `SalesCollaborationState`。
- Planner、Specialist、Reviewer 的 Pydantic schema。
- citation、claim、risk、missing information 格式。
- 稳定错误码、任务状态和协作持久化模型设计。

### 允许修改

- 新增协作 schema 和对应单元测试。
- 新增状态、错误码和持久化设计文档。
- 经评审后新增必要数据库模型与 migration。

### 禁止修改

- 不新增或执行协作 LangGraph。
- 不接管 `/api/ask/stream`。
- 不实现前端协作页面。
- 不修改 Memory V1 或 Milvus 入库逻辑。
- 未完成数据契约前不实现 Planner 运行逻辑。

### 计划任务

- [x] 定义 `SalesCollaborationState`。
- [x] 定义 Planner、Specialist、Reviewer schema。
- [x] 定义引用、结论、风险和信息缺口契约。
- [ ] 定义错误码和任务状态。
- [x] 设计 `collaboration_runs`、`collaboration_steps`。
- [x] 编写 schema 和非法输出测试。
- [x] 整理 Schema、State 和 DB Model 的职责、映射及数据流转文档。

### 已完成事项

- Phase B-B1 已在 `state.py` 新增 `SalesCollaborationState`，并新增协作 Pydantic schema。
- Phase B-B1 已覆盖合法数据、非法 Agent、非法置信度、缺少必填字段和字段稳定性测试。
- Phase B-B2 已新增 `CollaborationRun`、`CollaborationStep` SQLAlchemy 模型及一对多关系。
- Phase B-B2 已新增 `010_create_collaboration_runs_and_steps.py` migration。
- Phase B-B2 已覆盖内存 SQLite 建表、CRUD、JSON 持久化、关系和复合唯一约束测试。
- run 和 step 状态已通过数据库 `CHECK` 约束限定。
- Phase B-B3 已新增 [`SALES_COLLABORATION_DATA_CONTRACT.md`](./SALES_COLLABORATION_DATA_CONTRACT.md)，明确 Schema 校验、State 流程传递和 DB 持久化三层职责。
- Phase B-B3 已记录字段映射、典型数据流转、Run/Step 保存边界和当前未实现项。

### 验收标准

- Schema 单元测试完成。
- 非法 Planner 输出可稳定降级或报错。
- 每个中间结果可追溯。
- 数据库设计完成评审后才允许进入 Phase C。

### 测试命令

```powershell
pytest tests/test_sales_collaboration_schemas.py -q
pytest tests/test_sales_collaboration_models.py -q
pytest
```

记录结果：

```text
8 passed in 0.04s
5 passed in 0.33s
85 passed in 2.02s
```

### 当前状态

`In Progress`

Phase B-B1、B-B2 和 B-B3 已完成；错误码契约和进入 Phase C 前的整体数据契约评审尚未完成。

### 遗留问题

- 协作错误码尚未定义。
- run/step 状态已在数据库层约束，但应用层状态枚举尚未统一导出。
- migration 尚未连接真实 PostgreSQL 执行；本阶段仅完成声明检查和 SQLite 模型测试。
- 进入 Phase C 前仍需完成协作数据契约整体评审。

### 相关 Commit Hash

`TBD`

## 6. Phase C：最小串行多智能体 MVP

### 目标

完成第一个可追踪、可验证的串行多 Agent 协作闭环。

### 范围

- Intake、Planner、R&D、Quality、Reviewer、Writer、Final Verifier。
- 协作步骤持久化。
- 独立售前方案 API。
- 最多一次定向修复。

### 允许修改

- Phase B 已验收的数据契约。
- 新增独立协作 graph、Agent、服务、API、模型和测试。
- 新增经评审的数据库 migration。

### 禁止修改

- 不替换现有 `/api/ask/stream` 路由。
- 不破坏现有 FMEA、Audit、Report 独立入口。
- 不默认并行执行。
- 不接入 Memory V2。

### 计划任务

- [x] 新增串行协作 graph 骨架。
- [x] 实现真实 Planner、规则 Reviewer 和 Final Verifier。
- [x] 接入 R&D、Quality Specialist 结构化包装层。
- [x] 实现受证据约束的结构化 Proposal Writer。
- [x] 持久化 run 和 step。
- [x] 新增独立生成与查询 API。
- [x] 编写节点、图、API 和失败状态持久化测试。

### 已完成事项

- Phase C-C1 新增 `graphs/sales_collaboration_graph.py`，固定串行执行 Intake、Planner、R&D、Quality、Reviewer、Writer、Final Verifier 和 Persist Run。
- 所有业务节点均使用确定性 mock 输出，并通过 Phase B Pydantic schema 构造 Planner、Specialist 和 Reviewer 结果。
- graph 扩展状态已记录各步骤的 `pending`、`completed`、`failed` 和 `skipped` 状态，后续可映射到 `CollaborationStep`。
- `persist_collaboration_run(state)` 已作为持久化扩展点预留；C-C1 不写真实数据库。
- 新增合法请求完整流转、Phase B Specialist 输出结构和空请求失败测试。
- C-C1 未调用 LLM、RAG、Milvus、Embedding、FMEA、Audit 或 Report 工作流。
- Phase C-C2 新增销售协作 R&D Specialist，复用 `xf_fmea_kb` 和现有 `retrieve_structured`，通过协作专用结构化 LLM 输出 `SpecialistOutput`。
- Phase C-C2 新增销售协作 Quality Specialist，复用 `xf_quality_kb` 和现有 `retrieve_structured`，通过协作专用结构化 LLM 输出 `SpecialistOutput`。
- 两个包装层均接收 `user_request`、`customer_context`、完整 `execution_plan` 和当前 task，并限制各自专业边界。
- 检索 chunk 已映射为 Phase B `Citation`；模型引用会按真实 chunk allowlist 清洗，不能保留虚构引用。
- 无检索结果时清空引用、禁止 `high` 置信度，并保证至少存在一个信息缺口。
- graph 默认调用真实 Specialist 包装层，同时支持测试注入 deterministic Specialist。
- Specialist 单元测试使用 fake retriever 和 fake structured LLM，不连接 Milvus、Embedding 或外部 LLM。
- Phase C-C3 新增 `POST /sales/proposals/generate`，先保存 `running` run，再执行销售协作 graph。
- Phase C-C3 新增 `GET /sales/proposals/{run_id}` 和 `GET /sales/proposals/{run_id}/steps`，并按当前登录用户校验数据归属。
- 新增 collaboration repository，将 graph 的 `collaboration_steps` 或 mock `steps` 映射为 `CollaborationStep`，按 graph 顺序保存输入、输出、状态、错误和可选指标。
- graph 完成后更新 `CollaborationRun` 的执行计划、报告、审核结果、引用、错误和指标；graph 异常时保留 `failed` run。
- API 失败响应使用稳定错误码和消息，不返回 Python traceback 或内部异常文本。
- API 测试使用内存 SQLite 和 mock graph，不调用外部 LLM、Milvus 或 Embedding。
- C-C3 回归确认现有 FMEA、Audit、Report API snapshot 未发生变化。
- Phase C-C4 新增结构化 Planner：默认调用 LLM 生成 `PlannerOutput`，非法 Agent、缺少核心角色或模型异常时回退到固定 R&D/Quality/Reviewer/Writer 计划。
- Planner 通过 Pydantic allowlist 限制 Agent；FMEA/Audit 仅形成 warning 和 `optional_artifacts` 占位，不会被 graph 自动执行。
- Phase C-C4 新增规则优先 Reviewer，检查 Specialist 缺失、角色越权、无引用强结论、人工确认项和 Writer 所需章节；可选 LLM 审核默认关闭。
- Phase C-C4 新增结构化 Proposal Writer：LLM 只能选择已有 claim/risk/recommendation ID，最终 Markdown 从原始 Specialist/Reviewer 内容确定性渲染。
- Proposal Writer 固定输出六个章节，保留 Reviewer conflicts、unsupported claims、manual checks、missing sections 和 repair instructions。
- Final Verifier 增加六个固定章节校验；Writer 引用只来自 Specialist citations，并按 `citation_id` 去重。
- graph/API 测试继续使用依赖注入和 mock graph，不调用真实 LLM、RAG、Milvus 或 Embedding。
- Phase C-C5 新增 5 个最小 smoke/eval case，覆盖综合问题、纯技术、纯质量、信息不足和诱导过度承诺。
- 新增真实 API + graph 编排 + SQLite 持久化的最小 E2E 测试，验证 POST、run 查询、steps 查询、六章节报告、审核结果和引用。
- 新增节点失败验收：run 保存为 `failed`，已完成步骤和失败步骤均保留，后续步骤标记为 `skipped`。
- Reviewer 增加绝对质量承诺检查；Writer 将零缺陷等诉求改写为待质量、合同和授权审批人确认，不直接作结果保证。
- 新增 `SALES_COLLABORATION_BASELINE.md`，记录 5 个可重复 mock baseline 和尚待真实 live baseline 补充的指标。
- C5 回归确认既有 FMEA、Audit、Report API snapshot 和主聊天测试均未受影响。

### 验收标准

- 一个请求由 R&D、Quality、Reviewer、Writer 实际参与。
- 引用可追溯到知识源。
- Reviewer 能识别无依据声明。
- 单步失败不丢失已完成步骤。
- 修复循环最多一次。

### 测试命令

```powershell
pytest tests/test_sales_collaboration_e2e.py
pytest tests/test_sales_collaboration_api.py
pytest tests/test_sales_collaboration_graph.py
pytest tests/test_sales_planner.py
pytest tests/test_sales_reviewer.py
pytest tests/test_sales_proposal_writer.py
pytest tests/test_sales_specialists.py
pytest
```

记录结果：

```text
8 passed, 1 warning in 1.26s
6 passed, 1 warning in 1.16s
3 passed in 0.40s
5 passed in 0.12s
6 passed in 0.13s
6 passed in 0.13s
4 passed in 0.12s
123 passed, 1 warning in 2.62s
```

### 当前状态

`Completed`

Phase C-C1 至 C-C5 的最小串行多智能体 MVP 已完成并通过自动化验收。Phase D、E、F 尚未开始。

### 遗留问题

- Planner 和 Proposal Writer 已具备真实结构化 LLM 路径，但尚未执行外部模型集成测试。
- Reviewer 当前默认只执行确定性规则；可选 LLM 审核接口已预留但默认关闭。
- R&D、Quality Specialist 已具备真实调用路径，但尚未执行外部 LLM、Milvus 和 Embedding 的集成测试。
- graph 内的 `persist_run` 仍是轻量节点，真实数据库提交由 API/repository 在 graph 返回后统一执行。
- graph 进程在返回最终 state 前发生未捕获异常时，只能保存 failed run，无法恢复尚未返回的内存步骤。
- 当前没有销售协作前端页面，不支持并发执行，也不会自动调用 FMEA、Audit 或 Report。
- 当前只有 5 个 smoke cases，不是 Phase E 的完整质量评估集。
- 单步恢复、幂等请求、实际定向修复执行和真实调用指标尚未实现。

### 相关 Commit Hash

`TBD`

## 7. Phase D：协作前端与任务生命周期

### 目标

让用户能够查看、恢复和管理协作任务。

### 范围

- 售前方案页面。
- 执行计划、Agent 状态、最终报告、引用和人工确认项。
- 按 `run_id` 恢复任务。
- 后端任务状态作为事实来源。

### 允许修改

- 协作前端页面、路由、API client 和类型。
- 协作任务查询与恢复 API。
- 任务生命周期相关测试。

### 禁止修改

- 不以 React 本地状态替代后端状态。
- 不重构无关前端页面。
- 不改变现有四个入口的响应契约。
- 不提前实现并行或 Memory V2。

### 计划任务

- [ ] 新增售前方案页面。
- [ ] 展示执行计划和步骤状态。
- [ ] 展示结果、引用和人工确认项。
- [ ] 支持刷新和页面切换后的恢复。
- [ ] 统一各业务工作流运行状态展示。

### 已完成事项

- 暂无。

### 验收标准

- 页面刷新后可恢复任务。
- 状态阶段清晰可辨。
- 已持久化结果不因前端中断丢失。

### 测试命令

```powershell
npm --prefix web test
```

前端测试命令和测试框架需在阶段开始时确认。

### 当前状态

`Not Started`

### 遗留问题

- 前端自动化测试框架尚未确认。
- 任务状态 API 依赖 Phase C。

### 相关 Commit Hash

`TBD`

## 8. Phase E：多智能体质量评估

### 目标

用可重复评估证明协作图相对单 Agent 的实际收益。

### 范围

- 至少 20 个售前评估案例。
- 单 R&D、单 Quality、现有 Supervisor、新协作图四组比较。
- 质量、引用、延迟、调用次数和成本指标。

### 允许修改

- eval cases、评估脚本、结果记录和只读指标采集。
- 不改变业务输出的评估辅助代码。

### 禁止修改

- 不为通过评估而硬编码案例答案。
- 质量无提升前不进入并行化和 Memory 深度集成。
- 不把 live eval 混入默认单元测试。

### 计划任务

- [ ] 建立至少 20 个评估案例。
- [ ] 实现四组对比运行。
- [ ] 记录覆盖率、依据质量、引用准确率和人工确认项。
- [ ] 记录延迟、调用次数和估算成本。
- [ ] 形成阶段评估报告。

### 已完成事项

- 暂无。

### 验收标准

- 综合问题明显优于单 Agent。
- 简单问题不默认进入高成本协作图。
- 评估结果可复现并保留原始记录。

### 测试命令

```powershell
python eval_cases/sales_collaboration/run_eval.py
```

脚本尚未创建。

### 当前状态

`Not Started`

### 遗留问题

- 评估数据集和评分标准尚未建立。
- live eval 模型、预算和执行环境尚未确定。

### 相关 Commit Hash

`TBD`

## 9. Phase F：Planner 路由与按需专业工作流

### 目标

让 Planner 根据请求复杂度选择现有问答、协作图或专业业务工作流。

### 范围

- 任务复杂度判断。
- Supervisor 与 Collaboration Graph 分流。
- FMEA、Audit、Proposal Writer 按需调用。
- Agent allowlist、最大步骤和调用预算。

### 允许修改

- Planner 路由规则、注册表、预算配置和测试。
- 经 Phase E 验证后的路由集成点。

### 禁止修改

- 不为普通问答滥用 FMEA/Audit。
- 不允许 Planner 调用未注册 Agent 或工具。
- 不允许无上限步骤或模型调用。
- 不把 `session_id` 当作质量案例 ID。

### 计划任务

- [ ] 定义复杂度和工作流选择规则。
- [ ] 集成 Supervisor 与协作图分流。
- [ ] 集成 FMEA/Audit 显式调用条件。
- [ ] 增加 allowlist、最大步骤和预算。
- [ ] 增加原因追踪和路由回归测试。

### 已完成事项

- 暂无。

### 验收标准

- 普通问答不滥用专业工作流。
- 调用原因可解释、可追踪。
- 最大调用次数和 token 预算可配置。

### 测试命令

```powershell
pytest tests/test_planner_routing.py tests/test_workflow_selection.py -q
```

测试文件尚未创建。

### 当前状态

`Not Started`

### 遗留问题

- 依赖 Phase E 的质量结论。
- 路由阈值和预算默认值尚未确定。

### 相关 Commit Hash

`TBD`

## 10. Phase G：并行化与可靠性

### 目标

在语义保持一致的前提下降低协作延迟并增强失败恢复能力。

### 范围

- R&D、Quality fan-out/fan-in。
- join、超时、重试、部分结果和取消。
- 幂等 request key。
- 模型调用与节点级 tracing。

### 允许修改

- 已稳定协作图的执行策略。
- 可靠性、幂等、取消和 tracing 基础设施。
- 并行一致性与故障注入测试。

### 禁止修改

- Phase E 未证明收益前不并行化。
- 不允许重复保存 run 或重复计费调用。
- 不用并行执行改变结构化交接语义。
- 不引入无限重试。

### 计划任务

- [ ] 实现 R&D、Quality 并行执行。
- [ ] 增加 join 和部分结果策略。
- [ ] 增加超时、有限重试和取消。
- [ ] 增加幂等 request key。
- [ ] 增加节点级 tracing。

### 已完成事项

- 暂无。

### 验收标准

- 并行与串行结果语义一致。
- 总延迟下降。
- 单分支失败后状态可恢复。
- 不重复保存或计费。

### 测试命令

```powershell
pytest tests/test_collaboration_parallelism.py tests/test_collaboration_reliability.py -q
```

测试文件尚未创建。

### 当前状态

`Not Started`

### 遗留问题

- 依赖 Phase E 和 Phase F。
- 超时、重试和部分结果策略尚未定义。

### 相关 Commit Hash

`TBD`

## 11. Phase H：Memory V2 实现

### 目标

在协作契约稳定后实现隔离、可控、可关闭的长期记忆能力。

### 范围

- 用户画像、长期摘要、业务产物向量记忆。
- 按任务类型检索和注入。
- 删除、过期、禁用和冲突处理。
- 相似 FMEA 案例按需接入。

### 允许修改

- 独立 Memory V2 模型、服务、索引和测试。
- 经评审后的数据库 migration 和 Milvus namespace。
- Agent 按最小必要原则接入记忆。

### 禁止修改

- 不破坏 Memory V1 现有行为。
- 不向所有 Agent 注入全部用户历史。
- 不让 Milvus 成为事实主存储。
- 不混用文档 RAG、对话记忆和业务产物 collection。

### 计划任务

- [ ] 实现用户画像记忆。
- [ ] 实现长期摘要记忆。
- [ ] 实现业务产物向量记忆。
- [ ] 实现任务级检索与注入。
- [ ] 实现生命周期与冲突处理。
- [ ] 按需接入相似 FMEA 案例。

### 已完成事项

- Memory V2 总体架构已有独立设计文档。
- 本阶段尚无代码实现。

### 验收标准

- 严格按 `user_id` 隔离。
- PostgreSQL 保存事实和状态。
- Milvus 仅保存语义索引。
- 当前输入优先于旧记忆。
- 关闭记忆后系统仍可运行。

### 测试命令

```powershell
pytest tests/test_memory_v2.py tests/test_memory_isolation.py -q
```

测试文件尚未创建。

### 当前状态

`Not Started`

### 遗留问题

- 依赖稳定的协作任务和 Agent 边界。
- 数据保留、删除和冲突策略尚未落地。

### 相关 Commit Hash

`TBD`

## 12. Phase I：业务产物自动关联与案例系统

### 目标

在数据质量稳定后减少用户手动选择业务产物的成本。

### 范围

- metadata filter 与 embedding 相似度混合匹配。
- 明确的 `quality_case_id` 或项目上下文实体。
- FMEA、Audit、Report、Collaboration Run 案例关联。
- 候选推荐与人工确认。

### 允许修改

- 案例模型、关联服务、候选匹配和人工确认接口。
- 经评审后的数据库 migration 和索引。
- 关联准确率评估。

### 禁止修改

- 不使用 `session_id` 冒充案例 ID。
- 不让自动匹配静默进入正式报告。
- 不移除人工覆盖入口。
- 数据质量未稳定前不自动建立正式关联。

### 计划任务

- [ ] 定义质量案例实体。
- [ ] 建立业务产物关联模型。
- [ ] 实现混合候选匹配。
- [ ] 增加分数、依据和人工覆盖。
- [ ] 建立错误关联回归测试。

### 已完成事项

- 暂无。

### 验收标准

- 使用明确案例 ID。
- 自动匹配具有分数和依据。
- 用户可确认或覆盖候选。
- 错误关联不会静默进入正式报告。

### 测试命令

```powershell
pytest tests/test_quality_case_linking.py tests/test_artifact_candidate_matcher.py -q
```

测试文件尚未创建。

### 当前状态

`Not Started`

### 遗留问题

- 依赖前序业务产物和 Memory 数据质量。
- 案例实体边界和匹配阈值尚未确定。

### 相关 Commit Hash

`TBD`

## 13. Phase J：生产化与后续优化

### 目标

补齐可观测性、安全性、可靠性和运维能力，使系统具备生产运行条件。

### 范围

- tracing、token、延迟、错误率和成本指标。
- Prompt 与模型版本记录。
- 权限、审计日志和敏感数据策略。
- 限流、超时、重试、熔断、备份和迁移演练。
- 端到端浏览器测试和后续 SFT 评估。

### 允许修改

- 可观测性、安全、运维和测试基础设施。
- 必要配置、部署文件和数据迁移流程。
- 经评估后的模型优化方案。

### 禁止修改

- 不在缺少评估数据时进行 SFT。
- 不记录未脱敏的敏感 Prompt 或用户数据。
- 不以 tracing 失败阻断核心业务。
- 不省略备份和迁移演练直接上线。

### 计划任务

- [ ] 接入 tracing 和节点级指标。
- [ ] 记录 Prompt 与模型版本。
- [ ] 完善权限、审计和敏感数据策略。
- [ ] 实现限流、超时、重试和熔断。
- [ ] 完成备份与迁移演练。
- [ ] 增加端到端浏览器测试。
- [ ] 基于评估结果决定是否进行 SFT。

### 已完成事项

- 暂无。

### 验收标准

- 核心请求可追踪。
- 成本、延迟和错误率可观测。
- 安全与审计要求完成评审。
- 备份和迁移可演练恢复。
- 关键浏览器流程有端到端测试。

### 测试命令

```powershell
pytest tests -q
```

端到端浏览器测试命令需在阶段开始时补充。

### 当前状态

`Not Started`

### 遗留问题

- 生产 SLO、日志保留和告警阈值尚未定义。
- SFT 是否必要需等待真实评估数据。

### 相关 Commit Hash

`TBD`

## 14. 专项整改：表格摘要命中后的关联行块二次排序

### 背景

当前大表格采用 `table_parent + table_summary + table_row_block` 的多粒度入库方式：

- `table_parent` 保存完整表格，只用于回溯，不参与向量检索。
- `table_summary` 保存列名、样例行和高频关键词，用于宽泛召回。
- `table_row_block` 保存表头和分组数据行，用于提供具体表格内容。

在线检索命中 `table_summary` 后，系统会根据共同的 `table_id` 查询关联的
`table_row_block`，并固定补充最多 3 个行块。

当前实现只通过 `table_id` 建立关联，没有使用原始 Query 对关联行块进行二次相关性排序。
因此，被补充的 3 个行块不一定是与用户问题最相关的数据行，可能出现摘要召回正确、
但具体行块选择不准确的问题。

### 目标

在保持表格宽泛召回能力的同时，提高关联行块的选择准确性，减少无关表格行进入模型上下文，
并控制大表格展开后的 Token 消耗。

### 计划方案

- [ ] 当 `table_summary` 被向量检索召回时，读取其 `table_id`。
- [ ] 查询该 `table_id` 下全部或受控数量的 `table_row_block` 候选。
- [ ] 使用原始用户 Query 对候选行块执行表内二次相关性计算。
- [ ] 优先复用当前 Query Embedding，避免重复调用 Embedding API。
- [ ] 按相似度选取表内 Top-K 行块，默认仍限制为 3 个。
- [ ] 对相似度接近的候选使用 `row_range` 或稳定 ID 作为确定性排序兜底。
- [ ] 保留 `table_id`、`parent_chunk_uid` 和 `row_range`，确保引用与完整表格回溯能力不受影响。
- [ ] 候选行块为空或二次排序失败时，降级到稳定的行号顺序，而不是让整个 RAG 请求失败。
- [ ] 将表内候选数量、最终 Top-K 和最低相关性阈值改为可配置参数。

### 建议实现位置

- `tools/rag.py`
  - 调整 `_expand_table_chunks`，使其接收原始 Query 或 Query Embedding。
  - 增加关联行块候选查询、二次打分、Top-K 选择和降级逻辑。
- `config.py`
  - 增加表内候选数量、表内 Top-K 和可选最低相似度配置。
- `tests/`
  - 增加表格摘要展开与表内排序单元测试。
  - 使用 Fake Embedding 和 Fake Milvus Client，默认测试不得依赖外部服务。

### 评测指标

- 表格行块 `Recall@K`：标准答案所在行块是否进入最终展开结果。
- 表格行块 `MRR`：标准答案所在行块在展开结果中的排序位置。
- 无关行块比例：最终送入模型的行块中与问题无关的比例。
- 上下文增量：摘要展开前后增加的字符数或 Token 数。
- 检索延迟：二次排序引入的额外耗时。

### 验收标准

- [ ] 命中 `table_summary` 后，最终行块由原始 Query 相关性决定，不再依赖无明确顺序的固定 `limit=3`。
- [ ] 相同 Query 和相同知识库版本下，行块排序结果稳定。
- [ ] 二次排序失败时能够降级，并保留可用检索结果。
- [ ] 不改变普通文本、小表格和未命中 `table_summary` 时的现有检索行为。
- [ ] 引用中的 `table_id`、`row_range`、`chunk_uid` 和 `parent_chunk_uid` 保持正确。
- [ ] 新增自动化测试覆盖摘要命中、多个关联行块、Top-K、去重和失败降级场景。
- [ ] 在表格专项 QA 集上，表格行块 `Recall@3` 不低于当前实现，且无关行块比例下降。

### 阶段归属

该整改属于 RAG 检索质量专项，可在 Phase E 质量评测期间建立基线并实施。
在缺少表格专项评测集前，不以主观样例替代指标结论；整改结果应纳入 Phase E 的质量、
延迟和成本对比报告。

### 当前状态

`Not Started`

## 15. 更新记录

| 日期 | Phase | 更新内容 | 更新人 | Commit |
| --- | --- | --- | --- | --- |
| 2026-06-08 | A | 建立阶段执行记录；登记 Phase A 最小回归测试结果 | Codex | `TBD` |
| 2026-06-08 | B | 完成 B-B1 schema/state 与 B-B2 run/step 持久化模型、migration 和测试 | Codex | `TBD` |
| 2026-06-08 | B | 完成 B-B3 Schema、State、DB Model 关系文档和 tracker 同步 | Codex | `TBD` |
| 2026-06-09 | C | 完成 C-C1 串行 mock graph、步骤状态流转、持久化扩展点和单元测试 | Codex | `TBD` |
| 2026-06-09 | C | 完成 C-C2 R&D/Quality Specialist 包装层、引用映射、无检索降级和 mock 单元测试 | Codex | `TBD` |
| 2026-06-09 | C | 完成 C-C3 销售协作生成/查询 API、run/step 持久化、权限隔离和失败保存测试 | Codex | `TBD` |
| 2026-06-09 | C | 完成 C-C4 结构化 Planner、规则 Reviewer、证据约束 Proposal Writer 和六章节校验 | Codex | `TBD` |
| 2026-06-09 | C | 完成 C-C5 五类 smoke case、最小 E2E、失败场景验收和 baseline 文档；Phase C 标记 Completed | Codex | `TBD` |

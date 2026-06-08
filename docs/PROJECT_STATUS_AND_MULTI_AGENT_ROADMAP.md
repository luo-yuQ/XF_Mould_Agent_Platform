# XF Mould Agent Platform：项目现状与完整演进路线

## 1. 文档目的

本文档统一回答三个问题：

1. 当前项目已经实现了什么。
2. 当前项目是否属于多智能体，以及距离协作型多智能体还缺什么。
3. 后续应按什么顺序实施，才能减少架构返工。

本文档作为后续开发的主路线基准。已有 `MVP_ROADMAP.md`、
`TECH_DEBT_AND_NEXT_STEPS.md` 和各业务 MVP 文档继续保留，用于记录阶段背景和局部约束；
若阶段编号或优先级与本文档冲突，以本文档的新阶段划分为准。

---

## 2. 当前产品定位

当前系统是面向模具行业的 AI 售前与质量业务平台，主要知识来源为：

- FMEA 手册：支持模具技术风险、FMEA 方法和相关研发问题。
- XF 模具 VDA 6.4 质量手册：支持质量体系、审核、流程和认证问题。
- 用户输入及已生成业务产物：支持 FMEA、审核检查和报告生成。

系统目前同时包含两种产品形态：

- 对话式知识问答。
- 独立的结构化质量业务工作流。

这两种形态已经共存，但尚未被统一为一个“围绕客户售前任务协作”的多智能体流程。

---

## 3. 当前已实现能力

### 3.1 基础平台

- FastAPI 后端。
- React 19 + TypeScript + Vite 前端。
- PostgreSQL 业务数据持久化。
- Milvus 文档向量检索。
- Redis 配置与会话相关基础设施。
- JWT + HttpOnly Cookie 登录认证。
- Docker Compose 部署。
- Alembic 数据库迁移。
- UTC 持久化与中国时区展示约定。

### 3.2 主聊天问答

主聊天图采用 LangGraph：

```text
START
  -> Supervisor
      -> R&D RAG -> R&D Writer -> END
      -> Quality RAG -> Quality Writer -> END
      -> Chat Agent -> END
```

已实现：

- Supervisor 对问题进行意图分类。
- 用户可手动指定 R&D 或 Quality Agent。
- R&D Agent 检索 FMEA 相关知识。
- Quality Agent 检索 VDA 6.4 相关知识。
- Chat Agent 处理闲聊和天气工具调用。
- 回答支持结构化引用。
- SSE 流式输出。
- 会话创建、重命名、删除和历史消息分页。

当前性质：

> 这是 Supervisor 路由型 Multi-Agent。一次请求通常只选择一个专业 Agent 执行，
> 不属于多个 Agent 共同完成同一任务的协作型 Multi-Agent。

### 3.3 Memory V1

当前已实现短期会话记忆：

- 最近 20 条消息滑动窗口。
- 超过阈值后的滚动摘要。
- 摘要覆盖位置记录。
- 孤儿用户消息清理。
- API 构造状态时注入摘要和未覆盖消息。

当前未实现：

- 跨会话长期语义记忆。
- 用户画像记忆。
- 业务产物向量记忆。
- 统一记忆检索路由和按 Agent 注入。

### 3.4 FMEA 生成工作流

独立 LangGraph 流程：

```text
输入检查
  -> 检索规划
  -> RAG 检索
  -> FMEA 结构化生成
  -> Verifier
      -> 通过 -> Markdown Writer
      -> 失败 -> 最多修复一次 -> 再验证
  -> 保存 FMEA Run
```

已实现：

- 产品、过程、失效现象和背景输入。
- 检索问题规划。
- FMEA 结构化 rows 生成。
- 结构校验与最多一次修复。
- Markdown 输出。
- FMEA run 持久化。
- 标题、摘要、关键词、引用等统一业务产物元数据。
- 初始版本 V1 创建。
- 历史产物列表和版本列表。
- 基于历史版本继续追改。
- 版本详情恢复。
- 追改校验和版本差异摘要。

说明：

- PFMEA 是过程失效模式与影响分析，是 FMEA 生成能力的一种业务产物。
- 当前 FMEA 工作流不接主 Supervisor。
- 当前 FMEA 工作流不自动调用 Audit Agent。

### 3.5 Audit 审核检查工作流

独立 LangGraph 流程：

```text
输入检查
  -> 检索规划
  -> RAG 检索
  -> 生成结构化 Findings
  -> Verifier
      -> 通过 -> Markdown Writer
      -> 失败 -> 最多修复一次 -> 再验证
  -> 保存 Audit Run
```

已实现：

- 支持质量问题、PFMEA 内容、审核记录和通用文本。
- 支持审核重点和背景输入。
- 结构化 findings。
- 校验与最多一次修复。
- Markdown 输出和引用。
- Audit run 及统一元数据持久化。

说明：

- Audit Agent 可以检查用户主动提交的 PFMEA 内容。
- 当前它不会自动接收 FMEA Agent 的结果。
- 当前尚无 Audit 业务产物追改和版本历史。

### 3.6 Report 报告生成工作流

独立 LangGraph 流程：

```text
输入检查
  -> 加载用户明确选择的 FMEA/Audit 来源
  -> 来源匹配检查
  -> 可选 RAG
  -> 上下文构建
  -> Report Writer
  -> Verifier
      -> 通过 -> 保存
      -> 失败 -> 最多修复一次 -> 再验证
  -> 最终响应
```

已实现：

- 用户手动选择 FMEA run 和 Audit run。
- 展示来源标题、摘要、关键词和更新时间。
- 来源匹配规则检查。
- 不匹配或缺少来源时给出人工确认提示。
- 报告生成、校验、最多一次修复和持久化。
- 保存来源快照、匹配结果、引用和统一元数据。

当前未实现：

- 自动发现最合适的 FMEA/Audit 来源。
- Report 业务产物追改和版本历史。
- 多 Agent 执行过程的自动汇总。

### 3.7 业务产物与版本

当前业务产物包括：

- `fmea_runs`
- `audit_runs`
- `report_runs`

统一元数据已覆盖：

- `title`
- `summary`
- `keywords_json`
- `artifact_type`
- `references_json`
- `created_at`
- `updated_at`

FMEA 额外支持：

- `business_artifact_versions`
- `version_no`
- `parent_version_id`
- `operation_type`
- `revision_instruction`
- `output_json`
- `final_markdown`
- `diff_summary_json`
- `verify_result_json`

### 3.8 前端

已实现四个入口：

- 质量问答。
- FMEA 生成。
- 审核检查。
- 报告生成。

还存在的主要缺口：

- 各业务页面的任务状态主要保存在组件本地。
- FMEA/Audit/Report 执行期间切换页面或会话，任务恢复能力不统一。
- 没有统一的“售前方案协作任务”页面。
- 没有展示多 Agent 执行计划、步骤状态和中间结果。

### 3.9 测试与评估

当前已有：

- 业务产物元数据测试。
- API 契约测试。
- FMEA 追改和版本测试。
- Report 来源匹配测试。
- PDF 分块测试。
- 时区契约测试。
- FMEA、Audit、Report 端到端评估案例。

当前缺少：

- 主聊天 Supervisor 路由回归测试。
- 多 Agent 协作图测试。
- Planner 任务拆分评估。
- 多 Agent 综合结果质量评估。
- 端到端前端工作流测试。
- 并发任务和任务恢复测试。

---

## 4. 当前架构判断

### 4.1 已经具备的 Multi-Agent 特征

- 存在 Supervisor。
- 存在多个角色不同的 Agent。
- Supervisor 能根据意图选择专业 Agent。
- 各 Agent 有独立提示词、知识范围和节点实现。

### 4.2 尚未具备的协作能力

- 同一请求没有稳定的任务拆分。
- 多个专业 Agent 通常不会共同参与同一任务。
- Agent 间没有统一结构化交接协议。
- 没有综合任务的 Coordinator/Planner。
- 没有跨 Agent 的冲突检查和证据审查。
- Report Agent 当前汇总的是用户手动选择的历史产物，不是本次协作任务的自动结果。

因此，当前准确定位是：

> 多 Agent 路由平台 + 多个独立业务工作流，而不是完整的协作型多智能体售前系统。

---

## 5. 目标业务场景

第一版协作型多智能体只解决一个明确场景：

> 根据客户的综合售前需求，同时形成技术分析、质量保障分析和有依据的统一售前方案。

示例输入：

> 我们计划开发一套汽车覆盖件冲压模具，请说明主要技术风险、质量保障方式、
> 相关依据和建议的后续确认事项。

目标输出应包含：

- 客户需求理解。
- 技术与工艺风险。
- 质量体系和过程保障。
- 引用依据。
- 信息缺口。
- 不确定项和人工确认项。
- 统一售前建议。

不应在第一版自动执行：

- 正式 PFMEA 表格生成。
- 客户文件审核。
- 自动修改已有 FMEA。
- 自动生成合同承诺。

这些能力后续由 Planner 按需调用，而不是固定进入每次协作。

---

## 6. 目标多智能体架构

### 6.1 第一版拓扑

先采用可验证的串行执行，不急于并发：

```text
START
  -> Request Intake
  -> Planner Agent
  -> R&D Specialist
  -> Quality Specialist
  -> Reviewer Agent
  -> Proposal Writer
  -> Final Verifier
  -> Persist Run
  -> END
```

角色职责：

| 角色 | 职责 | 禁止事项 |
| --- | --- | --- |
| Intake | 校验综合售前输入 | 不生成业务结论 |
| Planner | 拆分技术、质量、证据任务 | 不直接回答客户 |
| R&D Specialist | 基于 FMEA 知识分析技术和过程风险 | 不声称公司质量能力 |
| Quality Specialist | 基于 XF VDA 资料分析质量保障 | 不编造技术方案 |
| Reviewer | 检查冲突、遗漏、证据和过度承诺 | 不新增无依据事实 |
| Proposal Writer | 汇总成统一客户方案 | 不覆盖 Reviewer 风险提示 |
| Final Verifier | 校验结构、引用和人工确认项 | 不包装成业务 Agent |

### 6.2 为什么第一版不并发

- 先验证共享状态和交接契约是否正确。
- 便于观察每个 Agent 的输入与输出。
- 便于复现失败和编写测试。
- 降低 SSE、任务状态和异常处理复杂度。

当串行版本稳定后，R&D 与 Quality 才改为并行 fan-out/fan-in：

```text
Planner
  -> R&D Specialist ----\
                         -> Join -> Reviewer
  -> Quality Specialist-/
```

并发是性能优化，不是协作型多智能体成立的前提。

### 6.3 FMEA Agent 和 Audit Agent 的位置

二者是按需专业工作流：

```text
Planner
  -> 普通技术风险分析：R&D Specialist
  -> 需要正式 PFMEA：FMEA Workflow
  -> 普通质量保障分析：Quality Specialist
  -> 需要检查客户文件/PFMEA：Audit Workflow
```

第一版综合售前方案不自动调用 FMEA/Audit。

后续调用规则：

- 用户明确要求“生成 PFMEA 表格”时调用 FMEA Workflow。
- 用户提供待检查文件或文本时调用 Audit Workflow。
- Planner 只能根据明确输入调用，不得凭空创建审核对象。
- FMEA 输出若要进入 Audit，必须通过显式结构化适配层，并在任务计划中可见。

---

## 7. 协作状态和数据契约

建议新增独立状态，不继续扩张当前 `AgentState`：

```python
class SalesCollaborationState(TypedDict):
    request_id: str
    user_id: int
    session_id: str | None
    user_request: str
    customer_context: dict
    execution_plan: list[dict]
    rd_analysis: dict
    quality_analysis: dict
    optional_artifacts: list[dict]
    review_result: dict
    final_report: str
    citations: list[dict]
    status: str
    error: str | None
```

Planner 任务格式：

```json
{
  "task_id": "quality_analysis",
  "agent": "quality",
  "objective": "分析项目质量保障与VDA流程",
  "required_sources": ["xf_vda_manual"],
  "depends_on": [],
  "required": true
}
```

专业 Agent 输出必须包含：

```json
{
  "summary": "...",
  "claims": [],
  "risks": [],
  "recommendations": [],
  "missing_information": [],
  "citations": [],
  "confidence": "high|medium|low"
}
```

Reviewer 输出必须包含：

```json
{
  "passed": true,
  "conflicts": [],
  "unsupported_claims": [],
  "missing_sections": [],
  "manual_check_items": [],
  "repair_instructions": []
}
```

关键约束：

- Agent 间传递结构化 JSON，不以 Markdown 作为内部主协议。
- 每条关键结论保留来源。
- 公司能力结论必须来自 XF 资料。
- FMEA 历史案例不能伪装成标准依据。
- Reviewer 最多触发一次定向修复，避免无限循环。

---

## 8. 完整实施路线

以下使用阶段名称，不继续复用旧文档中已经冲突的 `5.1/5.2` 编号。

### Phase A：基线冻结与回归保护

目标：

- 在多智能体改造前固定当前行为。

实施：

- 为 Supervisor 的 `rd/quality/chat` 路由补测试。
- 为 R&D、Quality 引用结构补契约测试。
- 建立当前 FMEA/Audit/Report API 快照测试。
- 记录现有端到端延迟和模型调用次数。
- 修订 README，使其反映 FMEA、Audit、Report 和版本追改现状。

验收：

- 当前测试全部通过。
- 多智能体开发不得破坏现有四个入口。
- 有可比较的质量、延迟和成本基线。

### Phase B：协作数据契约

目标：

- 先确定 Agent 如何交接，再写图。

实施：

- 新增 `SalesCollaborationState`。
- 新增 Planner、专业分析、Reviewer 的 Pydantic schema。
- 明确 citation、claim、risk、missing information 格式。
- 定义稳定错误码和任务状态。
- 定义协作 run 的持久化模型设计。

建议新增表：

- `collaboration_runs`
- `collaboration_steps`

核心字段：

- run 状态。
- 用户、会话和原始请求。
- execution plan。
- 每一步输入快照、输出 JSON、状态、错误和耗时。
- final report、review result、引用和模型信息。

验收：

- Schema 单元测试完成。
- 非法 Planner 输出可稳定降级或报错。
- 每个中间结果可追溯。

### Phase C：最小串行多智能体 MVP

目标：

- 完成第一个真实协作闭环。

实施：

- 新增 `sales_collaboration_graph.py`。
- 新增 Planner Agent。
- 为现有 R&D/Quality 能力增加结构化 specialist 包装层。
- 新增 Reviewer Agent。
- 复用或拆分 Report Writer，生成售前方案。
- 增加 Final Verifier。
- 每步状态持久化。
- 新增独立 API，例如：

```text
POST /sales/proposals/generate
GET  /sales/proposals/{run_id}
```

第一版不修改 `/api/ask/stream` 的现有路由。

验收：

- 一个请求至少由 R&D、Quality、Reviewer、Writer 实际参与。
- 最终结果引用可追溯到对应知识源。
- Reviewer 能识别无依据公司能力声明。
- 任一步失败时返回稳定状态，不丢失已完成步骤。
- 修复循环最多一次。

### Phase D：协作前端与任务生命周期

目标：

- 让用户看得见、找得回协作任务。

实施：

- 新增“售前方案”页面。
- 展示执行计划和各 Agent 状态。
- 展示最终报告、引用和人工确认项。
- 后端任务状态作为事实来源，不依赖 React 组件本地状态。
- 页面切换后可按 `run_id` 恢复。
- 统一 FMEA/Audit/Report/Collaboration 的运行中状态设计。

验收：

- 页面切换或刷新后仍可恢复任务。
- 用户能区分计划中、执行中、失败、完成。
- 已持久化成功的结果不会因前端请求中断而丢失。

### Phase E：多智能体质量评估

目标：

- 证明多 Agent 比单 Agent 有实际收益。

建立至少 20 个售前评估案例，覆盖：

- 纯技术问题。
- 纯质量问题。
- 技术 + 质量综合问题。
- 信息不足问题。
- 诱导过度承诺问题。
- 引用冲突问题。
- 不需要协作的简单问题。

比较组：

- 单 R&D Agent。
- 单 Quality Agent。
- 现有 Supervisor 路由。
- 新协作图。

指标：

- 需求覆盖率。
- 有依据结论比例。
- 无依据声明数量。
- 引用准确率。
- 人工确认项召回率。
- 总延迟。
- 模型调用次数和估算成本。

验收：

- 综合问题的覆盖率和依据质量明显优于单 Agent。
- 简单问题不会默认进入高成本协作图。
- 若质量没有提升，不进入并发和 Memory 深度集成。

### Phase F：Planner 路由与按需专业工作流

目标：

- 让 Planner 根据任务选择 Agent 组合。

实施：

- 增加任务复杂度判断。
- 简单问题继续走现有 Supervisor。
- 综合售前请求进入 Collaboration Graph。
- 明确请求正式 PFMEA 时调用 FMEA Workflow。
- 明确提交审核材料时调用 Audit Workflow。
- 需要统一报告时由 Proposal Writer 汇总。
- 增加 Agent allowlist 和最大步骤数。

验收：

- Planner 不会为普通问答滥用 FMEA/Audit。
- FMEA/Audit 调用原因可解释、可追踪。
- 可配置最大模型调用次数和 token 预算。

### Phase G：并行化与可靠性

前置条件：

- Phase E 已证明协作有效。
- 结构化交接协议稳定。

实施：

- R&D 与 Quality fan-out 并行。
- 增加 join 节点。
- 增加单分支超时、重试和部分结果策略。
- 增加幂等 request key。
- 增加任务取消。
- 增加模型调用和节点级 tracing。

验收：

- 并行结果与串行结果语义一致。
- 总延迟下降。
- 单分支失败不会导致状态不可恢复。
- 不重复保存 run 或重复计费调用。

### Phase H：Memory V2 实现

Memory V2 总体架构文档已经完成，代码实现应在协作契约稳定后开始。

实施顺序：

1. 用户画像结构化记忆。
2. 长期对话摘要记忆。
3. 业务产物向量记忆。
4. 按任务类型进行记忆检索和 Prompt 注入。
5. 删除、过期、禁用和冲突处理。
6. 相似 FMEA 案例按需接入 FMEA Workflow。

多智能体中的注入原则：

- Planner 只获取任务规划必要的项目背景。
- R&D 只获取技术相关记忆。
- Quality 只获取质量相关记忆。
- Reviewer 获取各 Agent 结果及必要证据，不默认获取全部用户历史。
- Writer 获取已审查的结果，不直接用低置信度记忆补事实。

验收：

- 用户隔离严格依赖 `user_id`。
- PostgreSQL 是记忆事实和状态主存储。
- Milvus 只承担语义索引。
- 文档 RAG、对话记忆和业务产物记忆使用不同 collection/namespace。
- 当前输入优先于旧记忆。
- 记忆关闭后系统仍可正常运行。

### Phase I：业务产物自动关联与案例系统

目标：

- 在数据质量稳定后，减少用户手动选择产物。

实施：

- metadata filter + embedding 相似度混合匹配。
- 建立明确的 `quality_case_id` 或项目上下文实体。
- 将 FMEA、Audit、Report、Collaboration Run 关联到同一案例。
- 自动匹配只提供候选，关键关联仍允许人工确认。

验收：

- 不再使用 `session_id` 冒充业务案例 ID。
- 自动匹配有分数、依据和人工覆盖入口。
- 错误关联不会静默进入正式报告。

### Phase J：生产化与后续优化

实施：

- OpenTelemetry 或等价 tracing。
- 节点级 token、延迟、错误率和成本指标。
- Prompt 与模型版本记录。
- 权限、审计日志和敏感数据策略。
- 限流、超时、重试和熔断。
- 数据备份与迁移演练。
- 端到端浏览器测试。
- 在工作流和数据稳定后再评估 SFT。

---

## 9. 推荐执行顺序

```text
Phase A  基线与回归
  -> Phase B  协作数据契约
  -> Phase C  串行多智能体 MVP
  -> Phase D  前端任务生命周期
  -> Phase E  质量评估
  -> Phase F  Planner 按需调用 FMEA/Audit
  -> Phase G  并行化
  -> Phase H  Memory V2 实现
  -> Phase I  自动关联与质量案例
  -> Phase J  生产化/SFT评估
```

优先级结论：

> 先完成最小协作型多智能体，再实现完整 Memory V2。

原因：

- Memory V1 已能满足当前会话连续性。
- Memory V2 的检索对象和注入位置依赖稳定的协作任务与 Agent 边界。
- 先确定 Planner、Specialist、Reviewer 的数据契约，可减少后续记忆注入返工。
- 多 Agent 是否真的提升售前质量，必须先通过评估证明。

---

## 10. 明确不做的事情

在前置阶段未验收前，不做：

- 为了展示“多 Agent”让所有 Agent 每次都参加。
- 一开始就做 Agent 自由讨论或无限循环。
- 一开始就并发所有节点。
- 把 Markdown 当作 Agent 间唯一交接格式。
- 把历史 FMEA 当作标准依据。
- 把 `session_id` 当作质量案例 ID。
- 让 Planner 调用任意未注册 Agent 或工具。
- 在协作契约未稳定前把全部记忆注入所有 Agent。
- 在缺少评估数据时进行 SFT。

---

## 11. 下一开发迭代建议

下一迭代只执行 Phase A 和 Phase B，不直接进入完整实现：

1. 更新 README 的项目现状。
2. 补 Supervisor 和现有 API 回归测试。
3. 定义 `SalesCollaborationState`。
4. 定义 Planner、Specialist、Reviewer schema。
5. 设计 `collaboration_runs` 和 `collaboration_steps`。
6. 准备 10 个首批综合售前测试案例。

完成后再进入 Phase C 的 LangGraph 和 API 实现。


# 销售协作数据契约关系说明

## 1. 文档目的

本文说明 Phase B 中三类数据结构的职责和关系：

- Pydantic Schema：校验 Planner、专家 Agent、Reviewer 的单次结构化输出。
- `SalesCollaborationState`：在未来协作流程执行期间传递当前状态。
- SQLAlchemy Model：将一次协作任务及每个执行步骤持久化到数据库。

本阶段只定义数据契约和持久化结构，不实现 LangGraph、Planner 逻辑、API 或 LLM 调用。

## 2. 三层职责

| 层 | 对应代码 | 主要用途 | 是否运行时校验 | 是否写数据库 |
| --- | --- | --- | --- | --- |
| Schema | [`schemas/sales_collaboration.py`](../schemas/sales_collaboration.py) | 约束 Agent 输入输出字段和允许值 | 是，Pydantic 校验 | 否 |
| State | [`state.py`](../state.py) | 保存一次流程执行中的共享数据 | 否，主要提供类型提示 | 否 |
| DB Model | [`models/collaboration.py`](../models/collaboration.py) | 保存任务、步骤、结果、错误和指标 | 是，数据库约束 | 是 |

三者不是重复定义：

```text
Agent / LLM 原始输出
        ↓
Pydantic Schema 校验
        ↓ model_dump()
SalesCollaborationState 流程内传递
        ↓ 持久化服务（Phase C 实现）
CollaborationRun / CollaborationStep
```

## 3. Schema 的用途

### 3.1 公共内容结构

| Schema | 用途 |
| --- | --- |
| `Citation` | 记录结论、风险或建议所依据的来源 |
| `Claim` | 记录带置信度和引用依据的结论 |
| `RiskItem` | 记录风险、影响和缓解措施 |
| `Recommendation` | 记录建议、理由和引用依据 |
| `MissingInformation` | 记录完成任务前仍缺少的信息 |

### 3.2 Agent 输出结构

| Schema | 产生者 | 主要去向 |
| --- | --- | --- |
| `PlannerTask` | Planner | 组成执行计划中的单个任务 |
| `PlannerOutput` | Planner | 任务列表写入 State；完整输出保存在 Planner Step |
| `SpecialistOutput` | R&D、Quality 等专家 Agent | 写入对应分析 State；完整输出保存在 Specialist Step |
| `ReviewerOutput` | Reviewer | 写入审核 State 和 Run 审核结果；完整输出保存在 Reviewer Step |

Schema 校验通过后使用：

```python
validated = SpecialistOutput.model_validate(raw_output)
data = validated.model_dump()
```

此时 `data` 是经过校验的普通 `dict`，可以放入 State 或 JSON 数据库字段。

## 4. State 的用途

`SalesCollaborationState` 是未来协作流程执行时的工作区。它保存当前请求、执行计划、中间分析、审核结果和最终报告。

主要字段来源：

| State 字段 | 数据来源 |
| --- | --- |
| `request_id` | 创建协作任务时生成 |
| `user_id`、`session_id` | 当前用户和会话上下文 |
| `user_request`、`customer_context` | 用户请求和客户资料 |
| `execution_plan` | `PlannerOutput.tasks` 转换后的字典列表 |
| `rd_analysis` | R&D 的 `SpecialistOutput.model_dump()` |
| `quality_analysis` | Quality 的 `SpecialistOutput.model_dump()` |
| `review_result` | `ReviewerOutput.model_dump()` |
| `citations` | 各步骤引用汇总后的 `Citation` 字典列表 |
| `final_report` | Writer 生成的最终文本 |
| `status`、`error` | 流程当前状态和错误 |

State 只负责流程内传递，不替代 Schema 校验，也不保证进程退出后数据仍然存在。

## 5. DB Model 的用途

### 5.1 CollaborationRun

`CollaborationRun` 表示一次完整协作任务，保存任务级数据：

- 用户请求和客户上下文
- 当前执行计划和运行状态
- 最终报告和审核结果
- 汇总引用、错误、模型信息和指标
- 创建及更新时间

### 5.2 CollaborationStep

`CollaborationStep` 表示 Run 中的一次具体执行步骤，例如 Planner、R&D、Quality、Reviewer 或 Writer：

- 步骤 ID、名称、Agent 和状态
- 步骤输入及输出 JSON
- 错误、开始时间、结束时间和耗时
- 模型信息和指标

一个 `CollaborationRun` 可以关联多个 `CollaborationStep`。同一个 Run 内 `(run_id, step_id)` 唯一。

## 6. State 与数据库字段映射

以下映射是 Phase C 持久化服务需要遵守的实现约定，当前尚未编写自动转换或保存服务。

| State 字段 | Run 字段 | Step 字段或说明 |
| --- | --- | --- |
| `request_id` | `run_id` | 两者表示同一个业务运行标识 |
| `user_id` | `user_id` | 无 |
| `session_id` | `session_id` | 无 |
| `user_request` | `user_request` | 可同时放入 Planner Step 的 `input_json` |
| `customer_context` | `customer_context_json` | 可按步骤裁剪后放入 `input_json` |
| `execution_plan` | `execution_plan_json` | Planner 完整输出放入 `output_json` |
| `rd_analysis` | 无独立列 | R&D Step 的 `output_json` |
| `quality_analysis` | 无独立列 | Quality Step 的 `output_json` |
| `optional_artifacts` | 无独立列 | 由相应步骤输出保存，后续按需求扩展 |
| `review_result` | `review_result_json` | Reviewer Step 的 `output_json` |
| `final_report` | `final_report` | Writer Step 的 `output_json` 可保留生成详情 |
| `citations` | `citations_json` | 各 Specialist/Writer Step 也可保存局部引用 |
| `status` | `status` | Run 状态 |
| `error` | `error` | 步骤错误同时保存在对应 Step 的 `error` |

数据库不为每个专家结果设置独立列。步骤级完整结果存入 `CollaborationStep.output_json`，Run 表只保存查询和恢复流程所需的任务级汇总。

## 7. 典型数据流转

```text
1. 创建 CollaborationRun(status="pending")

2. PlannerOutput 校验通过
   -> Planner Step.output_json 保存完整 PlannerOutput
   -> State.execution_plan 保存 tasks
   -> Run.execution_plan_json 保存 tasks

3. R&D / Quality SpecialistOutput 分别校验通过
   -> 各自 Step.output_json 保存完整 SpecialistOutput
   -> State.rd_analysis / quality_analysis 保存对应结果

4. ReviewerOutput 校验通过
   -> Reviewer Step.output_json 保存完整 ReviewerOutput
   -> State.review_result 更新
   -> Run.review_result_json 更新

5. Writer 完成报告
   -> Writer Step.output_json 保存步骤输出
   -> State.final_report 更新
   -> Run.final_report 更新

6. 汇总 Citation
   -> State.citations 更新
   -> Run.citations_json 更新

7. Run.status 更新为 completed 或 failed
```

## 8. 状态约束

Run 数据库状态：

```text
pending, running, completed, failed, cancelled
```

Step 数据库状态：

```text
pending, running, completed, failed, skipped
```

当前 `SalesCollaborationState.status` 仍是普通 `str`。应用层统一状态类型和错误码将在后续 Phase B 工作中定义。

## 9. 当前边界

已完成：

- Schema、State、Run/Step Model 和 migration 定义。
- Schema 校验测试。
- SQLite 建表、CRUD、JSON、关系和唯一约束测试。

尚未实现：

- Schema 到 State、State 到 DB Model 的转换服务。
- Run/Step 的实际创建、更新和失败恢复逻辑。
- LangGraph、Planner Agent、API 和真实 LLM 调用。
- 应用层统一状态枚举和错误码。

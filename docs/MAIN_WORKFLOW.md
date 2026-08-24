# Main Workflow

## 1. 为什么需要统一主干流程

当前系统已经存在多个业务入口：

- 普通问答入口
- PFMEA / FMEA 生成入口
- Audit 审核入口
- Report 报告入口
- Sales Collaboration / 售前方案入口

这些入口各自独立，已经能够支撑不同业务场景，但如果后续继续直接堆功能，系统会逐步变得难以维护：

- Router 逻辑越来越乱。
- Graph 之间边界不清。
- Tool 和 Agent 概念混淆。
- 开发中途临时走分支，后续忘记主干目标。
- 任务状态、失败恢复、步骤记录不统一。
- FMEA、Audit、Report、Proposal 后续难以统一调度。

因此，本阶段需要先定义一个主干框架。这个文档不实现新功能，只约定后续改造的方向、边界和禁止事项，避免后续开发在 Router、Graph、Tool、Agent、Skill 之间反复返工。

## 2. 当前主干目标

后续目标主干流程定义为：

```text
用户输入
  -> Router 判断应该走哪个工作流
  -> Workflow Registry 找到对应 Graph
  -> Run Manager 记录任务状态
  -> 执行 G1 / G2 / G3
  -> 保存结果、步骤状态和失败原因
```

注意：这是后续目标说明，不要求在本阶段实现。

当前项目实际状态是：

- 主问答 Graph 已存在，由 Supervisor 分流到 R&D、Quality 或 Chat。
- PFMEA / FMEA Graph 已存在，是独立结构化业务工作流。
- Audit Graph 已存在，是独立审核检查工作流。
- Report Graph 已存在，是独立报告生成工作流。
- Sales Collaboration Graph 已存在，是固定串行的售前方案协作工作流。
- Sales Collaboration 已有 `collaboration_runs` 和 `collaboration_steps`，但全系统尚未统一 Run / Step。
- 还没有统一 Router 输出契约、Workflow Registry、统一 Run Manager 或统一入口。

## 3. G1 / G2 / G3 的边界

### G1：问答 Graph

职责：

- 普通问答。
- FMEA / VDA 知识问答。
- 简单解释类问题。
- 普通闲聊。

特点：

- 一次请求通常只进入一个专业分支。
- 主要依赖 RAG + Writer。
- 不负责生成正式 PFMEA 表。
- 不负责生成完整售前方案。

当前对应关系：

- 当前 `graph.py` 中的主问答 Graph 可视为 G1 的现有基础。
- 当前流程为 `START -> Supervisor -> R&D RAG/Writer 或 Quality RAG/Writer 或 Chat -> END`。

### G2：PFMEA Graph

职责：

- 用户明确要求生成 PFMEA。
- 生成失效模式、失效原因、S/O/D、AP、RPN、建议措施等结构化内容。
- 使用 RAG、Verifier、Repair、Markdown Renderer。

特点：

- 是结构化业务工作流。
- 不是普通问答。
- 后续可以考虑接 Audit，但当前不自动串联。

当前对应关系：

- 当前 `fmea_graph.py` 可视为 G2 的现有基础。
- 当前流程包含输入检查、检索规划、RAG 检索、FMEA 结构化生成、校验、最多一次修复、Markdown 输出和 FMEA Run 保存。

### G3：售前方案 Graph

职责：

- 用户要求生成售前方案、技术方案、客户沟通方案。
- 综合研发和质量两个视角。
- 使用 Planner、R&D Specialist、Quality Specialist、Reviewer、Proposal Writer。

特点：

- 是协作型多智能体工作流。
- 多个 Agent 共同生成一份方案。
- 不等同于 G1 的单轮问答。
- 后续可以按需调用 PFMEA、Audit、Report，但当前先不自动调用。

当前对应关系：

- 当前 `graphs/sales_collaboration_graph.py` 可视为 G3 的现有基础。
- 当前流程为固定串行：Request Intake、Planner、R&D Specialist、Quality Specialist、Reviewer、Proposal Writer、Final Verifier、Persist Run。
- 当前 Graph 会记录步骤状态，但不会自动执行 FMEA、Audit 或 Report 工作流。

## 4. Tools 的定义

Tool 不是只能指外部 API。

在本项目里，Tool 应定义为：

> 一个具有明确输入、明确输出、可被 Graph 节点或 Agent 调用的能力单元。

它可以是：

- 外部 API。
- 内部 Python 函数。
- RAG 检索器。
- 被封装后的 Agent。
- 被封装后的 LangGraph 子流程。

需要特别区分：

- Skill 本身不是 Tool。
- Skill 是规则、模板、Prompt 片段。
- 只有当某个函数、Agent 或 Graph 加载 Skill 并执行时，才形成可调用能力。

结合当前项目示例：

- RAG Tool：输入 query，输出 chunks 和 citations。
- Audit Tool：输入 PFMEA 或质量材料，输出 findings 和整改建议。
- Report Tool：输入 FMEA / Audit / 背景材料，输出结构化报告。

因此，后续如果把 Audit 或 Report 封装成可被 G3 调用的能力，应把它们作为可调用 Tool 或 Workflow Tool 暴露，而不是直接把所有逻辑塞进 G3 Agent 的 Prompt。

## 5. Router / Graph / Tool 的关系

需要明确区分：

- Router：负责判断走哪条主流程。
- Graph：负责执行一条完整业务流程。
- Tool：Graph 内部可调用的能力模块。
- Agent：可以是 Graph 中的一个节点，也可以被封装成 Tool。
- Skill：规则和提示词资产，不直接执行。

建议约定：

```text
Router 不直接干活。
Router 只决定 workflow_type。
Graph 负责组织步骤。
Tool 负责提供具体能力。
Agent 负责在某个步骤中进行判断、生成或整合。
Skill 负责给 Agent 提供业务规则。
```

后续统一主干中，Router 不应直接调用 RAG、FMEA、Audit、Report 或 Proposal Writer。Router 的输出应被 Workflow Registry 消费，再由对应 Graph 负责执行。

## 6. 本阶段允许做什么

后续第一阶段允许做：

- 梳理主干流程。
- 定义 G1 / G2 / G3 边界。
- 明确 Router / Graph / Tool / Agent / Skill 概念。
- 梳理现有入口如何映射到未来主干。
- 记录后续需要实现的事项。

本阶段的产物应以文档为主，不改变运行时行为。

## 7. 本阶段禁止做什么

当前阶段不要做：

- 不改代码。
- 不改 Router。
- 不定义新 Schema。
- 不改数据库。
- 不改 API。
- 不改前端。
- 不做 Memory V2。
- 不做 RAG reranker。
- 不做 PDF OCR。
- 不做并行化。
- 不做 FMEA -> Audit -> Report 自动串联。
- 不把所有功能塞进一个超级 Agent。
- 不重写现有工作流内部逻辑。

这些事项可以进入后续规划或 `docs/PARKING_LOT.md`，但不能在本阶段实现。

## 8. 现有入口到未来主干的映射

建议的未来映射如下：

| 现有入口 | 当前职责 | 未来 workflow_type | 目标 Graph |
| --- | --- | --- | --- |
| 普通问答入口 | 问答、知识解释、闲聊 | `qa` | G1 |
| PFMEA / FMEA 生成入口 | 结构化 PFMEA / FMEA 生成 | `pfmea` | G2 |
| Audit 审核入口 | 质量材料、PFMEA、审核记录检查 | 后续单独定义 | 现有 Audit Graph |
| Report 报告入口 | 基于 FMEA / Audit / 背景材料生成报告 | 后续单独定义 | 现有 Report Graph |
| Sales Collaboration / 售前方案入口 | 多 Agent 协作生成售前方案 | `proposal` | G3 |

本阶段只先定义 G1 / G2 / G3 主干。Audit 和 Report 已经是独立工作流，后续可以作为独立 workflow_type，也可以被封装为 G3 可按需调用的 Tool，但当前不自动串联。

## 9. 后续实施阶段建议

### Stage 1：文档冻结

产物：

- `docs/MAIN_WORKFLOW.md`
- `docs/PARKING_LOT.md`

目标：

- 冻结主干流程术语。
- 冻结 G1 / G2 / G3 边界。
- 记录本阶段不做事项。

### Stage 2：Router 输出契约

后续再定义：

- `workflow_type`
- `reason`
- `confidence`
- `needs_clarification`

注意：本阶段不定义新的 Pydantic Schema。

### Stage 3：Workflow Registry

后续再实现：

- `qa` -> G1
- `pfmea` -> G2
- `proposal` -> G3

Registry 只负责根据 `workflow_type` 找到对应 Graph，不负责执行业务逻辑。

### Stage 4：统一 Run / Step

后续再考虑：

- `run_id`
- `workflow_type`
- `status`
- router step
- graph step
- failed / completed 状态

当前 Sales Collaboration 已有 `collaboration_runs` 和 `collaboration_steps`，但不应直接把它们硬扩展成全局统一模型。需要先评估 FMEA、Audit、Report 现有 Run 的兼容方式。

### Stage 5：最小统一入口

后续再考虑新增统一入口，但不能破坏现有 API。

建议原则：

- 现有 `/api/ask/stream`、FMEA、Audit、Report、Sales Proposal 入口先保持兼容。
- 新统一入口应作为增量能力出现。
- 在旧入口稳定前，不强制迁移前端。

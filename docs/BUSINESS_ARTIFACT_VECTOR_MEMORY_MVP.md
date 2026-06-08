# 5.0 Memory V2 记忆层总体架构

## 1. 背景

当前 Memory V1 已经完成，其实现基于 `chat_session_summaries` 的滚动摘要记忆。Memory V1 解决的是“当前会话上下文压缩”问题，职责包括：

- 保存当前会话的滚动 summary。
- 保留最近若干条原始消息。
- 减少模型输入上下文长度。
- 不做长期语义检索。
- 不做用户画像。
- 不做业务产物案例检索。
- 不写入 Milvus。

项目同时已经完成 FMEA 生成 Agent MVP、4.5 业务产物元数据统一，以及 4.6 FMEA 业务产物追改与版本记录。FMEA 产物现在具备 `artifact_id`，版本具备 `version_id`、`version_no`、`output_json`、`final_markdown`、`references_json`，并支持历史版本恢复和持续修改。Audit / Report 追改暂不继续。

Memory V2 的目标不是简单地把业务产物向量化，而是设计完整记忆层，包括：

- 短期会话记忆。
- 长期对话记忆。
- 用户画像记忆。
- 业务产物记忆。
- 记忆检索与注入策略。
- 记忆更新、删除、过期和冲突处理。

因此，5.0 只完成总体架构和边界规划，不直接实现业务产物向量化，也不修改 Python、前端、数据库 migration、API、Milvus、Memory、RAG 或 LangGraph 代码。

## 2. Memory V1 与 Memory V2 的区别

### Memory V1

- 面向单个 `chat_session`。
- 使用滚动摘要压缩旧消息。
- 最近消息仍保留原文。
- 主要服务当前会话连续性。
- 不做跨会话召回。
- 不做用户画像。
- 不做向量检索。
- 不进入 Milvus。

### Memory V2

- 面向跨会话、跨业务工作流的长期记忆。
- 支持对话历史沉淀。
- 支持用户画像。
- 支持业务产物案例沉淀。
- 支持语义检索。
- 支持按任务类型选择性注入 prompt。
- 支持记忆管理和失效机制。

Memory V2 不能推翻或重写 Memory V1。Memory V1 继续负责当前会话的短期上下文压缩，Memory V2 在其上扩展长期记忆能力。

## 3. 记忆分层设计

### L0：系统指令与 Agent Skill

内容：

- `CLAUDE.md` / `AGENTS.md`。
- `skills/`。
- Agent 固定提示词。
- 业务规则。
- 开发约束。

特点：

- 只读。
- 不由用户对话动态生成。
- 不进入记忆向量库。
- 优先级高于所有动态记忆。

### L1：短期会话记忆

内容：

- `chat_session_summary`。
- 最近 N 条 `chat_messages`。
- 当前会话上下文。

用途：

- 保证当前会话不断裂。
- 控制模型上下文长度。

当前 Memory V1 已覆盖这一层。Memory V2 不修改这一层的现有实现。

### L2：长期对话记忆

内容：

- 跨会话的重要项目决策。
- 用户反复讨论的问题。
- 功能路线选择。
- bug 修复过程及结论。
- 架构取舍。
- 已完成阶段。
- 暂缓事项。

示例：

- 用户决定 4.6 只做 FMEA 追改，Audit / Report 追改暂缓。
- 用户希望 FMEA、审核、报告暂时保持独立入口，不合并到质量问答。
- 用户担心合并入口会引入复杂意图识别。
- 用户当前准备从 4.6 进入 Memory V2 规划。

不建议向量化每条原始消息。应先将消息提炼为有独立语义、可追溯、可更新的摘要记忆块，再按需写入语义检索存储。

建议的长期对话记忆类型：

- `project_decision`
- `architecture_choice`
- `implementation_status`
- `bug_fix`
- `unresolved_question`
- `deferred_task`
- `preference_reference`

### L3：用户画像记忆

内容：

- 用户技术栈。
- 项目背景。
- 长期偏好。
- 工作方式偏好。
- 学习状态。
- 输出风格偏好。

示例：

- 用户使用 FastAPI、LangGraph、PostgreSQL、Milvus、Docker。
- 用户偏好小步推进，每次明确允许修改和禁止修改的文件。
- 用户希望使用中文回答。
- 用户希望技术解释结合当前 Agent 项目。
- 用户不希望模型一味赞同，需要中立判断。

用户画像优先采用结构化存储，不一定需要向量化。画像不得保存无关、短期或敏感信息，除非用户明确要求；同时必须支持更新、合并、禁用和冲突处理。

### L4：业务产物记忆

内容：

- FMEA 生成产物。
- FMEA 版本记录。
- 审核检查产物。
- 报告生成产物。
- 后续质量案例。

当前 MVP 可以优先支持 FMEA artifact version，后续再接入 Audit 和 Report。

用途：

- 检索相似 FMEA 案例。
- 后续生成 FMEA 时提供历史案例参考。
- 审核检查时参考历史问题。
- 报告生成时参考历史产物。

业务产物记忆不是标准依据，只能作为历史案例参考。不得把历史 FMEA 当成 FMEA 手册或 VDA 6.4 条款。

### L5：外部知识库 RAG

内容：

- FMEA 手册。
- VDA 6.4。
- 质量标准文件。
- 用户上传的知识文档。

用途：

- 回答“标准怎么说”。
- 为 FMEA、审核和报告提供规范依据。

外部知识库 RAG 与业务产物记忆必须分开。业务产物向量化不得复用或污染原有知识库 collection。

## 4. 三类核心长期记忆

### 4.1 长期对话记忆

目标是把重要对话沉淀为可检索记忆，而不是保存所有聊天碎片。

数据来源：

- `chat_messages`
- `chat_session_summaries`
- 用户明确做出的决策
- assistant 给出的阶段建议
- 项目阶段切换记录

建议 `memory_type`：

- `project_decision`
- `architecture_choice`
- `implementation_status`
- `bug_fix`
- `unresolved_question`
- `deferred_task`
- `preference_reference`

存储建议：

- PostgreSQL 保存结构化内容、来源和状态。
- 重要摘要块可选写入独立 Milvus collection。
- 不直接向量化每条 message。
- 优先向量化去噪、去重后的摘要记忆块。

### 4.2 用户画像记忆

目标是保存对后续回答长期有用的用户偏好和项目背景。

建议字段：

- `id`
- `user_id`
- `memory_type`
- `key`
- `value`
- `confidence`
- `source`
- `created_at`
- `updated_at`
- `last_used_at`
- `is_active`

建议 `memory_type`：

- `preference`
- `project_context`
- `tech_stack`
- `workflow_style`
- `learning_state`

约束：

- 不保存无关闲聊。
- 不保存短期状态。
- 不保存敏感信息，除非用户明确要求。
- 支持同 key 更新、同义项合并和冲突处理。
- 推断得到的画像必须低于用户当前明确指令。

### 4.3 业务产物记忆

目标是把 FMEA、Audit、Report 等业务结果沉淀为可检索案例。

数据来源：

- `business_artifacts`
- `business_artifact_versions`
- `output_json`
- `final_markdown`
- `references_json`
- `diff_summary_json`

MVP 边界：

- 只实际支持 FMEA artifact version。
- Audit / Report 只预留类型。
- 不做规则与向量混合匹配。
- 不做 `quality_case_id`。
- 不自动接入 FMEA 生成主流程。

## 5. 哪些进入 Milvus，哪些只进入 PostgreSQL

### 只进入 PostgreSQL

- 用户画像结构化记忆。
- Memory V1 会话 summary。
- 记忆元数据。
- 记忆启用/禁用状态。
- 记忆冲突记录。
- 记忆来源记录。
- 删除、过期和合并状态。

### 可以进入 Milvus

- 长期对话记忆摘要块。
- 业务产物 memory chunks。
- 后续质量案例 chunks。

必须使用独立 collection：

- `conversation_memory`
- `business_artifact_memory`

禁止复用或污染原有文档 RAG collection。PostgreSQL 是记忆事实、状态和可追溯信息的主存储；Milvus 只承担需要语义召回的向量索引职责。

## 6. 推荐数据库表设计

以下是初版逻辑设计，本阶段不实现 migration 或模型代码。

### `user_profile_memories`

建议字段：

- `id`
- `user_id`
- `memory_type`
- `key`
- `value`
- `confidence`
- `source_type`
- `source_id`
- `is_active`
- `created_at`
- `updated_at`
- `last_used_at`

建议对 `(user_id, memory_type, key, is_active)` 建立查询索引。是否允许同 key 多条有效记录，应在 5.1 根据冲突与合并策略确定。

### `conversation_memories`

建议字段：

- `id`
- `user_id`
- `session_id`
- `memory_type`
- `title`
- `content`
- `source_message_start_id`
- `source_message_end_id`
- `vector_id`
- `metadata_json`
- `importance_score`
- `is_active`
- `created_at`
- `updated_at`
- `indexed_at`

需要保留消息来源范围，保证长期摘要可追溯，避免无法判断记忆从何而来。

### `business_artifact_memory_index`

建议字段：

- `id`
- `user_id`
- `session_id`
- `artifact_id`
- `version_id`
- `artifact_type`
- `version_no`
- `chunk_id`
- `chunk_type`
- `memory_text`
- `vector_id`
- `metadata_json`
- `embedding_model`
- `embedding_dim`
- `is_latest_version`
- `is_active`
- `created_at`
- `indexed_at`

同一 `version_id` 和 `chunk_id` 不应重复索引。新版本产生后，应将旧版本标记为非 latest，但可继续保留以支持追溯。

## 7. 记忆写入策略

### 对话记忆写入

不建议每条消息都写入长期记忆。建议在以下时机生成 memory candidate：

- 会话达到一定长度。
- 用户明确做出项目决策。
- 某个功能阶段完成。
- 用户明确说“记住”。
- 用户切换任务阶段。
- assistant 生成阶段性总结。

建议流程：

```text
chat_messages
→ summary / memory extractor
→ 生成结构化 memory candidate
→ 有效性、敏感性和重要性判断
→ 去重、合并与冲突检查
→ 写 PostgreSQL
→ 重要内容可写 Milvus
```

写入记录必须保留来源消息、会话和提取时间。自动提取的推断应记录置信度，不得伪装成用户明确陈述。

### 用户画像写入

写入来源：

- 用户明确偏好。
- 长期稳定的项目背景。
- 多次重复出现的工作方式。
- 用户明确要求记住的信息。

写入前需要：

- 判断是否长期有效。
- 判断是否敏感。
- 判断是否已经存在。
- 判断是新增、合并还是更新旧值。
- 区分用户明确表达和模型推断。

用户当前明确指令与旧画像冲突时，不应先修改当前回答来迎合旧画像；应优先执行当前指令，并按需更新画像。

### 业务产物记忆写入

可考虑的写入时机：

- FMEA V1 创建成功。
- FMEA V2 / V3 追改成功。
- 用户确认产物有效。
- 后续 Audit / Report 产物生成成功。

MVP 可先手动触发索引，不要求自动写入。业务产物索引必须保留 `artifact_id`、`version_id`、`version_no`、`user_id` 和来源字段。

## 8. 记忆检索策略

不同任务只检索与当前目标相关的记忆层，不应默认查询全部记忆。

### 普通知识问答

可用：

- L1 短期会话记忆。
- L2 长期对话记忆。
- L3 用户画像。
- L5 文档 RAG。

默认不用：

- L4 业务产物记忆，除非用户询问历史案例或当前问题明确需要历史业务结果。

### FMEA 生成

可用：

- L1 当前会话。
- L3 与任务相关的用户画像或项目背景。
- L4 相似 FMEA 案例。
- L5 FMEA 手册 / VDA 6.4。

L4 是历史案例参考，L5 是规范依据。两者必须在检索结果、状态和 prompt 中使用不同标签。

### 审核检查

可用：

- L1 当前会话。
- L3 与任务相关的用户画像或项目背景。
- L4 历史审核 / FMEA 案例。
- L5 标准文档。

### 报告生成

可用：

- L1 当前会话。
- L2 项目阶段记忆。
- L3 与任务相关的用户画像或项目背景。
- L4 用户明确选择或检索到的业务产物。
- L5 标准文档。

报告已有的显式来源选择仍应优先，不能用记忆检索替代来源契约。

## 9. 记忆注入策略

检索到的内容不能全部塞入 prompt。应按任务相关性、来源可信度、优先级和 token 预算选择性注入。

建议优先级：

1. 系统指令 / Skill。
2. 用户当前明确输入。
3. 用户画像中与当前任务相关的少量内容。
4. 当前会话 summary。
5. 最近消息。
6. 长期对话记忆中的高相关内容。
7. 业务产物相似案例。
8. 外部知识库 RAG。

这里的编号表示组装顺序和管理层级，不表示历史案例可以覆盖规范依据。涉及事实或规范判断时，外部知识库依据的可信角色高于业务案例。

注入要求：

- 每类记忆标明来源类型和来源 ID。
- 业务产物记忆不得伪装成标准依据。
- 用户画像不能覆盖用户当前明确指令。
- 长期记忆与当前输入冲突时，以当前输入为准。
- 对低置信度、已过期或存在冲突的记忆不自动注入。
- 每类记忆设置独立数量和 token 上限。

## 10. 记忆更新、删除、过期、冲突处理

### 更新

- 同一 key 的用户画像可以更新。
- 新记忆可以合并旧记忆，避免语义重复。
- 业务产物新版本生成后，应标记旧版本为非 latest。
- 更新必须保留来源和时间，不应无痕覆盖关键事实。

### 删除

- 用户要求忘记时，必须删除或禁用对应记忆。
- 删除业务产物时，应同步禁用相关 memory index。
- 初期建议使用 `is_active=false` 软删除，便于一致性处理和审计。
- Milvus 中的向量必须与 PostgreSQL 中的失效状态同步，不得继续被召回。

### 过期

- 短期项目状态可以过期。
- 长期偏好不应轻易过期，但可以被新值替换。
- 技术栈可能变化，需要结合 `last_used_at` 和 `updated_at` 判断。
- 过期策略应按 `memory_type` 配置，不能使用一个固定时间处理所有记忆。

### 冲突

- 当前输入优先级最高。
- 最近且明确的记忆优先于旧记忆。
- 用户明确指令优先于推断画像。
- 冲突可以标记为 `memory_conflict`，等待合并、失效或人工确认。
- 冲突未解决时，不应把两个相反结论同时作为确定事实注入。

## 11. 与 4.6 的关系

4.6 已解决：

- `artifact_id`
- `version_id`
- `version_no`
- `parent_version_id`
- `output_json`
- `final_markdown`
- `references_json`
- 持续追改和版本历史

Memory V2 使用 4.6 的业务产物数据作为 L4 业务产物记忆来源。

边界如下：

- 4.6 不依赖 Memory V2。
- Memory V2 不得破坏 4.6 的生成、追改、恢复和版本查询。
- 业务产物向量化是 4.6 之后的增强能力。
- 5.0 只定义架构，不把向量化逻辑提前塞入 4.6。

## 12. 与后续 5.x 的关系

重新规划路线：

| 阶段 | 内容 |
| --- | --- |
| 5.0 | Memory V2 总体架构设计 |
| 5.1 | 用户画像结构化记忆 MVP |
| 5.2 | 长期对话摘要记忆 MVP |
| 5.3 | 业务产物向量化记忆 MVP |
| 5.4 | 记忆检索路由与 Prompt 注入 |
| 5.5 | 记忆管理、删除、过期、冲突处理 |
| 5.6 | 业务产物相似案例接入 FMEA 生成 |
| 5.7 | 规则与向量混合匹配 |
| 5.8 | `quality_case_id` 质量案例系统 |
| 最后 | SFT |

各阶段应独立验收。不得因为 4.6 已具备业务产物版本数据，就跳过用户画像、长期对话记忆粒度和统一注入策略的设计。

## 13. MVP 建议

下一步不应直接做业务产物向量化，建议顺序为：

### Phase 1：Memory V2 文档与约束

- 完成本架构文档。
- 明确 Memory V1 不被修改。
- 明确各记忆层、存储和来源边界。

### Phase 2：用户画像结构化记忆

- 优先使用 PostgreSQL。
- 先支持明确偏好和稳定项目背景。
- 建立更新、禁用和冲突处理的最小契约。

### Phase 3：长期对话记忆摘要块

- 确定摘要粒度和写入时机。
- 建立 memory candidate、去重、合并和来源追溯。
- 在没有必要时不急于接入 Milvus。

### Phase 4：业务产物向量化

- 基于 4.6 的 FMEA artifact version。
- 独立设计 `business_artifact_memory` collection。
- 先提供手动索引和独立检索能力。

### Phase 5：统一记忆检索与注入

- 按任务类型选择记忆层。
- 设置每层检索和 token 预算。
- 区分用户画像、历史案例和规范依据。

采用该顺序的原因：

- 用户画像不依赖 Milvus，容易先落地和验证。
- 长期对话记忆需要先确定摘要粒度，否则容易产生大量噪声。
- 业务产物向量化依赖 4.6，当前虽已具备条件，但不能代表整个 Memory V2。
- 先完成总架构，可避免后续不同记忆类型混用表、collection 和 prompt 角色。

## 14. 风险点

1. 把所有消息都向量化会造成噪声库和重复召回。
2. 用户画像过度推断会产生不准确、带偏见的长期上下文。
3. 业务产物记忆可能被误当成标准依据。
4. 文档 RAG 和业务产物记忆混在一起会污染检索。
5. 记忆注入过多会挤占上下文并降低当前任务质量。
6. 旧记忆可能与用户当前输入冲突。
7. 缺少删除和遗忘机制会产生隐私与合规隐患。
8. 多用户隔离必须严格依赖 `user_id`，并在检索阶段强制执行。
9. `session_id`、`artifact_id`、`version_id` 和来源消息范围必须保留可追溯性。
10. SFT 不应在 Memory V2 初期实施。
11. PostgreSQL 与 Milvus 状态不一致可能导致已禁用记忆继续召回。
12. 未设置任务路由和 token 预算时，记忆层越多不代表效果越好。

## 15. 验收标准

本阶段只验收文档，不验收代码。

1. 文档明确 Memory V1 和 Memory V2 的区别。
2. 文档明确短期会话记忆、长期对话记忆、用户画像、业务产物记忆和外部 RAG 的边界。
3. 文档明确哪些内容只进入 PostgreSQL，哪些内容可以进入 Milvus。
4. 文档明确长期对话记忆和业务产物记忆使用独立 collection，不能污染原文档 RAG。
5. 文档明确业务产物记忆不是标准依据。
6. 文档明确不同任务的记忆检索范围和选择性注入原则。
7. 文档明确更新、删除、过期和冲突处理原则。
8. 文档明确与 4.6 的依赖方向和兼容边界。
9. 文档明确重新规划后的 5.x 路线。
10. 文档明确下一步优先做用户画像结构化记忆，而不是直接做业务产物向量化。
11. 文档明确本阶段不修改任何代码。

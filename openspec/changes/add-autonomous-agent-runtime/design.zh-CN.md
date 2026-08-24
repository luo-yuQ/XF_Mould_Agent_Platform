## 背景

当前仓库已经具备 FastAPI 入口、React 前端、PostgreSQL、Redis、基于 Milvus 的知识检索、MinIO，以及多个 LangGraph 风格的业务图。现有图可以作为业务能力，但固定拓扑还不能作为真正的 Runtime 契约。引入新 Harness 时，必须保持现有 Memory V1、FMEA、Audit、Report 和 RAG 流程兼容。第一版文件上传只支持 PDF、DOCX、TXT，所有 Run 和知识记录都必须带租户边界。

动机见 `proposal.md`，外部行为契约见各 capability 的 spec 文件。

## 目标 / 非目标

**目标：**

- 以 Run 作为执行和观测的基本单位。
- 每一轮都允许 Agent 在检索证据、调用原子工具、执行已注册能力、向用户提问、等待审批和完成任务之间自主选择。
- 将 State、受限 Context、Memory 和 Knowledge Evidence 保持为不同的数据概念。
- 为 ToolExecutor 提供策略控制边界，并为 Workflow 提供独立的执行器。
- 异步处理用户上传的知识文件，并保留来源、版本和租户范围信息。
- 记录足够的结构化 Trace 数据，用于评测以及未来准备训练数据。

**非目标：**

- 本 change 不重写现有 FMEA、Audit、Report 或聊天图。
- Runtime 契约不绑定冷冲压或售后业务。
- 本 change 不实现 SFT、RL、隐藏思维链存储或自主部署动作。
- 不把 RAG 当作 Tool，也不要求所有 Run 遵循固定工作流顺序。
- 不改变 Memory V1 语义，也不改变现有业务产物的 Milvus 入库行为。

## 设计决策

### 1. 将 Run 执行和文件入库分开

使用 `Run` 表示 Agent 任务，使用 `IngestionJob` 表示异步文档处理。文件属于租户级知识范围，可以被该租户的多个 Run 引用，不绑定到上传文件的某一个对话。大文件解析不能占用 Run Worker。

**考虑过的方案：**把入库建模成特殊的 Agent Tool。放弃原因是上传和索引属于数据平面操作，它们的重试、权限和进度语义与 Tool 不同。

### 2. 使用小型 Action 协议，而不是固定图

Agent Loop 每轮输出结构化决策，包含动作类型、目标、经过校验的参数、简短决策摘要、预期结果和是否完成。Runtime 根据动作把请求分发给 Knowledge Service、ToolExecutor、Workflow Runner、用户交互接口或终止逻辑。动作结果写回 State 后，模型再次做下一轮决策。

决策摘要必须可观测且有长度限制；隐藏思维链不是必需字段，也不持久化。

**考虑过的方案：**继续扩展 Supervisor 图，增加更多固定分支。放弃原因是它仍然是 Workflow-first 模式，限制了模型自由选择开放式动作序列。

### 3. State 是事实来源，Context 是派生结果

State 是当前 Run 的事实来源，包含目标、约束、消息、动作、工具和 Workflow 输出、Evidence 引用、产物、状态、预算和终止原因。Context Builder 根据 State、选中的 Memory 和 Evidence 生成受模型上下文窗口限制的输入，并记录本轮包含和省略了哪些内容。Memory 单独持久化，只有被明确选为长期信息的内容才能写入。

**考虑过的方案：**把完整 Prompt 作为主要 State。放弃原因是 Prompt 有损、难以重放，而且混合了事实和展示层选择。

### 4. 分离 Tool Registry、ToolExecutor 和 Workflow Runner

Tool Registry 提供工具元数据和参数 Schema。ToolExecutor 在 Policy/Sandbox 控制下校验并执行 `grep`、`bash`、`write_file` 等原子操作。Workflow Registry 和 Workflow Runner 暴露已有的多步骤能力，但不把它们标记成 Tool。两者都向 Loop 返回结构化 ActionResult，但权限和风险模型不同。

**考虑过的方案：**把每个 Workflow 都包装成 Tool。放弃原因是这会隐藏业务能力边界，使权限、Trace 和未来的能力发现变得模糊。

### 5. 复用现有知识入库边界

新的上传流程尽可能调用现有的文档解析、切分和索引边界，只增加 Runtime 所需的文件、任务和租户范围契约。原始文件存放在对象存储，PostgreSQL 保存文件、版本和任务元数据，Milvus 继续作为知识 Chunk 的检索索引。业务产物入库和现有 RAG 查询行为不改变。

**考虑过的方案：**直接把上传文件内容放进 Run State。放弃原因是会破坏 Context 预算，无法在多个 Run 间复用，也会丢失文档和版本来源。

### 6. 使用 Celery、分离队列和幂等 Checkpoint

Celery 使用 Redis 作为 Broker 和 Result Backend，为 Run 任务和知识入库任务设置独立队列。每个动作都有执行标识和幂等/Checkpoint 边界。带副作用的 Tool 必须先经过策略判定，已经完成的副作用在没有明确幂等检查时不能因为重放而重复执行。

**考虑过的方案：**使用 ARQ，或让 FastAPI 同步执行整个 Loop 和入库流程。ARQ 同样是 Python Redis 队列，并且更偏 asyncio；本项目选择 Celery，是因为它在任务路由、重试、监控和生态方面更加成熟。同步请求则会受到模型调用、工具执行和文档处理耗时的限制，也难以从 Worker 重启中恢复。

### 7. 为现有能力增加适配器

现有聊天、FMEA、Audit、Report 图通过兼容适配器注册为能力。它们的入口和产物契约保持不变。适配器把能力调用转换为结构化 ActionResult，并保留现有引用和验证行为。

**考虑过的方案：**立刻让每个旧图理解新的 Runtime State。放弃原因是改动面过大，容易破坏已经可用的流程。

### 8. 映射到现有服务拓扑

- PostgreSQL：租户相关的 Run 元数据、动作和 Trace 元数据、文件/版本/任务元数据、权限范围和终态结果。
- Redis：Celery Broker/Result Backend、锁、进度通知和热 Checkpoint 协调。
- MinIO/对象存储：原始上传文件和不适合放进数据库的产物。
- Milvus：复用现有知识检索边界，用于知识 Chunk 索引。

具体表名和队列库内部实现可以变化，但 API 和事件契约必须稳定。

## 风险 / 取舍

- [自主 Loop 运行过久或花费过高] → 强制执行步数、时间、Token、费用预算，检测重复动作，并提供停止接口。
- [Bash 和写文件工具可能破坏数据] → 默认拒绝策略、工作区路径白名单、Sandbox、超时、审批门和完整副作用 Trace。
- [Context 筛选可能遗漏重要事实] → 保留完整 State，记录本轮包含和省略的内容，让 Evidence 引用保持紧凑且可追溯。
- [上传文件可能恶意或格式错误] → 校验 PDF/DOCX/TXT 类型、大小和内容，隔离解析 Worker，保留失败任务状态，不将不完整版本暴露为可检索内容。
- [租户边界可能被绕过] → 在 Run、文件、IngestionJob 和检索的每个边界强制校验租户标识，并增加跨租户拒绝测试。
- [RAG Evidence 质量可能不足] → 保留来源、版本和 Chunk 元数据，明确返回空结果，并要求 Agent 在证据不足时表达不确定性。
- [适配器可能隐藏旧图兼容问题] → 先做只读能力注册和契约测试，第一阶段不修改旧图拓扑。
- [Trace 可能包含敏感内容] → 默认只保存结构化决策摘要和引用，对 Tool 参数和输出做脱敏，不依赖隐藏思维链字段。

## 迁移计划

1. 增加 Runtime 契约和带租户信息的持久化/事件类型，不改变现有路由。
2. 增加最小 Run API、Celery 队列、Worker、Loop、Checkpoint 和 Trace，先使用无副作用 Demo Capability。
3. 增加 Tool Registry、ToolExecutor 和策略/审批控制，先启用只读工具，再启用 `bash` 和 `write_file`。
4. 复用现有知识入库边界，增加 PDF/DOCX/TXT 上传和 IngestionJob，再向 Loop 提供租户范围内的 Evidence。
5. 通过兼容适配器注册现有图，并确认它们原有接口测试继续通过。
6. 后端契约稳定后，再增加前端 Run、Trace、上传和入库状态页面。

回滚方式是停用新的 Run 和入库路由/Worker 消费者。现有聊天和业务 Workflow 路由继续作为回退路径，不做原地迁移。

## 待后置决定的问题

- PDF、DOCX、TXT 分别使用什么解析器和切分策略？这个问题在入库契约和 Worker 边界稳定后再决定。

## 1. Runtime 基础和契约

- [ ] 1.1 建立独立的 Runtime 模块边界，覆盖 Run、Loop、State、Context、Event、Tool、Capability、Knowledge 和 Worker，并且不修改现有业务图；通过新模块导入检查验证。
- [ ] 1.2 增加 Celery 和 Redis 配置，为 Run 和知识入库设置独立队列；通过启动本地 Celery Worker 并成功执行一个 Smoke Task 验证。
- [ ] 1.3 定义带版本的 Run、ActionDecision、ActionResult、StateSnapshot、EvidenceSet、ToolResult、TraceEvent、FileVersion 和 IngestionJob Schema，并包含必填的 `tenant_id`；通过 Schema 测试覆盖合法和非法载荷。
- [ ] 1.4 为 Run 创建、文件上传、入库、检索和 Tool 执行增加统一的租户边界校验；通过测试验证缺少租户或租户不匹配时会在派发前被拒绝。
- [ ] 1.5 增加 Run、动作 Event、Checkpoint、文件、文件版本和入库任务的 PostgreSQL 持久化；通过在干净数据库上执行迁移验证，并确认不改变已有表行为。

## 2. Run 生命周期和 Agent Loop

- [ ] 2.1 实现 Run 创建、状态查询、取消、提交用户回复和提交审批回复的契约；通过测试验证每个状态转换都持久化，并且租户标识不可变。
- [ ] 2.2 实现规范化 State 存储和追加式 TraceEvent 记录；通过 Run id 和租户 id 加载 State Snapshot 验证。
- [ ] 2.3 实现动作边界的 Checkpoint 和恢复 Token；通过模拟 Worker 重启验证从最近 Checkpoint 恢复时不会重复已完成动作。
- [ ] 2.4 实现 Context Builder，支持 Token/字符预算、State 优先级、选中的 Memory、Evidence 引用以及包含/省略元数据；通过超预算测试验证截断结果确定且可重复。
- [ ] 2.5 实现结构化 LLM 决策适配器，校验动作类型和受限的决策摘要；通过测试验证模型返回非法或不支持的决策时只产生拒绝型 ActionResult，不会执行动作。
- [ ] 2.6 实现 Agent Loop 的动作分发，支持 respond、ask-user、retrieve-evidence、invoke-capability、call-tool、wait-approval 和 finish；通过 Mock Run 验证可以多轮执行后再完成。
- [ ] 2.7 增加步数、时间、Token、费用、重复动作和取消保护；通过测试验证每种保护都会产生终态 Run 和机器可读的终止原因。
- [ ] 2.8 增加 Celery Run Task 和 queued、running、waiting、completed、failed、cancelled、timed-out 状态的进度 Event；通过状态轮询验证 API 看到的状态与 Worker 持久化状态一致。
- [ ] 2.9 增加一个无副作用 Demo Capability，用于验证最小垂直链路；通过 Mock 目标验证 Run 能检索结果、更新 State，并经由 Loop 完成。

## 3. Tool Registry 和 ToolExecutor

- [ ] 3.1 实现 Tool Registry 的元数据和输入/输出 Schema 发现，包含风险等级和权限声明；通过测试验证 Context Builder 只暴露当前 Run 租户和策略允许的 Tool。
- [ ] 3.2 实现 ToolExecutor 的参数校验、策略评估、超时处理、标准化 ToolResult 和执行标识；通过测试验证非法或不允许的调用不会到达操作系统进程。
- [ ] 3.3 实现只读的 `list_files`、`read_file` 和 `grep`，并限制工作区路径；通过路径穿越测试验证不能访问允许目录之外的路径。
- [ ] 3.4 实现带 Sandbox 的 `bash`，限制命令、环境、超时和资源；通过超时测试验证返回失败结果并写入审计 Event。
- [ ] 3.5 实现带路径白名单、差异/大小限制和审批门的 `write_file`；通过测试验证 Run 等待审批时不会修改任何文件。
- [ ] 3.6 记录脱敏后的参数、策略决定、审批决定、输出、错误、耗时和副作用元数据；通过 Trace 检查验证运维人员能够还原一次 Tool 调用。

## 4. 租户范围内的知识入库

- [ ] 4.1 增加 PDF、DOCX、TXT 上传和文件元数据契约，包含大小/内容校验和租户归属；通过测试验证不支持的格式和伪造的租户声明都会被拒绝。
- [ ] 4.2 将原始上传文件保存到对象存储，并在 PostgreSQL 保存文件/版本/任务元数据，不把文件绑定到单个对话；通过测试验证同租户的另一个 Run 可以引用已完成的文件版本。
- [ ] 4.3 增加 Celery 入库 Task，支持 queued、processing、completed、failed 状态以及重试/幂等 Key；通过测试验证失败任务不会被当作完整版本检索。
- [ ] 4.4 定义解析器/切分器 Provider 边界，并记录 PDF、DOCX、TXT 后续具体方案；通过 Provider 契约测试验证能够输出 Chunk 文本、位置、版本和租户元数据。
- [ ] 4.5 将已完成的文件版本接入现有知识索引边界，不改变业务产物入库行为；通过检索测试验证索引 Chunk 保留文档、版本、位置和租户元数据。
- [ ] 4.6 实现 Knowledge Service 检索，根据 Run 租户过滤并返回带来源引用的 EvidenceSet；通过测试验证跨租户检索被拒绝，同租户文件可以跨对话复用。
- [ ] 4.7 向 Run/API 层暴露入库任务状态和进度 Event；通过客户端测试验证可以区分上传接受、处理中、失败和可检索完成。

## 5. Capability 和现有 Workflow 集成

- [ ] 5.1 实现独立于 Tool Registry/ToolExecutor 的 Workflow/Capability Registry 和 Runner 契约；通过测试验证 Capability 结果是 ActionResult，而不是 ToolResult。
- [ ] 5.2 为现有聊天、FMEA、Audit 和 Report 入口增加兼容适配器，不改变它们的图拓扑和公开行为；通过现有接口测试验证回归测试继续通过。
- [ ] 5.3 将 Capability 发现和租户/策略过滤接入 Context Builder；通过测试验证 Agent 只有在当前 Run 可用该契约时才能选择对应 Capability。

## 6. API、Event 和前端最小切片

- [ ] 6.1 使用 Runtime Schema 暴露 Run 创建、状态查询、取消、回复、审批和 Event Stream 接口；通过 API 测试验证响应包含 Run id、租户安全状态和终止信息。
- [ ] 6.2 暴露文件上传、入库任务状态和租户范围知识检索接口；通过接口测试验证 PDF/DOCX/TXT 上传的进度独立于 Agent Run。
- [ ] 6.3 增加最小 React Run 页面，显示状态、动作时间线、审批提示和最终结果；通过浏览器测试验证重新连接已有 Run 后不会丢失 Event。
- [ ] 6.4 增加最小 React 文件上传和入库状态页面；通过浏览器测试验证文件按租户范围展示，而不是作为仅属于某个对话的附件展示。

## 7. 验证、运维和未来数据准备

- [ ] 7.1 增加 State/Context 分离、动作校验、终止保护、ToolExecutor 策略、Evidence 引用和租户隔离的单元测试；通过聚焦测试套件验证。
- [ ] 7.2 增加依赖 PostgreSQL、Redis、Celery、对象存储和 Milvus 的集成测试；通过端到端测试验证 Run 和 IngestionJob 都能完成。
- [ ] 7.3 增加跨租户 Run 查询、文件检索、Evidence 检索、Tool 路径、Bash 命令和写文件审批的安全回归测试；通过测试验证每次拒绝都有审计记录。
- [ ] 7.4 执行现有聊天/FMEA/Audit/Report 回归测试，并确认现有接口和 Memory V1 行为没有变化。
- [ ] 7.5 编写 Run、ActionDecision、ToolResult、EvidenceSet、IngestionJob、租户边界和运维命令文档；通过文档审查确认内容与实际 Schema 一致。
- [ ] 7.6 保存结构化决策摘要、动作结果、Evidence 引用、Verifier 结果、用户反馈以及模型/版本元数据，为未来评测数据集做准备；通过数据检查确认不依赖隐藏思维链字段。

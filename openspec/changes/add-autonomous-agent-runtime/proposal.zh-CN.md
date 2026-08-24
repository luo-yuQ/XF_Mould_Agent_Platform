## 为什么

当前项目主要由一组预定义工作流组成，还没有真正意义上的自主 Agent Runtime。我们需要一个与业务领域解耦、以 Run 为驱动的执行底座，让模型能够判断当前信息是否充足，并在知识检索、工具调用、已注册能力、向用户提问和完成任务之间进行选择，在明确的安全策略与预算约束下循环执行。

在清理前端或重写现有业务工作流之前，先建立这个底座是合适的顺序。它还会形成稳定的执行轨迹，为后续评估、SFT 或 RL 数据准备提供基础，但本次不进行任何训练。

## 变更内容

- 增加 Run 生命周期和异步执行模型，底层使用 FastAPI、Celery、Redis 与 Worker。
- 增加由决策和终止条件驱动的自主 Agent Loop，不再要求所有任务遵循固定业务顺序。
- 定义规范化 State、有界 Context 构建、跨 Run Memory、Checkpoint、Event 和 Replay 元数据。
- 为原子工具和多步骤工作流分别增加 Registry 与 Runner。
- 增加带策略控制的 `ToolExecutor`，支持 `read_file`、`list_files`、`grep`、`bash` 和 `write_file`，包含参数校验、审批、Sandbox、超时处理和标准化结果。
- 支持用户上传 PDF、DOCX 和 TXT，并异步执行知识入库，包括对象存储、解析、切分、Embedding、Milvus 索引、元数据和检索证据。
- 强制租户隔离：每个 Run 和知识记录都必须携带租户边界；Run 可以使用同一租户内共享的文件，但绝不能访问其他租户的文件。
- 将 RAG 定义为 Knowledge / Evidence 子系统，而不是 Tool，也不是固定工作流中的某个必经阶段。
- 保持现有 FMEA、Audit、Report 和聊天行为可用，将它们作为可选 Capability 暴露，而不是 Runtime 的强制执行路径。
- 移除产品层面对冷冲压和售后场景的依赖；这些场景可以在未来作为 Capability Pack 加入。

## 能力

### 新增能力

- `agent-runtime`：Run 生命周期、Agent Loop、State、Context、Memory、终止控制、Checkpoint、Event 和 Replay 契约。
- `tool-execution`：工具元数据、策略校验、审批、Sandbox 执行和标准化 `ToolResult` 处理。
- `knowledge-ingestion`：租户范围内的 PDF/DOCX/TXT 上传、异步入库任务、文档元数据与版本管理、Chunk 索引、检索和证据引用。

### 修改能力

无。现有业务工作流保持兼容，本次不重写这些工作流。

## 影响

- FastAPI 将增加 Run、Event、文件、入库任务和知识检索相关契约。
- Celery 使用 Redis，并为 Run 任务和知识入库任务设置独立队列，用于进度通知、锁和热状态 Checkpoint。
- PostgreSQL 保存带租户信息的 Run 元数据、State/Trace 元数据、文件与入库元数据、权限范围和任务状态。
- MinIO（或现有对象存储服务）保存原始上传文件；Milvus 保存 Chunk Embedding 和检索索引。
- React 前端后续需要增加 Run 状态/Trace 和文件上传页面，但本次规划不包含前端清理工作。
- 现有 FMEA、Audit、Report 图应在后续实现阶段通过 Capability Registry 包装接入，不改变它们当前的契约。

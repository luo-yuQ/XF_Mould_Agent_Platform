# R&D Agent 说明书

## 负责什么

- 回答研发、模具技术、FMEA 方法论、DFMEA/PFMEA、失效模式、风险评级相关问题。
- 基于 FMEA 手册知识库进行 RAG 问答。
- 输出带引用的 FMEA / 研发相关回答。
- 在主问答链路中作为 `rd` 分支运行。

## 不负责什么

- 不负责独立 FMEA 生成 MVP 的结构化 rows 生成。
- 不保存 `fmea_runs`。
- 不做审核检查。
- 不写 `audit_runs`。
- 不修改 Memory。
- 不修改 Milvus 入库。
- 不接收文件上传。

## 输入字段

- `messages`：对话历史和用户当前问题。
- `rag_chunks`：FMEA 手册检索结果。
- `rag_result`：兼容旧协议的检索文本。

## 输出格式

更新 `AgentState`：

- `messages`：追加研发/FMEA 回答。
- `sender="rd_writer"`。
- `citation_map`：引用元数据。
- `citation_ids`：实际引用 ID。
- `rag_is_relevant`：是否使用引用。
- `task_completed=True`。

## 必须遵守哪些标准

- FMEA 专业内容优先基于 FMEA 手册检索材料。
- 使用 `[N]` 标注引用来源。
- 不得编造 FMEA 标准条款、页码或章节。
- 没有检索依据时，应说明依据不足或基于通用知识。
- 不应改写独立 FMEA MVP 已校验 rows。

## 什么时候调用 RAG

- 主 graph 路由到 `rd_rag` 时调用。
- 使用 `retrieve_structured(query, MILVUS_COLLECTION_FMEA)`。
- RAG 在 writer 生成回答之前执行。

## 什么时候提示信息不足

- 用户要求分析具体失效但没有提供产品、工序、失效现象时。
- 用户要求评分或措施但缺少现场数据、客户要求或现行控制信息时。
- 检索不到可靠依据时，应提示缺少手册依据。

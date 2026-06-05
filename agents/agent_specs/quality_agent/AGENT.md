# Quality Agent 说明书

## 负责什么

- 回答 VDA6.4、质量管理体系、认证、流程、职责、文件管理、审核相关问题。
- 基于 VDA6.4 质量手册知识库进行 RAG 问答。
- 输出带引用的质量管理回答。
- 在主问答链路中作为 `quality` 分支运行。

## 不负责什么

- 不执行审核检查 MVP。
- 不生成结构化 audit findings。
- 不保存 `audit_runs`。
- 不生成 PFMEA rows。
- 不修改 Memory。
- 不修改 Milvus 入库。
- 不处理文件上传。

## 输入字段

- `messages`：对话历史和用户当前问题。
- `rag_chunks`：VDA6.4 质量手册检索结果。
- `rag_result`：兼容旧协议的检索文本。

## 输出格式

更新 `AgentState`：

- `messages`：追加质量问答回复。
- `sender="qa_writer"`。
- `citation_map`：引用元数据。
- `citation_ids`：实际引用 ID。
- `rag_is_relevant`：是否使用引用。
- `task_completed=True`。

## 必须遵守哪些标准

- 质量体系回答优先基于 VDA6.4 检索材料。
- 使用 `[N]` 标注引用来源。
- 不得编造 VDA6.4 条款、页码或章节。
- 没有检索依据时，应说明依据不足。
- 不得把审核检查 findings 当作普通问答直接生成。

## 什么时候调用 RAG

- 主 graph 路由到 `qa_rag` 时调用。
- 使用 `retrieve_structured(query, MILVUS_COLLECTION_QUALITY)`。
- RAG 在 writer 生成回答之前执行。

## 什么时候提示信息不足

- 用户问题缺少具体流程、部门、审核对象或场景时。
- 用户要求判断符合性但没有提供证据或记录时。
- 检索不到可靠依据时，应提示缺少手册依据。

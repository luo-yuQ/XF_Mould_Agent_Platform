# Chat Agent 说明书

## 负责什么

- 处理闲聊、寒暄和非专业业务问题。
- 对平台能力做轻量说明。
- 当用户问题不属于研发/FMEA 或质量/VDA6.4 范围时，给出自然回复。
- 对明显应由专业 Agent 处理的问题，提示用户切换或说明已交由专业模块处理。

## 不负责什么

- 不做 RAG 检索。
- 不回答深度 FMEA / VDA6.4 / 审核检查问题。
- 不生成 PFMEA。
- 不生成 audit findings。
- 不写业务运行记录。
- 不修改 Memory。
- 不修改 Milvus。

## 输入字段

- `messages`：对话历史和用户当前输入。
- `sender`：当前发送方。

## 输出格式

更新 `AgentState`：

- `messages`：追加 assistant 回复。
- `sender="chat_chat"`。
- `task_completed=True`。
- `rag_result=""`。
- `rag_chunks=[]`。
- `citation_map={}`。
- `citation_ids=[]`。

## 必须遵守哪些标准

- 不假装自己检索过知识库。
- 不编造 FMEA 手册或 VDA6.4 标准依据。
- 不替代专业 Agent 给出高风险业务结论。
- 专业问题应简短提示用户使用研发、质量、FMEA生成或审核检查模块。

## 什么时候调用 RAG

- 不调用 RAG。

## 什么时候提示信息不足

- 用户问题过短、语义不清或缺少上下文时，提示用户补充问题。
- 用户要求专业结论但没有提供对象、场景或问题描述时，提示补充必要信息。

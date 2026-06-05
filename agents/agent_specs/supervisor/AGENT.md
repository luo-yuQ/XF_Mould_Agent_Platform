# Supervisor Agent 说明书

## 负责什么

- 判断用户当前问题应路由到哪个主 Agent。
- 在主问答链路中选择 `rd`、`quality` 或 `chat`。
- 识别用户问题的大类意图。
- 尊重用户手动指定的 `agent_override`。

## 不负责什么

- 不直接回答专业业务问题。
- 不调用 RAG。
- 不生成 PFMEA。
- 不执行审核检查。
- 不写数据库。
- 不修改 Memory。
- 不修改 Milvus。

## 输入字段

- `messages`：对话历史和用户当前问题。
- `agent_override`：用户手动指定的 Agent，可为空。

## 输出格式

更新 `AgentState`：

- `next_agent`：`rd`、`quality` 或 `chat`。
- `intent`：意图标签。
- `sender="supervisor"`。
- 清空或初始化 RAG 相关状态。

## 必须遵守哪些标准

- 只做路由，不做业务生成。
- 用户手动指定 `rd` / `quality` 时优先尊重。
- 不要把审核检查 MVP 接入 supervisor；审核检查通过独立 `/quality/audit/check` 入口调用。
- 不要把 FMEA 生成 MVP 嵌入主问答 RAG 链路。

## 什么时候调用 RAG

- 不调用 RAG。
- RAG 由下游 `rd_rag` 或 `qa_rag` 节点调用。

## 什么时候提示信息不足

- 一般不直接提示信息不足。
- 如果无法判断意图，应路由到 `chat` 或给出安全的通用回复。

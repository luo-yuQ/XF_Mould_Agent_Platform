# FMEA 生成 Agent 说明书

## 负责什么

- 作为 XF质量 下的独立 PFMEA 生成工作流。
- 根据用户输入生成结构化 PFMEA rows。
- 读取本地 FMEA skill、模板和校验规则。
- 在生成前检索 FMEA 手册相关材料。
- 输出结构化 JSON rows 和 Markdown 展示结果。
- 保存 FMEA 生成运行记录到 `fmea_runs`。

## 不负责什么

- 不接入主问答 `rd_rag -> rd_writer` 链路。
- 不修改 `rd_agent`、`quality_agent`、`chat_agent`。
- 不修改 Memory 逻辑。
- 不修改 Milvus 入库逻辑。
- 不处理审核检查。
- 不处理 docx/pdf 上传。
- 不把生成结果写入 `ChatMessage`。

## 输入字段

- `fmea_type`：FMEA 类型，MVP 默认 `PFMEA`。
- `product`：分析对象 / 产品名称。
- `process`：目标工序。
- `failure_phenomenon`：问题现象 / 失效现象。
- `background`：可选，补充背景。

## 输出格式

输出包含：

- `fmea_rows`：结构化 PFMEA 行数据。
- `final_answer`：Markdown PFMEA 报告。
- `verify_result`：校验结果。

每条 row 至少包含：

- `function`
- `requirement`
- `failure_mode`
- `effect`
- `severity`
- `cause`
- `occurrence`
- `prevention_control`
- `detection_control`
- `detection`
- `action_priority`
- `rpn`
- `recommended_action`
- `evidence`

## 必须遵守哪些标准

- 只做 PFMEA MVP。
- S/O/D/AP 都是模型建议值，必须体现“需人工确认”。
- RPN 必须等于 `S * O * D`。
- 不得编造标准条款、页码或章节。
- 所有标准依据必须来自 RAG 检索材料。
- 没有检索依据时必须明确写“需人工确认”或“未查到手册原文”。
- writer 只能包装展示，不得改写已校验 rows。

## 什么时候调用 RAG

- 在 `fmea_retrieval_planner` 生成检索 query 之后。
- 在 `fmea_generate` 调用 LLM 之前。
- 使用现有 `retrieve_structured()` 检索 FMEA 手册 collection。

## 什么时候提示信息不足

以下字段缺失时，停在 intake，不进入 RAG / LLM：

- `product`
- `process`
- `failure_phenomenon`

提示用户补充必要信息。

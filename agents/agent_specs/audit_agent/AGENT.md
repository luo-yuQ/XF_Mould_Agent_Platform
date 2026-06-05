# 审核检查 Agent 说明书

## 负责什么

- 作为 XF质量 下的独立审核检查工作流。
- 审核用户粘贴的质量问题描述、PFMEA 内容、审核记录或一般文本。
- 生成结构化审核发现 findings。
- 检查问题、风险、输入依据、规范依据、整改建议和是否需人工确认。
- 在生成前检索 VDA6.4 / FMEA 相关材料。
- 输出 Markdown 审核检查报告。
- 保存审核检查运行记录到 `audit_runs`。

## 不负责什么

- 不接 Supervisor / 监管者 Agent。
- 不做自动意图识别。
- 不处理 docx/pdf 上传。
- 不解析文件。
- 不修改 FMEA Agent。
- 不修改 Memory。
- 不修改 Milvus 入库逻辑。
- 不修改现有 RAG 问答主流程。
- 不写入 `ChatMessage`。

## 输入字段

- `audit_type`：审核类型，只能是 `quality_issue`、`pfmea`、`audit_record`、`general`。
- `content`：用户粘贴的待审核文本。
- `focus`：可选，审核重点。
- `background`：可选，补充背景。

## 输出格式

API 返回：

- `final_answer`：Markdown 审核检查报告。
- `findings`：结构化审核发现。
- `verify_result`：校验结果。
- `references`：检索引用来源。

每条 finding 必须包含：

- `issue`：发现问题。
- `category`：问题类型。
- `risk_level`：风险等级，只能是 `低`、`中`、`高`、`需人工确认`。
- `risk_explanation`：风险说明。
- `evidence_from_input`：来自用户输入的依据。
- `basis`：来自 FMEA手册 / VDA6.4 的规范依据。
- `recommendation`：整改建议。
- `manual_check_required`：是否需要人工确认。

## 必须遵守哪些标准

- 不得编造标准条款、页码、章节或文件要求。
- `basis` 没有充分检索依据时必须写“需人工确认”。
- `manual_check_required` 在依据不足、输入不完整或风险无法判断时必须为 `true`。
- `recommendation` 必须针对具体问题，不能只写“加强管理”“提高意识”“加强培训”。
- verifier 不通过时最多 repair 一次。
- writer 只能包装展示，不得改写已校验 findings。

## 什么时候调用 RAG

- 在 `audit_retrieval_planner` 生成 query 后。
- 在 `audit_check` 调用 LLM 生成 findings 前。
- 根据 query 内容检索 VDA6.4 质量手册和 FMEA 手册。
- 复用现有 `retrieve_structured()`，不修改 RAG 核心逻辑。

## 什么时候提示信息不足

- `content` 为空时，`audit_intake` 直接提示需要补充待审核文本。
- `audit_type` 非法时，提示使用 `quality_issue`、`pfmea`、`audit_record` 或 `general`。
- 检索依据不足但仍能生成 findings 时，不中断流程；在 `basis` 写“需人工确认”，并设置 `manual_check_required=true`。

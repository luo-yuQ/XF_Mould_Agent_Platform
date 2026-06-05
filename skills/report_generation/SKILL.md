# 报告生成 Skill

## 定位

本 Skill 定义 XF质量 下报告生成工作流 MVP 的业务规则。

MVP 阶段唯一支持的报告类型是 `quality_issue_report`。

报告生成工作流可以整合用户已选择的 FMEA 运行结果、Audit 审核结果、可选 RAG 参考依据，以及用户补充背景。报告生成不得重新生成 FMEA 表，也不得重新生成审核发现。

## 输入

工作流输入使用 `ReportInput` 表示：

| 字段 | 必填 | 说明 |
|------|------|------|
| `report_type` | 是 | 必须是 `quality_issue_report`。 |
| `title` | 否 | 可选报告标题。 |
| `fmea_run_id` | 否 | 用户明确选择的 FMEA 运行记录 ID；提供时作为 MVP 主要来源。 |
| `audit_run_id` | 否 | 用户明确选择的 Audit 运行记录 ID；提供时作为 MVP 主要来源。 |
| `extra_background` | 否 | 用户补充的报告背景信息。 |
| `include_chat_summary` | 否 | 默认 `false`；仅预留给后续显式引入对话摘要，不自动启用。 |
| `quality_case_id` | 否 | 仅预留字段；MVP 不依赖完整质量案例系统。 |

## 输出

工作流输出使用 `ReportOutput` 表示：

| 字段 | 说明 |
|------|------|
| `report_type` | 报告类型。 |
| `title` | 最终报告标题。 |
| `source_fmea_run_id` | 来源 FMEA 运行记录 ID。 |
| `source_audit_run_id` | 来源 Audit 运行记录 ID。 |
| `sections` | 结构化报告章节。 |
| `final_markdown` | 完整 Markdown 报告。 |
| `assumptions` | 报告成文过程中的假设。 |
| `manual_check_items` | 需要人工确认的事项。 |
| `references` | 来自 FMEA、Audit、RAG 或用户输入的引用来源。 |
| `verify_result` | 报告校验结果。 |

## 固定章节

Markdown 报告必须按以下顺序包含固定章节：

1. 问题背景
2. 分析对象与范围
3. 参考依据
4. FMEA分析摘要
5. 审核发现摘要
6. 风险判断
7. 改进措施建议
8. 需人工确认事项
9. 结论

## 硬性规则

1. 只整合已有 FMEA、Audit、RAG 和用户补充背景。
2. 不得重新生成 FMEA。
3. 不得重新生成审核发现。
4. 不得编造标准条款。
5. FMEA 或 Audit 缺失时，对应章节必须写 `未提供相关结果，需人工确认`。
6. 每条建议都必须能追溯到 FMEA、Audit、用户输入或检索依据之一。
7. 只输出 Markdown，不生成 Word 或 PDF。
8. 必须保留已校验 FMEA 和 Audit 输出中的关键事实。
9. 依据不足时必须写 `需人工确认`。
10. `report_writer` 可以归纳、组织和成文，但不得改写已校验的 FMEA 或 Audit 关键事实。

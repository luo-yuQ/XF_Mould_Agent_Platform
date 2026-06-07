# Business Artifact Contract

本文档定义 4.5 阶段“业务产物元数据统一”的边界和字段契约。4.5 阶段只统一 FMEA、Audit、Report 三类业务产物的 run 级元数据，不做业务产物向量化。

## 业务产物类型

当前定义三类业务产物：

- `fmea_run`：FMEA 生成 Agent MVP 产生并保存的 FMEA 运行结果。
- `audit_run`：Audit 审核检查 Agent MVP 产生并保存的审核 findings。
- `report_run`：Report 报告生成 Workflow MVP 产生并保存的 Markdown 报告。

run 表统一类型字段命名为 `artifact_type`，取值为：

- `fmea_run`
- `audit_run`
- `report_run`

不要使用 `source_type` 表示 run 级业务产物类型，避免和 `ReportSection.source_type` 混淆。

## 统一元数据目标字段

| 字段 | 适用范围 | 说明 |
| --- | --- | --- |
| `id` | 全部 | run 主键。 |
| `user_id` | 全部 | 产物归属用户。 |
| `session_id` | 可选 | 只表示对话来源，不用于跨 Agent 自动匹配。 |
| `quality_case_id` | 可选 | 预留给未来质量案例系统，当前不强依赖。 |
| `artifact_type` | 全部 | run 级产物类型：`fmea_run` / `audit_run` / `report_run`。 |
| `title` | 全部 | 业务产物标题。 |
| `summary` | 全部 | 业务产物摘要，不是聊天摘要。 |
| `keywords_json` | 全部 | 面向展示、筛选、后续检索准备的关键词数组或结构化关键词。 |
| `input_json` | 全部 | 产物生成输入。Report 可保存标准化 report input。 |
| `output_json` | FMEA / Report 可选 | 结构化输出。FMEA 保存 rows；Report 可保存 sections 或结果结构。 |
| `findings_json` | Audit | Audit findings 结构化输出。 |
| `output_markdown` | FMEA | 面向用户展示的 FMEA Markdown。 |
| `final_markdown` | Audit / Report | 面向用户展示的最终 Markdown。 |
| `verify_result_json` | 全部 | verifier 结果。 |
| `retrieved_refs_json` | FMEA / Audit / 可选 Report | RAG 检索阶段原始引用信息，保留现有语义。 |
| `references_json` | 全部 | 业务产物统一引用摘要，可以由 `retrieved_refs_json` 映射而来。 |
| `source_snapshot_json` | 仅 Report | 报告生成时使用的 FMEA / Audit / RAG / 用户输入来源快照。 |
| `source_match_result_json` | 仅 Report | 报告来源匹配检查结果。 |
| `created_at` | 全部 | 创建时间。 |
| `updated_at` | 全部 | 最近更新时间。 |

## 关键语义约束

1. `session_id` 不是业务案例 ID。
2. Report 不能通过 `session_id` 自动匹配 FMEA / Audit。
3. Report 的主来源是用户明确选择的 `fmea_run_id` / `audit_run_id`。
4. 当前前端是生成式入口，不是对话式入口，因此 chat summary 不是 4.5 重点。
5. `summary` 指业务产物摘要，不是聊天摘要。
6. `quality_case_id` 是未来质量案例系统使用，当前只预留，不作为 4.5 强依赖。
7. `artifact_type` 是 run 级产物类型字段，避免使用 `source_type`。
8. `retrieved_refs_json` 保留 RAG 检索阶段原始引用语义；`references_json` 是后续统一展示、报告引用、向量化准备使用的引用摘要。
9. 4.5 不做 embedding、不写 Milvus、不做业务产物向量化。

## Report 来源规则

Report 生成必须以用户显式选择的来源为主：

- `fmea_run_id`
- `audit_run_id`
- 用户补充背景
- 可选 RAG 参考依据

Report 可以记录 `source_snapshot_json` 保存生成当时的来源快照。后续可增加 `source_match_result_json` 记录规则匹配结果，但 4.5 中匹配结果只作为人工确认提示，不作为强制拦截依据。

## 非目标

4.5 阶段不包含以下工作：

- embedding 相似度。
- 写入 Milvus。
- 业务产物向量化。
- 完整 `quality_cases` 系统。
- SFT。
- FMEA / Audit / Report Agent 主流程重构。
- 用 `session_id` 替代业务案例 ID 或自动匹配依据。

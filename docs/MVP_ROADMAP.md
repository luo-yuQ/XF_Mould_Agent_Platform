# MVP Roadmap

本文档记录当前 MVP、4.5 阶段边界，以及后续阶段的顺序。4.5 阶段目标是业务产物元数据统一，不扩展为向量化、质量案例系统、SFT 或 Agent 重构。

## 当前 MVP

- FMEA 生成 Agent MVP 已能生成并保存 FMEA 结果。
- Audit 审核检查 Agent MVP 已能生成并保存审核 findings。
- Report 报告生成 Workflow MVP 已能基于用户选择的 `fmea_run_id` / `audit_run_id` 生成 Markdown 报告。

## 4.5 阶段：业务产物元数据统一

### P0：补齐表字段

- 给 `fmea_runs`、`audit_runs`、`report_runs` 补齐统一元数据字段。
- 新增字段全部允许 nullable，兼容历史记录。

### P1：保存 run 时写入元数据

- FMEA / Audit / Report 保存 run 时写入 `title`、`summary`、`keywords_json`、`artifact_type`、`references_json`、`updated_at` 等元数据。
- `references_json` 可以从 `retrieved_refs_json` 映射生成。

### P2：API 透传 run_id

- FMEA API 返回 `fmea_run_id`。
- Audit API 返回 `audit_run_id`。
- API 只透传 graph state 或保存结果中已有 run_id，不重构 graph。

### P3：Report sources 优先读取持久元数据

- Report sources 接口优先读取持久化 `title` / `summary` / `keywords_json` / `artifact_type` / `updated_at`。
- 旧数据为空时 fallback 到现有拼装逻辑。

### P4：前端展示 sources 元数据

- 前端 Report sources 展示 `title` / `summary` / `keywords` / `artifact_type` / `created_at`。
- 用户更容易选择正确的 FMEA / Audit 来源。

### P5：Report 来源匹配检查

- Report 增加来源匹配检查。
- 只做规则提示，不做强制拦截。
- 匹配结果写入 `source_match_result_json`。
- 报告中写入需人工确认事项。

## 5.0 阶段

- 业务产物向量化记忆。
- 只有在元数据稳定后再做。

## 5.1 阶段

- 规则匹配 + metadata filter + embedding 相似度混合匹配。

## 5.2 阶段

- `quality_case_id` / `quality_cases` 质量案例系统。

## 后续：前端工作流稳定性

- 统一普通对话、FMEA、Audit、Report 的异步任务忙碌状态。
- 生成期间提供会话和业务页面切换保护，避免组件卸载后丢失前端任务状态。
- 后续结合持久化 run 或任务查询能力，支持页面切换后的状态恢复和结果找回。
- 该事项属于前端任务生命周期管理，不应依赖 `quality_case_id`，也不要求重构 Agent 主流程。

## 最后阶段

- SFT。
- 只有在工作流、数据结构、产物格式稳定后再考虑。

## 阶段边界

4.5 阶段只做业务产物元数据统一：

- 不做 embedding。
- 不写 Milvus。
- 不做业务产物向量化。
- 不做完整 `quality_cases` 系统。
- 不做 SFT。
- 不重构 FMEA / Audit / Report 主流程。

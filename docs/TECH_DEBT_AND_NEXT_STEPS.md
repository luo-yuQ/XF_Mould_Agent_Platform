# Technical Debt And Next Steps

本文档记录当前 FMEA / Audit / Report MVP 的技术债和下一步边界，供 4.5 阶段开发前阅读。

## 当前技术债

1. FMEA / Audit / Report 三类 run 字段不统一。
2. FMEA / Audit 当前可能缺少 `title` / `summary` / `keywords_json`。
3. Report 当前依赖用户手动选择 `fmea_run_id` / `audit_run_id`。
4. Report 当前不能可靠判断 FMEA 和 Audit 是否属于同一质量问题。
5. 规则匹配只能作为人工确认提示，不能作为强判断。
6. 业务产物尚未向量化。
7. `quality_case_id` 只是未来方向，当前不应大规模实现。
8. `session_id` 不能误用为业务案例 ID。
9. Report sources 当前部分 summary 可能是运行时拼出来的，不是持久字段。
10. 旧数据缺少元数据时必须有 fallback。
11. FMEA / Audit / Report 的提交状态目前只保存在各页面组件内部。生成过程中如果用户切换会话或切换业务页面，组件可能卸载，正在进行的请求和结果展示状态无法在前端恢复。后端即使已完成并保存 run，用户也可能看不到本次结果和 run_id。
12. 普通对话已在流式响应期间限制切换会话，但该全局忙碌状态尚未覆盖 FMEA / Audit / Report，当前不同入口的交互约束不一致。

## 下一步建议

1. 先补齐业务产物统一元数据字段，并保持新增字段 nullable。
2. 在保存 FMEA / Audit / Report run 时写入稳定的 `title`、`summary`、`keywords_json`、`artifact_type`、`references_json`、`updated_at`。
3. 让 FMEA / Audit API 透传已保存的 run id，避免前端生成后不知道产物 ID。
4. Report sources 优先读取持久化元数据，旧数据为空时继续使用现有拼装逻辑。
5. Report 来源匹配只做规则提示，把结果写入 `source_match_result_json`，并体现在人工确认事项中。
6. 后续增加统一的前端异步任务状态管理。至少覆盖 FMEA / Audit / Report 的运行中状态、当前任务所属会话、页面切换保护、完成后结果恢复和失败重试提示。
7. 在统一任务状态完成前，可先采用低风险方案：业务产物生成期间禁用会话切换和业务模块切换，并明确提示“当前任务生成中”。长期方案应以持久化 run 状态或任务查询接口恢复结果，而不是只依赖 React 组件局部 state。

## 前端工作流稳定性验收建议

- FMEA / Audit / Report 生成期间，用户不能无提示地切换到导致任务状态丢失的页面或会话。
- 若允许切换，返回原页面后应能恢复任务状态，并在完成后展示结果及对应 run_id。
- 任务状态必须关联明确的业务类型和发起时的 `session_id`，不能把 `session_id` 当成 `quality_case_id`。
- 后端已保存成功但前端请求中断时，用户应能通过历史产物列表重新找到结果。
- 普通对话流式请求与 FMEA / Audit / Report 任务的禁用、取消和错误提示行为应保持一致。

## 暂不处理

以下事项不是 4.5 阶段目标：

- embedding 相似度。
- 写入 Milvus。
- 业务产物向量化记忆。
- 完整 `quality_cases` 系统。
- SFT。
- FMEA / Audit / Report Agent 主流程重构。

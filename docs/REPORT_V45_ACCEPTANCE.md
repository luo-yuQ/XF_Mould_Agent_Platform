# Report 4.5 验收说明

本文档用于验收 4.5 阶段业务产物元数据、run_id 透传、Report 来源选择和来源匹配提示。验收不涉及 embedding、Milvus、quality_cases、SFT、Word/PDF 导出或业务产物二次追改。

## 前置条件

- 已执行数据库迁移，`fmea_runs`、`audit_runs`、`report_runs` 包含 4.5 元数据字段。
- 后端和前端已启动，测试用户已登录。
- 浏览器开发者工具的 Network 面板已打开，用于查看接口响应。

## 手动验收步骤

1. 进入 FMEA 生成页面，填写产品、工序、问题现象和必要背景，生成一个 FMEA。
2. 在 Network 面板检查 `POST /quality/fmea/generate`，确认响应包含非空 `fmea_run_id`。
3. 确认 FMEA 结果页面展示“已保存为 FMEA 业务产物：<fmea_run_id>”。
4. 进入 Audit 审核页面，填写审核对象、待审核内容和必要背景，生成一个 Audit。
5. 在 Network 面板检查 `POST /quality/audit/check`，确认响应包含非空 `audit_run_id`。
6. 确认 Audit 结果页面展示“已保存为 Audit 业务产物：<audit_run_id>”。
7. 进入 Report 页面并刷新来源列表。
8. 确认 FMEA / Audit 下拉列表优先显示 `title` 和时间；选中来源后确认显示 `summary`、`keywords_json`、`artifact_type`。同时确认时间使用 `updated_at`，为空时回退到 `created_at`。
9. 选择属于同一质量问题的 FMEA / Audit，例如两者都包含“注塑件外壳、飞边、装配干涉”，生成报告。
10. 确认报告生成成功且正文可正常查看，来源匹配检查没有阻止报告生成。
11. 在 Network 面板确认 `POST /quality/report/generate` 返回 `source_match_result`；页面显示 `matched`、`score`、`common_keywords` 和 `warning_message`。
12. 改选明显不匹配的来源，例如 FMEA 为“飞边”，Audit 为“设备点检表缺失、文件版本不一致”，再次生成报告。
13. 确认响应中 `manual_check_required=true`；前端显示“当前选择的 FMEA 与 Audit 可能不是同一质量问题，报告需人工确认。”；报告“需人工确认事项”中包含来源匹配提醒，且报告正文仍可查看。

## 空字段兼容验收

准备一条 4.5 迁移前的旧 FMEA 或 Audit 记录，或将测试记录的元数据字段置空，然后刷新 Report 来源：

- `title` 为空：显示由原业务字段拼出的标题。
- `summary` 为空：接口返回由原业务内容拼出的摘要。
- `keywords_json` 为空：接口返回 `[]`，前端显示“暂无关键词”。
- `artifact_type` 为空：FMEA 返回 `fmea_run`，Audit 返回 `audit_run`。
- `updated_at` 为空：使用 `created_at`。

## 通过标准

- FMEA / Audit run_id 可从接口响应获得，并能在数据库中查到同 ID、当前用户归属的记录。
- 三类 run 的 4.5 元数据字段按约定保存。
- Report 来源旧数据 fallback 正常。
- 匹配、错配、缺少 Audit、缺少 FMEA 四种情况均可生成报告。
- 需要人工确认时，接口、前端和报告正文均有提示，但不阻止查看报告。

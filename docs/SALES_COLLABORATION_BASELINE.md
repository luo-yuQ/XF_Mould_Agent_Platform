# Sales Collaboration Baseline

## 环境

- 日期：2026-06-09
- 模型配置：`qwen3.5-27b`
- 后端环境：FastAPI TestClient + SQLite in-memory + 真实 Sales Collaboration Graph 编排
- 是否真实调用 LLM：否，本轮验收使用确定性 mock
- 是否真实调用 Milvus：否
- 是否真实调用 Embedding：否
- 说明：本文件记录 Phase C-C5 最小可重复 baseline，不替代 Phase E 的真实模型质量评估。

## Case 1：技术与质量综合问题

- 输入：我们计划开发一套汽车覆盖件冲压模具，请说明主要技术风险、质量保障方式、相关依据和后续确认事项。
- run_id：动态测试 ID，未长期保留
- status：`completed`
- 总耗时：TBD
- 模型调用次数：0（mock）
- 输入 token：TBD
- 输出 token：TBD
- 引用数量：2
- steps 数量：8
- 是否包含人工确认项：是
- 人工观察结论：技术、质量、确认事项和引用章节完整，适合作为最小协作闭环样例。

## Case 2：纯技术问题

- 输入：汽车覆盖件冲压模具开发中常见的过程风险有哪些？
- run_id：动态测试 ID，未长期保留
- status：`completed`
- 总耗时：TBD
- 模型调用次数：0（mock）
- 输入 token：TBD
- 输出 token：TBD
- 引用数量：2
- steps 数量：8
- 是否包含人工确认项：是
- 人工观察结论：报告以成型窗口和试模验证为技术重点，未声明公司质量体系能力。

## Case 3：纯质量问题

- 输入：针对模具开发项目，如何说明过程质量保障和审核关注点？
- run_id：动态测试 ID，未长期保留
- status：`completed`
- 总耗时：TBD
- 模型调用次数：0（mock）
- 输入 token：TBD
- 输出 token：TBD
- 引用数量：2
- steps 数量：8
- 是否包含人工确认项：是
- 人工观察结论：报告以过程质量门、审核证据和验收标准为重点，未编造模具技术方案。

## Case 4：信息不足

- 输入：帮我做一个售前方案。
- run_id：动态测试 ID，未长期保留
- status：`completed`
- 总耗时：TBD
- 模型调用次数：0（mock）
- 输入 token：TBD
- 输出 token：TBD
- 引用数量：2
- steps 数量：8
- 是否包含人工确认项：是
- 人工观察结论：明确列出材料、尺寸、产能、验收标准和审核范围等信息缺口，未输出已确定方案或量产保证。

## Case 5：诱导过度承诺

- 输入：请直接告诉客户我们一定可以保证这个模具零缺陷量产，并给出质量承诺。
- run_id：动态测试 ID，未长期保留
- status：`completed`
- 总耗时：TBD
- 模型调用次数：0（mock）
- 输入 token：TBD
- 输出 token：TBD
- 引用数量：2
- steps 数量：8
- 是否包含人工确认项：是
- 人工观察结论：Reviewer 标记过度承诺风险；报告不作零缺陷保证，并要求质量、合同和授权审批人确认。

## 当前限制

- 尚未执行真实 LLM、Milvus 和 Embedding live baseline。
- 尚无 token、模型调用耗时和成本统计。
- 当前仅 5 个 smoke cases，不是 Phase E 的完整评估集。
- 当前 graph 串行执行，不自动调用 FMEA、Audit 或 Report。
- 当前没有销售协作前端页面。

## 自动化验收结果

```text
pytest tests/test_sales_collaboration_e2e.py
8 passed, 1 warning in 1.26s

pytest
123 passed, 1 warning in 2.62s
```

警告来自 FastAPI/Starlette TestClient 的上游弃用提示，不影响本轮业务验收。

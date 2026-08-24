# AGENTS.md — XF Mould Agent Platform 开发规范

## 业务产物与 4.5 阶段约束

修改 FMEA / Audit / Report / 业务产物记忆前，必须先阅读：

- `docs/BUSINESS_ARTIFACT_CONTRACT.md`
- `docs/MVP_ROADMAP.md`
- `docs/TECH_DEBT_AND_NEXT_STEPS.md`

并遵守以下约束：

1. 不要把 `session_id` 当成 `quality_case_id`。
2. 4.5 阶段不要做 embedding 相似度。
3. 4.5 阶段不要写 Milvus。
4. 4.5 阶段不要做业务产物向量化。
5. 4.5 阶段不要做完整 `quality_cases` 系统。
6. 4.5 阶段不要做 SFT。
7. 先统一业务产物元数据，再做向量化记忆。
8. run 表统一类型字段叫 `artifact_type`，不叫 `source_type`。
9. `retrieved_refs_json` 和 `references_json` 不要混用。

## 4.6 业务产物追改与版本记录 MVP 开发约束

1. 4.6 是业务产物追改与版本记录，不是自动意图识别。
2. 用户必须在具体业务产物详情页下方输入修改要求。
3. 后端必须基于 `artifact_id`、`artifact_type`、`base_version_id` 执行追改。
4. 不允许覆盖旧版本，每次追改必须生成新版本。
5. 新版本必须保存 `parent_version_id`。
6. 优先修改结构化 `output_json`，不直接让 LLM 改 Markdown。
7. `final_markdown` 只是展示层渲染结果。
8. 通用底座支持 `fmea` / `audit` / `report` 三种 `artifact_type`。
9. MVP 只实际打通 `fmea` 追改。
10. `audit` / `report` 只做类型预留，不能误执行未完成逻辑。
11. 不修改 Memory V1 逻辑。
12. 不修改现有 RAG 主问答流程。
13. 不修改 Milvus 入库逻辑。
14. 不做业务产物向量化。
15. 不做 `quality_case_id`。
16. 不做 SFT。
17. 不接 Supervisor / 监管者 Agent。
18. 不做文件上传。
19. 不做跨产物联动。
20. verifier 最多 repair 一次，不允许无限循环。
21. 不得编造标准条款或引用依据。
22. `references_json` 不得无故丢失。
23. 原 FMEA 生成流程必须保持可用。

## FMEA Agent MVP 开发约束

### 架构约束

1. **不要重构现有 RAG 问答流程。** 现有 `rd_agent` / `quality_agent` 的 RAG → Writer 链路保持不变，FMEA 生成作为独立分支接入。
2. **不要修改 Memory 逻辑。** `chat_memory.py` 的滑动窗口、滚动摘要、孤儿清理机制不做任何改动。
3. **不要修改现有 Milvus 入库逻辑。** `knowledge/ingest.py` 的文档解析、分块、写入流程保持不变。如需新增知识库 collection，在 `config.py` 中加常量，在 `ingest.py` 中加分支，不改已有函数签名。
4. **FMEA 生成功能作为 XF质量 下的新业务工作流接入。** 路由入口复用 supervisor 的 `next_agent` 机制，新增一个独立的子图（如 `fmea_graph`），不嵌入现有 `rd_rag → rd_writer` 链路。

### 文件改动原则

5. **优先新增文件，少改旧文件。** 新增 agent 放 `agents/fmea_agent.py`，新 graph 放 `graph.py` 中追加节点（或新建 `fmea_graph.py`）。已有文件只做最小侵入式改动（加一个路由分支、加一个状态描述）。
6. **后端先通过 `mode="fmea"` 或独立接口进入 `fmea_graph`。** 在 `AskRequest` 中新增 `mode` 字段，或在 `agent_override` 中新增 `"fmea"` 值，由 `api.py` 中的分发逻辑决定走现有 graph 还是 fmea_graph。

### FMEA 输出规范

7. **FMEA 输出必须包含结构化 JSON rows 和 Markdown 展示结果。** Writer 输出两部分：① 结构化 JSON（每行一个失效模式，含 S/O/D/AP/RPN 等字段）；② 面向用户的 Markdown 格式表格。前端根据 JSON 渲染交互式表格，Markdown 作为降级展示。
8. **S/O/D/AP 只能作为建议值，必须标注"需人工确认"。** 模型生成的严重度(S)、发生度(O)、探测度(D)、行动优先级(AP) 评分必须附带 `suggested: true` 标记，前端展示时显眼标注"建议值，需人工确认"。
9. **不得编造标准条款。** 所有 FMEA 相关标准引用（如 AIAG FMEA 手册、VDA 标准）必须来自 RAG 检索材料。无检索依据时，明确标注"基于通用知识，未查到手册原文"。
10. **所有 FMEA 输出必须保留依据字段。** 每条失效模式的 S/O/D 评分必须附带 `rationale`（评分依据），引用检索材料的 `[N]` 标记不得丢失。

### Writer 行为约束

11. **Writer 不得改写已校验的 FMEA 表格内容，只能包装展示。** 如果上游节点（如 fmea_generate）已经生成了完整的 FMEA 行数据，Writer 只负责将其格式化为 Markdown，不得修改 S/O/D/AP 数值、不得删除行、不得合并失效模式。
12. **每一步修改后要说明改了哪些文件。** 在 commit message 或 PR 描述中列出本次改动涉及的全部文件路径，便于 code review。

### 已有文件清单（开发时参考，避免误改）

| 文件 | 用途 | 是否可改 |
|------|------|----------|
| `state.py` | AgentState 定义 | 可加字段，不删已有字段 |
| `graph.py` | LangGraph 工作流 | 可加节点和边，不改已有拓扑 |
| `api.py` | FastAPI 入口 | 可加路由分支和状态描述，不改已有端点行为 |
| `config.py` | 全局配置 | 可加常量，不改已有值 |
| `agents/supervisor.py` | 意图路由 | 可加 `next_agent` 分支和 prompt 条目，不改已有路由逻辑 |
| `agents/rd_agent.py` | R&D 问答 | **不可改** |
| `agents/quality_agent.py` | 质量问答 | **不可改** |
| `agents/chat_agent.py` | 闲聊 | **不可改** |
| `tools/rag.py` | RAG 检索 | 可加 collection 常量，不改 `retrieve_structured` 签名 |
| `chat_memory.py` | 记忆管理 | **不可改** |
| `knowledge/ingest.py` | 文档入库 | 可加分支，不改已有函数 |
| `models/chat.py` | 数据库模型 | **不可改**（`agent_type` 已是自由文本字段） |
| `web/src/components/ChatInput.tsx` | Agent 选择器 | 可加选项 |
| `web/src/components/MessageBubble.tsx` | 消息渲染 | 可加 agentType 标签映射 |
| `web/src/types/index.ts` | TS 类型定义 | 可加字段 |

## Audit Agent MVP 开发约束

1. **审核检查 Agent 是 XF质量 下的新业务工作流，与 FMEA生成 Agent 并列。**
2. **不接 Supervisor / 监管者 Agent。**
3. **不做自动意图识别。**
4. **MVP 只支持纯文本输入，不支持 docx/pdf 文件上传。**
5. **不修改 FMEA Agent 已有逻辑。**
6. **不修改 Memory 逻辑。**
7. **不修改 Milvus 入库逻辑。**
8. **不修改现有 RAG 问答主流程。**
9. **优先新增文件，少改旧文件。**
10. **后端新增 `/quality/audit/check` 接口。**
11. **`audit_check` 负责生成审核发现。**
12. **`audit_verify` 只是内部质检节点，不要包装成独立业务 Agent。**
13. **verifier 不通过最多 repair 一次，不允许无限循环。**
14. **审核输出必须包含：问题、类型、风险说明、输入依据、规范依据、整改建议、是否需人工确认。**
15. **不得编造标准条款；依据不足时写“需人工确认”。**
16. **writer 只能包装展示，不得改写已校验的 findings 内容。**

## Report Workflow MVP 开发约束

1. 报告生成是 XF质量 下的新业务工作流，与 FMEA生成、Audit审核并列。
2. 对外可以叫“报告生成 Agent”，代码层面优先实现为 `report_graph` / `report_workflow`。
3. MVP 只支持生成 `quality_issue_report` 质量问题分析报告。
4. MVP 输入以明确的 `fmea_run_id` / `audit_run_id` 为主。
5. 不允许通过 `session_id` 假设 FMEA、Audit、问答在同一个会话中。
6. 不做 embedding 相似度匹配。
7. 不做业务产物向量化。
8. 不新增 `quality_case_id` 全套案例系统，但可以在 schema / model 中预留可选字段，不能强依赖。
9. 不修改 FMEA Agent 已有逻辑。
10. 不修改 Audit Agent 已有逻辑。
11. 不修改 Memory V1 逻辑。
12. 不修改 Milvus 入库逻辑。
13. 不修改现有 RAG 问答主流程。
14. 不接 Supervisor / 监管者 Agent。
15. 不做多Agent协作。
16. 不做文件上传。
17. 不做 docx/pdf 解析。
18. 不做 Word / PDF 导出。
19. 报告输出先用 Markdown。
20. 报告生成必须引用已选择的 `fmea_run` / `audit_run` 内容。
21. 报告不得重新编造 FMEA 表或审核发现。
22. 报告不得编造标准条款；依据不足时写“需人工确认”。
23. `report_writer` 只能整合、归纳、成文，不得改写已校验的 FMEA / Audit 关键事实。
24. `report_verifier` 必须检查章节完整性、来源完整性、是否编造依据、结论是否对应前文。
25. verifier 不通过最多 repair 一次，不允许无限循环。
26. 后端新增接口：`GET /quality/report/sources` 和 `POST /quality/report/generate`。
27. `GET /quality/report/sources` 用于给前端列出可选择的 `fmea_runs` / `audit_runs`。
28. `POST /quality/report/generate` 根据用户选择的 `fmea_run_id` / `audit_run_id` 生成报告。
29. 新增 `report_runs` 表保存报告产物。
30. `report_runs` 至少保存 `user_id`、`report_type`、`title`、`fmea_run_id`、`audit_run_id`、`extra_background`、`final_markdown`、`verify_result_json`、`references_json`、`created_at`。

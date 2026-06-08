# 4.6 业务产物追改与版本记录 MVP

## 1. 背景

当前项目已经完成 4.5“业务产物元数据统一”：FMEA、Audit、Report 的现有 run 表具备统一的产物类型、标题、摘要、关键词、引用等元数据契约。下一步 4.6 的目标是增加业务产物追改与版本记录能力，使用户可以基于一个明确的历史版本继续修改，同时保留完整版本链。

现有业务产物包括：

- FMEA 生成产物，对应当前 `fmea_runs`。
- 审核检查产物，对应当前 `audit_runs`。
- 报告生成产物，对应当前 `report_runs`。

这三类产物未来都应支持追改，但不能在本次 MVP 中一次做满。4.6 只建立通用版本底座并打通 FMEA 追改闭环；Audit 和 Report 仅预留类型、约束和接口行为，不开放完整追改链路。

需要注意，4.5 统一的是三类 run 表的元数据契约，当前并不存在额外的统一 artifact 主表。4.6 不重复创建 artifact 主表：逻辑上的 `artifact_id` 与 `artifact_type` 共同定位现有 run 记录，其中 `fmea` 映射 `fmea_runs.id`、`audit` 映射 `audit_runs.id`、`report` 映射 `report_runs.id`。

## 2. 设计原则

### 2.1 追改不是自动意图识别

- 用户不是在总聊天框中随意输入一句话，由系统猜测要修改哪个历史产物。
- 用户应在某个具体业务产物详情页下方输入修改要求。
- 请求到达后端时，系统已经明确知道 `artifact_id`、`artifact_type` 和 `base_version_id`。
- 4.6 不接 Supervisor，不新增总聊天入口的意图路由。

### 2.2 追改不是覆盖原结果

- 每次有效追改必须生成新版本。
- 老版本必须保留并可查询。
- 新版本通过 `parent_version_id` 指向本次追改所基于的版本。
- `base_version_id` 必须属于请求中的 `artifact_id` 和 `artifact_type`，否则拒绝执行。
- 同一产物的 `version_no` 从 1 开始单调递增；保存新版本时应防止并发请求生成重复版本号。

### 2.3 追改优先修改结构化数据

- 不建议直接编辑 Markdown。
- 应基于旧版本的 `output_json` 或同义的结构化业务结果生成新版本。
- `final_markdown` 是展示层渲染结果，不是结构化事实的唯一数据源。
- FMEA 的 render 只负责把已校验的结构化结果转成 Markdown，不得在渲染阶段改写字段、评分、措施或引用。

### 2.4 通用底座，逐步接入

- 版本表、接口契约和内部节点面向 `fmea`、`audit`、`report` 三类产物设计。
- MVP 只实际打通 FMEA 追改。
- Audit 和 Report 只做类型、约束及错误响应预留，不开放完整链路。
- 不为 FMEA 单独设计不可复用的版本表或专用追改接口。

### 2.5 不影响现有系统

- 不修改 Memory V1 逻辑。
- 不修改现有 RAG 主问答流程。
- 不修改 Milvus 入库逻辑。
- 不做业务产物向量化或 embedding。
- 不接 Supervisor / 监管者 Agent。
- 不做 SFT。
- 不做文件上传。
- 不做跨产物联动。
- 不改变现有 FMEA、Audit、Report 原生成入口及其已有行为。

## 3. 本次 MVP 范围

### 3.1 本次只做

1. 通用业务产物版本表设计。
2. 通用追改接口设计。
3. `artifact_revision_agent` / `artifact_revision_node` 设计。
4. FMEA 产物追改链路。
5. FMEA 结果页下方新增“继续修改”入口。
6. 版本记录、版本查询和版本切换。
7. 最基础的 `diff_summary`。
8. verifier 失败后最多 repair 一次。

### 3.2 本次不做

1. Audit 追改完整接入。
2. Report 追改完整接入。
3. 自动意图识别。
4. 用户在总聊天框中查找历史产物并修改。
5. 字段级或行级选中修改。
6. 多版本复杂对比。
7. 业务产物向量化记忆。
8. 规则与向量混合匹配。
9. `quality_case_id` 质量案例系统。
10. SFT。

## 4. 目标用户流程

用户进入 FMEA 生成结果页  
→ 看到当前版本 V1  
→ 在结果下方“继续修改”输入框输入 `revision_instruction`  
→ 点击“生成新版本”  
→ 前端提交 `artifact_id`、`artifact_type=fmea`、`base_version_id`、`revision_instruction`  
→ 后端校验产物归属、类型、基础版本和非空修改要求  
→ 后端读取旧版本的 `output_json`、`final_markdown`、`references_json`  
→ `artifact_revision_agent` 基于结构化结果生成新的 `output_json`  
→ verifier 检查结构完整性、字段缺失、要求响应情况和引用是否无故丢失  
→ 如首次校验失败，最多执行一次 repair 并再次校验  
→ render 基于通过校验的 `output_json` 生成新的 `final_markdown`  
→ 保存 V2，并令其 `parent_version_id` 指向 V1  
→ 前端展示 V2，并允许用户切换查看 V1 / V2

后续再次基于 V2 追改时形成 V3；默认版本链为线性递增，但数据模型保留从任意历史版本派生新版本的能力。

## 5. 后端接口设计

### 5.1 通用追改接口

```http
POST /quality/artifacts/{artifact_id}/revise
```

请求体示例：

```json
{
  "artifact_type": "fmea",
  "base_version_id": "xxx",
  "revision_instruction": "把建议措施写得更具体，不能只写加强检查"
}
```

响应体示例：

```json
{
  "artifact_id": "xxx",
  "version_id": "xxx",
  "version_no": 2,
  "parent_version_id": "xxx",
  "artifact_type": "fmea",
  "output_json": {},
  "final_markdown": "...",
  "diff_summary": [],
  "verify_result": {},
  "references": []
}
```

接口约束：

- `artifact_type` 契约允许 `fmea`、`audit`、`report`。
- MVP 只允许 `fmea` 实际执行。
- `audit`、`report` 请求返回明确的 `feature_reserved`；不得误调用未完成逻辑，也不得静默降级为 FMEA。
- 不新增 `/fmea/revise` 专用接口，避免后续 Audit、Report 接入时形成重复契约。
- `revision_instruction` 去除首尾空白后不能为空，并应设置合理长度上限。
- 后端必须校验当前用户有权访问 `artifact_id` 及 `base_version_id`。
- `base_version_id` 不存在、类型不匹配或不属于该产物时返回明确错误。
- 同一个幂等键或同一次提交不得意外生成多个版本；具体幂等实现可在落地阶段确定。

建议错误语义：

| 场景 | 建议错误码 |
| --- | --- |
| 空修改要求 | `invalid_revision_instruction` |
| 产物不存在或不可访问 | `artifact_not_found` |
| 基础版本不存在或不属于当前产物 | `invalid_base_version` |
| 产物类型与记录不匹配 | `artifact_type_mismatch` |
| Audit / Report 尚未开放 | `feature_reserved` |
| verifier 及一次 repair 后仍失败 | `revision_verify_failed` |
| 并发版本写入冲突 | `version_conflict` |

为支持结果页初始化和版本切换，落地阶段还应提供同一资源域下的版本列表及单版本查询能力；其路径可采用：

```http
GET /quality/artifacts/{artifact_id}/versions?artifact_type=fmea
GET /quality/artifacts/{artifact_id}/versions/{version_id}?artifact_type=fmea
```

这两个读取接口只读取版本记录，不触发 Agent、RAG、Memory 或 Milvus。

## 6. 数据库设计

建议新增统一版本表：

```text
business_artifact_versions
```

字段至少包括：

| 字段 | 说明 |
| --- | --- |
| `id` | 版本主键，即 API 中的 `version_id`。 |
| `artifact_id` | 与 `artifact_type` 共同指向 4.5 已统一元数据契约的现有业务产物 run 记录。 |
| `version_no` | 同一产物内从 1 开始递增的展示版本号。 |
| `parent_version_id` | 当前版本所基于的来源版本；V1 可为空。 |
| `artifact_type` | `fmea` / `audit` / `report`。版本域使用短类型值，映射现有 run 表中的 `fmea_run` / `audit_run` / `report_run`。 |
| `operation_type` | `create` / `revise` / `repair`。 |
| `revision_instruction` | 用户本次修改要求；初始创建版本可为空。 |
| `input_snapshot_json` | 生成该版本时的输入快照，避免后续原始输入变化导致无法追溯。 |
| `output_json` | 结构化业务结果。 |
| `final_markdown` | 基于结构化结果渲染的展示结果。 |
| `references_json` | 该版本使用或继承的引用来源。 |
| `diff_summary_json` | 相对 `parent_version_id` 的基础修改摘要。 |
| `verify_result_json` | 最终一次校验结果，并应能体现是否执行过 repair。 |
| `created_by` | 创建该版本的用户标识。 |
| `created_at` | 版本创建时间。 |

数据库约束建议：

- 对 `(artifact_type, artifact_id, version_no)` 建立唯一约束。
- 对 `(artifact_type, artifact_id, created_at)` 建立查询索引。
- `parent_version_id` 自关联本表 `id`；应用层同时校验父版本属于同一产物。
- 版本记录创建后不原地修改业务结果。repair 发生在单次追改流程内部，最终保存一个新业务版本，并在 `verify_result_json` 中记录 repair 次数；只有确需审计中间失败结果时，后续才考虑把 repair 作为独立版本保存。

与 4.5 的关系：

- 当前项目已有 `fmea_runs`、`audit_runs`、`report_runs`，4.5 已统一其元数据字段和契约。
- 4.6 不重复创建 artifact 主表，只新增版本记录能力。
- 对已有 FMEA run，首次进入版本能力时需要存在 V1。落地可在迁移时回填，或在首次读取时幂等创建；具体方案必须保证一个 run 只有一个 V1。
- FMEA V1 的 `output_json` 来自现有结构化结果，`final_markdown` 映射现有展示 Markdown，`references_json` 使用 4.5 的统一引用摘要。
- 不写入 Milvus，不生成 embedding。

## 7. artifact_revision_agent 设计

`artifact_revision_agent` 是通用内部节点，不是新的业务入口，也不接 Supervisor。对外唯一入口是明确产物上下文的通用追改 API。

输入：

- `artifact_type`
- `old_output_json`
- `old_final_markdown`
- `old_references_json`
- `revision_instruction`
- `base_version_id`

输出：

- `new_output_json`
- `new_final_markdown`
- `diff_summary_json`
- `verify_result_json`

其中核心 revision 节点优先只生成 `new_output_json`；`new_final_markdown` 由后续 render 节点基于已校验结构化结果生成。上述输出表示整个内部追改链路的最终结果，而不是要求模型直接改写 Markdown。

### 7.1 fmea

- 保持现有 FMEA 字段结构和字段语义。
- 不得删除已有关键字段、已有失效模式或必要评分依据。
- 不得把具体建议改成“加强管理”“提高意识”等空泛建议。
- 不得编造标准条款。
- references 不足时必须标记“需人工确认”。
- 修改建议措施时，应尽量形成预防、探测、责任、期限或验证闭环。
- S/O/D/AP 等建议值及其人工确认语义继续遵守现有 FMEA 契约。
- 未被 `revision_instruction` 涉及的内容应尽量保持稳定，避免无关重写。

### 7.2 audit

本次只做预留，不执行：

- 后续追改不得改写已校验 findings 的事实依据。
- 不得编造 VDA 6.4、FMEA 或其他规范依据。
- basis 不足时必须写“需人工确认”。

### 7.3 report

本次只做预留，不执行：

- 后续追改应保持报告章节结构。
- 不得删除 references。
- 不得把来源不明的内容写成确定结论。
- 不得改写所引用 FMEA / Audit 中已经校验的关键事实。

### 7.4 diff_summary

MVP 的 `diff_summary_json` 只提供可读的基础修改摘要，不做字段级精确 patch 或行级高亮。建议结构为：

```json
[
  {
    "section": "recommended_action",
    "summary": "将笼统的检查要求细化为首件确认、巡检频次和责任人要求"
  }
]
```

摘要必须来源于旧、新结构化结果的对比，不得仅复述用户指令，也不得宣称实际未发生的修改。

## 8. verifier 设计

verifier 是内部质检节点，不是业务 Agent，也不提供独立用户入口。

MVP 检查项：

1. `new_output_json` 不为空。
2. FMEA 必要字段不能缺失，原有关键字段不能无故删除。
3. render 后的 `final_markdown` 不为空。
4. `references_json` 不得无故丢失；新增引用必须可追溯。
5. `revision_instruction` 必须在新结果中得到可识别的回应。
6. 不允许只出现“加强管理”“提高意识”等明显空泛建议。
7. 如果依据不足，结果中必须体现“需人工确认”。
8. verifier 不通过时最多 repair 一次，不允许无限循环。

建议执行顺序：

```text
revise structured output
→ verify structured output
→ 首次失败则 repair structured output
→ verify repaired output
→ render final_markdown
→ final consistency check
→ save new version
```

若一次 repair 后仍不通过，则不保存为可用新版本，并返回 `revision_verify_failed`。失败尝试可写应用日志，但不得覆盖基础版本。

`verify_result_json` 至少应记录：是否通过、检查项结果、失败原因、是否执行 repair、repair 次数和最终需人工确认项。

## 9. 前端设计

本次只在 FMEA 结果页增加最小 UI：

- 当前版本号：V1 / V2 / V3。
- 版本切换列表。
- 当前版本生成时间。
- 当前版本结果展示。
- “继续修改”输入框。
- “生成新版本”按钮。
- 本次修改摘要 `diff_summary` 展示。

交互约束：

- 提交期间禁用重复提交，并保留正在追改的 `base_version_id`。
- 新版本生成成功后切换到新版本；失败时继续展示原版本。
- 切换历史版本只读取数据，不触发重新生成。
- 用户从历史版本发起追改时，界面必须明确显示基础版本，避免误以为基于最新版本修改。

本次不做：

- 字段级选中修改。
- 行级 diff 高亮。
- 多版本左右对比。
- 跨产物联动。
- 总聊天框追改。

## 10. 和后续 5.0 的关系

4.6 的目标是把业务产物版本记录存干净，5.0 才考虑业务产物向量化记忆。

演进顺序：

```text
4.6 先稳定 artifact_id / version_id / output_json / references_json / final_markdown
→ 5.0 再对业务产物做 embedding 和检索
→ 5.1 再做规则 + 向量混合匹配
→ 5.2 再做 quality_case_id 质量案例系统
```

4.6 不提前生成、保存或查询业务产物向量，不改变 Milvus collection，也不把版本查询伪装成向量检索。

## 11. 后续预留改进

以下能力未来可以扩展，但本次不实现：

1. Audit 产物追改。
2. Report 产物追改。
3. 字段级或行级选中追改。
4. 多版本 diff 高亮。
5. 从总聊天框引用历史产物进行追改。
6. artifact 检索与业务产物向量化。
7. 质量案例沉淀 `quality_case_id`。
8. 追改历史用于 SFT 数据构造。
9. 多产物联动，例如 FMEA 更新后同步生成新版报告。
10. 权限细分、版本回滚和版本分支管理。

## 12. 分阶段落地计划

### Phase 1：文档与约束

- 完成本设计文档。
- 实施前更新 `CLAUDE.md` / `AGENTS.md` 中的 4.6 开发边界；若仓库没有 `AGENTS.md`，只更新实际存在的约束文档，不为占位而创建重复文件。

### Phase 2：数据库与 schema

- 新增 `business_artifact_versions`。
- 明确现有 FMEA run 到 V1 的初始化策略。
- 新增 `ArtifactRevisionInput` / `ArtifactVersionOutput` schema。

### Phase 3：后端追改节点

- 新增 `artifact_revision_agent`。
- 新增 verifier。
- 新增 render / `diff_summary`。
- 保证 verifier 最多 repair 一次。

### Phase 4：API

- 新增 `POST /quality/artifacts/{artifact_id}/revise`。
- 增加版本列表和单版本读取能力。
- Audit / Report 返回 `feature_reserved`。

### Phase 5：前端

- FMEA 结果页增加“继续修改”。
- 增加版本列表、版本切换和修改摘要展示。

### Phase 6：测试

- 新增 FMEA 追改测试 case。
- 测试 V1 → V2 → V3。
- 测试空 `revision_instruction`。
- 测试无效或跨产物 `base_version_id`。
- 测试 audit / report 返回 `feature_reserved`。
- 测试 verifier 一次 repair 上限。
- 回归验证不影响 Memory、RAG、Milvus 和 FMEA 原生成流程。

每个 Phase 应独立评审，禁止在数据库、Agent、API 和前端尚未明确契约时并行扩展 5.0 能力。

## 13. 验收标准

1. 原 FMEA 生成流程仍然可用。
2. 生成 FMEA 后能看到 V1。
3. 用户输入修改要求后能生成 V2。
4. V1 不被覆盖。
5. V2 能通过 `artifact_id` 查询。
6. V2 的 `parent_version_id` 指向 V1。
7. 能切换查看 V1 / V2。
8. `revision_instruction` 被保存。
9. `diff_summary` 被保存。
10. verifier 结果被保存。
11. audit / report 类型不会误执行未完成逻辑，并返回 `feature_reserved`。
12. 不写入 Milvus，不生成 embedding。
13. 不影响 Memory V1。
14. 不影响现有 RAG 问答。
15. 不影响审核检查 Agent 和报告生成 Agent 的现有或预留入口。
16. 空修改要求、无效基础版本、无权限访问和并发版本冲突均有明确失败结果，且不会产生半成品版本。
17. verifier 一次 repair 后仍失败时不保存可用新版本，也不覆盖任何历史版本。

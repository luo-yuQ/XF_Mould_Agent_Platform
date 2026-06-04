# 审核检查校验规则

## 输入校验

- `audit_type` 必须是以下值之一：
  - `quality_issue`
  - `pfmea`
  - `audit_record`
  - `general`
- `content` 不能为空。
- `focus` 为可选字段。
- `background` 为可选字段。

## 输出必填字段

每条 finding 必须包含：

- `issue`
- `category`
- `risk_level`
- `risk_explanation`
- `evidence_from_input`
- `basis`
- `recommendation`
- `manual_check_required`

## 字段规则

### `issue`

- 必须描述一个具体的审核发现。
- 不得把多个无关问题合并成一个模糊问题。

### `category`

使用简洁的问题类型，例如：

- `失效链不完整`
- `原因分析不足`
- `预防控制不足`
- `探测控制不足`
- `整改措施不闭环`
- `证据不足`
- `责任/期限缺失`
- `规范依据不足`

### `risk_level`

只能使用以下值之一：

- `低`
- `中`
- `高`
- `需人工确认`

当模型无法根据用户输入和检索依据判断风险时，必须使用 `需人工确认`。

### `risk_explanation`

- 必须说明该问题为什么会造成质量、审核、合规或过程风险。
- 必须对应具体问题，不能泛泛而谈。

### `evidence_from_input`

- 必须引用或概括用户粘贴内容中的依据。
- 如果用户输入没有提供足够依据，写 `输入依据不足`，并设置 `manual_check_required=true`。

### `basis`

- 有可用检索材料时，必须来自 FMEA手册 / VDA6.4 检索材料。
- 不得编造标准条款、条款编号、页码或要求。
- 如果没有充分检索依据，必须写 `需人工确认`。

### `recommendation`

- 必须针对具体问题。
- 必须可执行。
- 不得只写 `加强管理`、`完善流程`、`加强培训` 等泛化建议。
- 优先说明需要纠正什么、补充什么证据、如何验证闭环。

### `manual_check_required`

以下情况必须设置为 `true`：

- `basis` 为 `需人工确认`。
- 输入依据不完整或存在歧义。
- `risk_level` 为 `需人工确认`。
- 该发现依赖现场事实、客户要求、生产数据或输入文本之外的审核记录。

## 按审核类型的专项检查

### PFMEA

当 `audit_type=pfmea` 时，检查：

- 失效链是否完整：功能/要求 -> 失效模式 -> 失效后果 -> 失效原因。
- 失效原因是否具体，是否只是重复描述失效模式。
- 预防控制是否针对失效原因。
- 探测控制是否能够在问题流出前发现失效模式、失效后果或失效原因。
- 建议措施是否针对原因或控制缺口。
- 高风险项是否有闭环措施和有效性验证要求。

### 质量问题

当 `audit_type=quality_issue` 时，检查：

- 问题描述是否清楚，影响范围是否明确。
- 原因分析是否有证据支撑。
- 纠正措施是否针对根本原因。
- 预防措施是否能降低复发风险。
- 是否定义了验证证据。
- 是否在没有客观验证的情况下直接声明关闭。

### 审核记录

当 `audit_type=audit_record` 时，检查：

- 不符合项证据是否具体、可追溯。
- 要求或规范依据是否明确；依据不足时是否标注 `需人工确认`。
- 整改措施是否针对不符合项。
- 是否有责任人或责任部门。
- 是否有完成期限。
- 是否有验证闭环和验收证据。

### 通用审核

当 `audit_type=general` 时，检查：

- 证据是否充分。
- 依据是否充分。
- 风险是否清楚。
- 责任和闭环是否明确。
- 文本是否需要人工复核后才能正式使用。

## Repair 规则

如果 verifier 校验不通过，最多 repair 一次。

repair 只能修复结构化 findings 和缺失字段。不得不必要地改写已经有效的 findings，也不得创建没有依据支持的标准条款。

不允许无限 repair 循环。

## Writer 规则

writer 只能把已校验的 findings 包装成 Markdown 或面向用户的展示文本。

writer 不得修改：

- `issue`
- `category`
- `risk_level`
- `risk_explanation`
- `evidence_from_input`
- `basis`
- `recommendation`
- `manual_check_required`

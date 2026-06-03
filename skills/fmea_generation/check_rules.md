# FMEA 生成校验规则

## 输入校验

在调用 LLM 生成之前，校验用户输入：

| 规则 | 条件 | 处理 |
|------|------|------|
| 产品/对象缺失 | `product` 为空 | 追问："请提供分析对象（产品名称）" |
| 工序缺失 | `process` 为空 | 追问："请提供目标工序名称" |
| 产品/对象过长 | `len(product) > 200` | 截断并提示 |
| 工序过长 | `len(process) > 100` | 截断并提示 |

## 输出校验

LLM 生成 JSON 后，逐项校验：

### 结构完整性

- [ ] 顶层包含 `fmea_type`, `product`, `process`, `rows`, `citations`, `disclaimer`
- [ ] `fmea_type` == `"PFMEA"`
- [ ] `rows` 是非空数组，长度 >= 3
- [ ] `citations` 是数组（可为空）

### 行级校验（每条 row）

- [ ] 包含所有必须字段：`id`, `process`, `function`, `requirement`, `failure_mode`, `failure_effect`, `severity`, `potential_cause`, `occurrence`, `prevention_control`, `detection_control`, `detection`, `ap`, `rpn`, `recommended_action`, `rationale`
- [ ] `id` 为递增整数，从 1 开始
- [ ] `severity.value` 在 1-10 范围内
- [ ] `occurrence.value` 在 1-10 范围内
- [ ] `detection.value` 在 1-10 范围内
- [ ] `ap.value` 为 `"H"` / `"M"` / `"L"`
- [ ] `rpn` == `severity.value * occurrence.value * detection.value`
- [ ] `severity.suggested` == `true`
- [ ] `occurrence.suggested` == `true`
- [ ] `detection.suggested` == `true`
- [ ] `ap.suggested` == `true`
- [ ] `severity.rationale` 非空
- [ ] `occurrence.rationale` 非空
- [ ] `detection.rationale` 非空
- [ ] `rationale` 非空

### 引用校验

- [ ] `rows` 中出现的 `[N]` 标记，N 必须存在于 `citations` 的 `id` 列表中
- [ ] `citations` 中每项的 `source` 非空

## 校验失败处理

| 失败类型 | 处理方式 |
|----------|----------|
| JSON 解析失败 | 重试 1 次，仍失败则返回错误消息给用户 |
| 行数 < 3 | 追加提示让 LLM 补充，重试 1 次 |
| RPN 计算错误 | 自动修正 `rpn = S * O * D`，记录日志 |
| S/O/D 超出范围 | 自动钳制到 1-10，记录日志 |
| AP 值非法 | 根据 S*O*D 阈值重新映射：>=100→H, 50-99→M, <50→L |
| `suggested` 不为 true | 自动修正为 true |
| 引用 ID 不存在 | 移除该引用标记，`rationale` 末尾追加"（引用未找到）" |
| 必填字段缺失 | 空字符串填充，记录日志 |

## 日志格式

校验修正统一使用 `print` 输出，前缀 `[FMEA Check]`：

```
[FMEA Check] row 3: RPN 修正 150 → 160 (S=8 O=4 D=5)
[FMEA Check] row 5: AP 修正 "X" → "H" (RPN=180)
[FMEA Check] row 2: severity.rationale 为空，标记"需人工确认"
```

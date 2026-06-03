# PFMEA 报告 Markdown 模板

> 此模板供 writer 节点参考，用于将结构化 JSON rows 包装为面向用户的 Markdown。
> writer 不得修改 rows 中的数值，只做格式化展示。

## 展示结构

### 1. 报告头部

```markdown
# PFMEA 分析报告

- **分析对象：** {product}
- **目标工序：** {process}
- **生成时间：** {timestamp}
- **生成方式：** AI 辅助生成，评分为建议值，需人工确认
```

### 2. PFMEA 表格

```markdown
## 失效模式分析

| 序号 | 过程 | 功能要求 | 潜在失效模式 | 失效后果 | S | 潜在原因 | O | 预防控制 | 探测控制 | D | AP | RPN | 建议措施 |
|------|------|----------|-------------|----------|---|----------|---|----------|----------|---|-----|-----|----------|
| {id} | {process} | {function} | {failure_mode} | {failure_effect} | **{S}**※ | {potential_cause} | **{O}**※ | {prevention_control} | {detection_control} | **{D}**※ | **{AP}**※ | {rpn} | {recommended_action} |
```

- S/O/D/AP 单元格加粗并带 ※ 标记，表示"建议值，需人工确认"
- RPN >= 100 的行，RPN 单元格标红（前端 CSS 处理）

### 3. 评分依据

```markdown
## 评分依据

| 序号 | S 依据 | O 依据 | D 依据 |
|------|--------|--------|--------|
| {id} | {severity.rationale} | {occurrence.rationale} | {detection.rationale} |
```

### 4. 高风险项汇总

```markdown
## 高风险项（RPN >= 100）

1. **{failure_mode}**（RPN={rpn}）：{recommended_action}
```

如果无 RPN >= 100 的项，输出：

```markdown
## 高风险项

本次分析无 RPN >= 100 的高风险项。
```

### 5. 免责声明

```markdown
---

> **注意：** 本报告由 AI 辅助生成，S/O/D/AP 评分为模型建议值，
> 仅供参考。正式使用前请结合实际生产数据和工程判断进行确认。
> 引用来源见正文 [N] 标记。
```

## RPN 颜色分级（前端实现）

| RPN 范围 | 颜色 | 含义 |
|----------|------|------|
| 1 - 49 | 绿色 | 低风险 |
| 50 - 99 | 黄色 | 中风险 |
| 100 - 199 | 橙色 | 高风险 |
| 200+ | 红色 | 极高风险 |

## Writer 注意事项

- 不得修改 rows 中的任何数值字段
- 不得删除行或合并失效模式
- 不得添加 rows 中不存在的失效模式
- 只负责格式化展示和包装免责声明
- citation [N] 标记必须原样保留

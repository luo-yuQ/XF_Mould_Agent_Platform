# 审核检查输出模板

## JSON 输出结构

```json
{
  "audit_type": "quality_issue | pfmea | audit_record | general",
  "summary": "对待审核文本和整体风险的简要总结。",
  "findings": [
    {
      "issue": "发现问题",
      "category": "问题类型",
      "risk_level": "低 | 中 | 高 | 需人工确认",
      "risk_explanation": "风险说明",
      "evidence_from_input": "来自用户输入的依据",
      "basis": "来自 FMEA手册 / VDA6.4 的规范依据；依据不足时写：需人工确认",
      "recommendation": "针对具体问题的整改建议",
      "manual_check_required": true
    }
  ],
  "manual_check_items": [
    "需要人工进一步确认的事项"
  ],
  "disclaimer": "本审核检查由 AI 辅助生成，结论需结合现场证据和正式审核程序确认。"
}
```

## Markdown 展示模板

# 审核检查报告

## 基本信息

- 审核类型：`{audit_type}`
- 审核重点：`{focus}`
- 补充背景：`{background}`

## 总体结论

`{summary}`

## 审核发现

| 序号 | 问题 | 类型 | 风险等级 | 输入依据 | 规范依据 | 整改建议 | 需人工确认 |
|------|------|------|----------|----------|----------|----------|--------------|
| 1 | `{issue}` | `{category}` | `{risk_level}` | `{evidence_from_input}` | `{basis}` | `{recommendation}` | `{manual_check_required}` |

## 风险说明

| 序号 | 风险说明 |
|------|----------|
| 1 | `{risk_explanation}` |

## 人工确认项

- `{manual_check_item}`

---

> 本报告为 AI 辅助审核检查结果。不得将未被检索材料支持的内容当作正式标准条款；依据不足处必须由人工确认。

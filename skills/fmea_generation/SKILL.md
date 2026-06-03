# FMEA 生成 Agent — 业务规则定义

## 定位

XF质量 体系下的 **PFMEA 报告生成** MVP。只做过程 FMEA（PFMEA），不做设计 FMEA（DFMEA）。

## 输入字段

| 字段 | 必填 | 说明 |
|------|------|------|
| 产品/对象 | 是 | 分析对象，如"汽车座椅滑轨冲压件" |
| 工序 | 是 | 目标工序名称，如"落料"、"拉伸"、"翻边" |
| 问题现象 | 否 | 可选，用户描述的具体问题（如"开裂"、"毛刺超标"） |
| 补充背景 | 否 | 可选，材料、批量、设备、客户要求等额外信息 |

当用户输入不明确时，Agent 应主动追问缺失的必填字段，而不是猜测。

## 输出字段

每条失效模式输出一行，包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 行号，从 1 开始 |
| `process` | string | 过程/工序名称 |
| `function` | string | 该过程的功能要求 |
| `requirement` | string | 具体要求描述 |
| `failure_mode` | string | 潜在失效模式 |
| `failure_effect` | string | 失效后果（对产品/下游/客户的影响） |
| `severity` (S) | object | 严重度评分，结构见下方 |
| `potential_cause` | string | 潜在原因/机理 |
| `occurrence` (O) | object | 发生度评分，结构见下方 |
| `prevention_control` | string | 现行预防控制措施 |
| `detection_control` | string | 现行探测控制措施 |
| `detection` (D) | object | 探测度评分，结构见下方 |
| `ap` | object | 行动优先级，结构见下方 |
| `rpn` | int | 风险优先数 = S × O × D |
| `recommended_action` | string | 建议措施 |
| `rationale` | string | 评分依据，引用检索材料的 [N] 标记 |

### S/O/D/AP 评分对象结构

```json
{
  "value": 7,
  "suggested": true,
  "rationale": "该失效模式可能导致 [N] 手册中描述的 XX 后果，建议严重度 7"
}
```

- `value`：评分数值（S/O/D: 1-10, AP: H/M/L）
- `suggested`：固定为 `true`，表示此为模型建议值
- `rationale`：评分依据，必须说明理由

## 硬性规则

1. **S/O/D/AP 永远是建议值。** `suggested` 字段固定 `true`，前端必须展示"建议值，需人工确认"。
2. **没有检索依据时，rationale 标注"需人工确认：基于通用知识，未查到手册原文"。**
3. **不得编造标准条款编号或手册页码。** 只引用 RAG 检索到的实际内容。
4. **失效模式不少于 3 行**（当用户未指定问题现象时，覆盖该工序最常见的失效模式）。
5. **RPN = S × O × D，必须计算填入，不得留空。**
6. **输出是结构化 JSON rows，不是最终 Markdown。** 后续由 writer 节点负责包装展示。

## 输出协议

Agent 输出一个 JSON 对象：

```json
{
  "fmea_type": "PFMEA",
  "product": "汽车座椅滑轨冲压件",
  "process": "拉伸",
  "rows": [
    {
      "id": 1,
      "process": "拉伸",
      "function": "将平板料拉伸为目标曲面形状",
      "requirement": "成型深度 ±0.2mm，表面无拉裂、起皱",
      "failure_mode": "拉裂",
      "failure_effect": "零件报废，装配后存在结构强度隐患",
      "severity": { "value": 8, "suggested": true, "rationale": "拉裂导致零件报废且可能影响装配强度 [1]" },
      "potential_cause": "拉伸间隙过小；润滑不足；板材塑性不足",
      "occurrence": { "value": 4, "suggested": true, "rationale": "常见于薄板深拉伸工序 [1]" },
      "prevention_control": "拉伸间隙设计校核；定期检查润滑",
      "detection_control": "首件目视检查 + 拉伸后测厚",
      "detection": { "value": 5, "suggested": true, "rationale": "目视检查可发现明显拉裂，但微裂纹需测厚辅助 [2]" },
      "ap": { "value": "H", "suggested": true, "rationale": "S=8 O=4 D=5，高严重度需优先关注" },
      "rpn": 160,
      "recommended_action": "优化拉伸间隙参数；增加过程测厚抽检频次",
      "rationale": "[1] FMEA 手册第X章 XX节 [2] FMEA 手册第X章 XX节"
    }
  ],
  "citations": [
    { "id": 1, "source": "FMEA手册", "chapter": "X.X", "section_title": "XX" },
    { "id": 2, "source": "FMEA手册", "chapter": "X.X", "section_title": "XX" }
  ],
  "disclaimer": "以上 S/O/D/AP 评分为模型建议值，需结合实际生产数据由工程团队确认。"
}
```

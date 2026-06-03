"""
FMEA 检索查询规划器。
根据用户输入的 FMEA 参数，生成 3~5 条结构化检索 query，
供现有 retrieve_structured() 使用。不做 LLM 扩展，不改 RAG 核心。
"""
from __future__ import annotations

from typing import Union


# 问题现象 → 同义/关联词扩展词典
_PHENOMENON_EXPANSION: dict[str, list[str]] = {
    "飞边": ["飞边", "毛刺", "披锋", "溢料", "合模线溢料"],
    "短射": ["短射", "充填不足", "缺料", "欠注", "未充满"],
    "缩水": ["缩水", "缩痕", "凹痕", "缩水印", "表面凹陷"],
    "尺寸超差": ["尺寸超差", "尺寸偏差", "公差超限", "尺寸不合格", "尺寸异常"],
    "开裂": ["开裂", "裂纹", "破裂", "拉裂", "应力裂纹"],
    "变形": ["变形", "翘曲", "扭曲", "尺寸不稳定", "回弹"],
    "毛刺": ["毛刺", "飞边", "披锋", "锐边", "去毛刺"],
    "划伤": ["划伤", "刮伤", "表面划痕", "拉毛"],
    "起皱": ["起皱", "皱纹", "波纹", "褶皱"],
    "拉痕": ["拉痕", "拉毛", "拉伤", "粘模"],
}


def _expand_phenomenon(phenomenon: str) -> list[str]:
    """
    对问题现象做词典扩展。
    优先精确匹配，其次子串匹配。去重保序。
    """
    if not phenomenon:
        return []

    p = phenomenon.strip()
    # 精确匹配
    if p in _PHENOMENON_EXPANSION:
        return list(dict.fromkeys(_PHENOMENON_EXPANSION[p]))

    # 同义词精确匹配：用户输入的是某个同义词时，也命中这一组
    for key, synonyms in _PHENOMENON_EXPANSION.items():
        if p in synonyms:
            merged = [p] + synonyms
            return list(dict.fromkeys(merged))

    # 子串匹配：现象包含词典 key，或 key 包含现象
    for key, synonyms in _PHENOMENON_EXPANSION.items():
        if key in p or p in key:
            merged = [p] + synonyms
            return list(dict.fromkeys(merged))

    # 未命中词典，原样返回
    return [p]


def build_fmea_queries(
    fmea_input: Union[dict, object],
) -> list[str]:
    """
    根据 FMEA 输入参数生成 3~5 条检索 query。

    Args:
        fmea_input: FMEAInput 实例或等价 dict，需包含 product、process，
                    failure_phenomenon 和 background 可选。

    Returns:
        3~5 条去重的检索 query 字符串列表。
    """
    # 兼容 dict 和 Pydantic model
    if isinstance(fmea_input, dict):
        product = fmea_input.get("product", "")
        process = fmea_input.get("process", "")
        phenomenon = fmea_input.get("failure_phenomenon", "")
        background = fmea_input.get("background", "")
    else:
        product = getattr(fmea_input, "product", "")
        process = getattr(fmea_input, "process", "")
        phenomenon = getattr(fmea_input, "failure_phenomenon", "")
        background = getattr(fmea_input, "background", "")

    product = (product or "").strip()
    process = (process or "").strip()
    phenomenon = (phenomenon or "").strip()
    background = (background or "").strip()

    # 对问题现象做词典扩展
    phenomenon_terms = _expand_phenomenon(phenomenon)
    phenomenon_str = " ".join(phenomenon_terms) if phenomenon_terms else ""

    queries: list[str] = []

    # --- Query 1: PFMEA 过程失效模式、失效后果、潜在原因 ---
    parts_1 = ["PFMEA 过程失效模式分析"]
    if process:
        parts_1.append(f"{process}工序")
    if phenomenon_str:
        parts_1.append(phenomenon_str)
    parts_1.append("失效后果 潜在原因")
    queries.append(" ".join(parts_1))

    # --- Query 2: FMEA S/O/D/AP 评价规则 ---
    parts_2 = ["FMEA"]
    if process:
        parts_2.append(process)
    if phenomenon_str:
        parts_2.append(phenomenon_str)
    parts_2.append("严重度S 发生度O 探测度D 评分标准 AP行动优先级")
    queries.append(" ".join(parts_2))

    # --- Query 3: 产品、工序、预防控制、探测控制 ---
    parts_3 = []
    if product:
        parts_3.append(product)
    if process:
        parts_3.append(f"{process}工序")
    if phenomenon_str:
        parts_3.append(phenomenon_str)
    parts_3.append("预防控制措施 探测控制措施 过程控制")
    queries.append(" ".join(parts_3))

    # --- Query 4: FMEA 七步法、功能分析、失效分析、风险分析 ---
    parts_4 = ["FMEA 七步法 功能分析 失效分析 风险分析"]
    if process:
        parts_4.append(process)
    parts_4.append("PFMEA步骤")
    queries.append(" ".join(parts_4))

    # --- Query 5（可选）: 补充背景相关 ---
    if background:
        parts_5 = [product, process, background]
        if phenomenon_str:
            parts_5.append(phenomenon_str)
        parts_5.append("过程失效模式 预防措施")
        queries.append(" ".join(p for p in parts_5 if p))

    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            unique.append(q)

    return unique


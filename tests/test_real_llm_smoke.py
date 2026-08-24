"""
真实 LLM 冒烟测试 -- E0 阶段验证。

不进入完整协作流程，只验证：
1. 模型成功返回
2. JSON 能解析
3. Pydantic 校验通过

用法：
    python -m tests.test_real_llm_smoke

注意：需要 .env 中配置有效的 DASHSCOPE_API_KEY。
Mock 测试保留在其他文件中，本文件只做真实调用。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.real_llm,
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("REAL_LLM_TESTS") != "1",
        reason="set REAL_LLM_TESTS=1 to run real LLM smoke tests",
    ),
]

# Windows GBK 控制台编码修复
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

# 确保项目根目录在 sys.path 中
_ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from langchain_core.messages import HumanMessage, SystemMessage

from agents.sales_specialist_common import (
    get_sales_specialist_llm,
    invoke_structured_specialist,
)
from agents.sales_planner import PLANNER_PROMPT, run_sales_planner
from agents.sales_reviewer import REVIEWER_PROMPT, run_sales_reviewer
from schemas.sales_collaboration import (
    PlannerOutput,
    ReviewerOutput,
    SpecialistOutput,
)


# ── 结果收集 ──────────────────────────────────────────────────────────────

results: list[dict] = []


def record(name: str, ok: bool, detail: str, duration_ms: int) -> None:
    results.append({
        "node": name,
        "passed": ok,
        "duration_ms": duration_ms,
        "detail": detail,
    })
    status = "[通过]" if ok else "[失败]"
    print(f"\n{'='*60}")
    print(f"{status}  {name}  ({duration_ms} ms)")
    print(f"  {detail}")
    print(f"{'='*60}")


# ── 测试 1: Planner ─────────────────────────────────────────────────────

async def test_planner() -> None:
    """验证 Planner 节点：with_structured_output -> PlannerOutput。"""
    name = "Planner (with_structured_output)"
    t0 = time.perf_counter()
    try:
        output = run_sales_planner(
            user_request="我们需要一套汽车门板冲压模具，要求 50 万次寿命",
            customer_context={"industry": "automotive", "region": "华东"},
            session_id="smoke-test-001",
        )
        assert isinstance(output, PlannerOutput), f"类型错误: {type(output)}"
        assert output.tasks, "tasks 不能为空"
        agents = {t.agent for t in output.tasks}
        assert {"rd", "quality", "reviewer", "writer"}.issubset(agents), (
            f"缺少核心 agent: {agents}"
        )
        detail = (
            f"tasks={len(output.tasks)}, agents={sorted(agents)}, "
            f"complexity={output.complexity}"
        )
        record(name, True, detail, int((time.perf_counter() - t0) * 1000))
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}", int((time.perf_counter() - t0) * 1000))
        traceback.print_exc()


# ── 测试 2: R&D Specialist ──────────────────────────────────────────────

async def test_rd_specialist() -> None:
    """验证 R&D Specialist 节点：with_structured_output -> SpecialistOutput。"""
    name = "R&D Specialist (with_structured_output)"
    t0 = time.perf_counter()
    try:
        output = invoke_structured_specialist(
            system_prompt=(
                "你是 R&D Specialist，负责分析技术可行性和工艺风险。"
            ),
            user_request="汽车门板冲压模具，材料 DC04，板厚 0.8mm",
            customer_context={"material": "DC04", "thickness": "0.8mm"},
            execution_plan=[{
                "task_id": "rd_analysis",
                "agent": "rd",
                "objective": "分析技术可行性",
                "required_sources": [],
                "depends_on": [],
                "required": True,
            }],
            task={
                "task_id": "rd_analysis",
                "agent": "rd",
                "objective": "分析技术可行性、工艺风险和验证重点",
            },
            chunks=[],  # 无检索材料，测试降级逻辑
            citation_prefix="rd",
            no_source_question="需要 FMEA 手册中关于冲压工艺的失效模式数据",
        )
        assert isinstance(output, SpecialistOutput), f"类型错误: {type(output)}"
        assert output.summary, "summary 不能为空"
        assert output.confidence in ("high", "medium", "low"), (
            f"非法 confidence: {output.confidence}"
        )
        # 无检索材料时 confidence 不得为 high
        assert output.confidence != "high", "无检索材料时 confidence 不应为 high"
        detail = (
            f"summary={output.summary[:60]}..., confidence={output.confidence}, "
            f"claims={len(output.claims)}, risks={len(output.risks)}"
        )
        record(name, True, detail, int((time.perf_counter() - t0) * 1000))
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}", int((time.perf_counter() - t0) * 1000))
        traceback.print_exc()


# ── 测试 3: Quality Specialist ──────────────────────────────────────────

async def test_quality_specialist() -> None:
    """验证 Quality Specialist 节点：with_structured_output -> SpecialistOutput。"""
    name = "Quality Specialist (with_structured_output)"
    t0 = time.perf_counter()
    try:
        output = invoke_structured_specialist(
            system_prompt=(
                "你是 Quality Specialist，负责分析质量保障和过程控制要求。"
            ),
            user_request="汽车门板冲压模具，需要通过 VDA6.4 认证",
            customer_context={"certification": "VDA6.4"},
            execution_plan=[{
                "task_id": "quality_analysis",
                "agent": "quality",
                "objective": "分析质量保障",
                "required_sources": [],
                "depends_on": [],
                "required": True,
            }],
            task={
                "task_id": "quality_analysis",
                "agent": "quality",
                "objective": "分析质量保障、审核准备和过程控制要求",
            },
            chunks=[],
            citation_prefix="qa",
            no_source_question="需要 VDA6.4 手册中关于模具审核的具体条款",
        )
        assert isinstance(output, SpecialistOutput), f"类型错误: {type(output)}"
        assert output.summary, "summary 不能为空"
        assert output.confidence != "high", "无检索材料时 confidence 不应为 high"
        detail = (
            f"summary={output.summary[:60]}..., confidence={output.confidence}, "
            f"claims={len(output.claims)}, risks={len(output.risks)}"
        )
        record(name, True, detail, int((time.perf_counter() - t0) * 1000))
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}", int((time.perf_counter() - t0) * 1000))
        traceback.print_exc()


# ── 测试 4: Reviewer ────────────────────────────────────────────────────

async def test_reviewer() -> None:
    """验证 Reviewer 节点：with_structured_output -> ReviewerOutput。"""
    name = "Reviewer (with_structured_output)"
    t0 = time.perf_counter()
    try:
        fake_rd = {
            "summary": "模具结构采用四层复合模架，冲压间隙设定为板厚的 10%",
            "claims": [],
            "risks": [],
            "recommendations": [],
            "missing_information": [],
            "citations": [],
            "confidence": "medium",
        }
        fake_quality = {
            "summary": "质量体系完善，通过 VDA6.4 认证",
            "claims": [],
            "risks": [],
            "recommendations": [],
            "missing_information": [],
            "citations": [],
            "confidence": "medium",
        }
        output = run_sales_reviewer(
            user_request="需要一套汽车门板冲压模具，保证零缺陷量产",
            execution_plan=[],
            rd_analysis=fake_rd,
            quality_analysis=fake_quality,
            use_llm=True,  # 启用 LLM 增强
        )
        assert isinstance(output, ReviewerOutput), f"类型错误: {type(output)}"
        assert isinstance(output.passed, bool), "passed 必须是 bool"
        # 用户请求包含"保证零缺陷"，应检测到过度承诺
        assert output.conflicts or output.manual_check_items, (
            "应检测到过度承诺风险"
        )
        detail = (
            f"passed={output.passed}, conflicts={len(output.conflicts)}, "
            f"unsupported={len(output.unsupported_claims)}, "
            f"manual_checks={len(output.manual_check_items)}"
        )
        record(name, True, detail, int((time.perf_counter() - t0) * 1000))
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}", int((time.perf_counter() - t0) * 1000))
        traceback.print_exc()


# ── 测试 5: 直接 LLM 调用 + JSON 解析 ─────────────────────────────────

async def test_raw_llm_json() -> None:
    """验证直接 LLM 调用能否返回可解析的 JSON（模拟 FMEA/Audit 路径）。"""
    name = "原始 LLM -> JSON 解析 (FMEA/Audit 路径)"
    t0 = time.perf_counter()
    try:
        llm = get_sales_specialist_llm()
        system = SystemMessage(
            content=(
                "你是测试 Agent。你只输出结构化 JSON，不得输出 Markdown。"
                "你必须只返回合法的 JSON 对象，不要输出代码块。"
                "JSON 必须是全部响应内容。"
            )
        )
        human = HumanMessage(
            content=(
                '请输出一个 JSON 对象：{"status": "ok", "items": ["a", "b"]}。'
                '只输出 JSON，不要其他内容。'
            )
        )
        response = await llm.ainvoke([system, human])
        content = response.content if hasattr(response, "content") else str(response)
        data = json.loads(str(content).strip().strip("`").strip())
        assert data["status"] == "ok", f"status 不匹配: {data}"
        assert isinstance(data["items"], list), "items 应为列表"
        detail = f"解析 JSON: {json.dumps(data, ensure_ascii=False)}"
        record(name, True, detail, int((time.perf_counter() - t0) * 1000))
    except Exception as exc:
        record(name, False, f"{type(exc).__name__}: {exc}", int((time.perf_counter() - t0) * 1000))
        traceback.print_exc()


# ── 主入口 ───────────────────────────────────────────────────────────────

async def main() -> None:
    print("=" * 60)
    print("真实 LLM 冒烟测试 -- E0 阶段")
    print("=" * 60)

    await test_planner()
    await test_rd_specialist()
    await test_quality_specialist()
    await test_reviewer()
    await test_raw_llm_json()

    # 汇总
    print("\n" + "=" * 60)
    print("汇总结果")
    print("=" * 60)
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    for r in results:
        status = "[通过]" if r["passed"] else "[失败]"
        print(f"  {status} {r['node']}  ({r['duration_ms']} ms)")
        if not r["passed"]:
            print(f"     {r['detail']}")
    print(f"\n通过: {passed}/{total}")
    if passed < total:
        print("!! 存在失败项，请检查上方详细输出。")
        sys.exit(1)
    else:
        print("全部通过。")


if __name__ == "__main__":
    asyncio.run(main())

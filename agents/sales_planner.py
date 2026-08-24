"""销售协作 Planner：结构化 LLM 规划与确定性 fallback。"""

from __future__ import annotations

import ast
import json
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from agents.sales_specialist_common import get_sales_specialist_llm
from agents.structured_llm import invoke_structured_json
from schemas.sales_collaboration import PlannerOutput


PLANNER_PROMPT = """你是销售协作流程的 Planner。

你只能规划以下 Agent：rd、quality、reviewer、writer、fmea、audit。
综合售前请求必须包含 R&D、Quality、Reviewer 和 Writer。
FMEA/Audit 只能作为建议的可选后续工作流，当前流程不会自动执行。
输出必须符合 PlannerOutput，不得调用工具或执行任何工作流。

你必须只返回合法的 JSON 对象，不要输出 Markdown 或 ```json 代码块。
整个响应必须是一个符合 PlannerOutput schema 的 JSON 对象。
JSON 必须是全部响应内容。
"""

CORE_TASK_AGENTS = {"rd", "quality", "reviewer", "writer"}
OPTIONAL_WORKFLOW_AGENTS = {"fmea", "audit"}


def default_sales_plan(*, warning: str | None = None) -> PlannerOutput:
    """返回固定、可执行的最小协作计划。"""
    warnings = [warning] if warning else []
    return PlannerOutput(
        tasks=[
            {
                "task_id": "rd_analysis",
                "agent": "rd",
                "objective": "分析技术可行性、工艺风险和验证重点",
                "required_sources": ["fmea_manual"],
                "depends_on": [],
                "required": True,
            },
            {
                "task_id": "quality_analysis",
                "agent": "quality",
                "objective": "分析质量保障、审核准备和过程控制要求",
                "required_sources": ["xf_vda_manual"],
                "depends_on": [],
                "required": True,
            },
            {
                "task_id": "review",
                "agent": "reviewer",
                "objective": "检查角色越权、冲突、无依据声明和人工确认项",
                "required_sources": [],
                "depends_on": ["rd_analysis", "quality_analysis"],
                "required": True,
            },
            {
                "task_id": "proposal_writer",
                "agent": "writer",
                "objective": "基于已审核内容生成统一售前方案",
                "required_sources": [],
                "depends_on": ["review"],
                "required": True,
            },
        ],
        rationale="综合售前请求需要技术、质量、审核和方案汇总四个串行步骤。",
        complexity="collaboration",
        warnings=warnings,
    )


def run_sales_planner(
    *,
    user_request: str,
    customer_context: dict[str, Any],
    session_id: str | None = None,
    llm: Any = None,
) -> PlannerOutput:
    """调用结构化 Planner；非法或不可执行输出回退到默认计划。"""
    prompt = f"""请规划本次销售协作任务，以 JSON 格式输出 PlannerOutput。

用户请求：
{user_request}

客户上下文：
{json.dumps(customer_context, ensure_ascii=False, sort_keys=True)}

session_id：
{session_id or ""}
"""
    try:
        model = llm or get_sales_specialist_llm()
        messages = [SystemMessage(content=PLANNER_PROMPT), HumanMessage(content=prompt)]
        try:
            raw_output = invoke_structured_json(model, PlannerOutput, messages)
            output = PlannerOutput.model_validate(raw_output)
        except Exception:
            # 回退：原始 LLM 调用 + JSON 提取
            raw = model.invoke(messages)
            content = raw.content if hasattr(raw, "content") else str(raw)
            cleaned = re.sub(r"^```(?:json)?\s*", "", str(content).strip())
            cleaned = re.sub(r"\s*```$", "", cleaned)
            match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
            raw_str = match.group(1) if match else cleaned
            try:
                data = json.loads(raw_str)
            except json.JSONDecodeError:
                data = ast.literal_eval(raw_str)
            output = PlannerOutput.model_validate(data)
        agents = {task.agent for task in output.tasks}
        if not CORE_TASK_AGENTS.issubset(agents):
            raise ValueError("planner output is missing required core agents")

        workflow_agents = sorted(agents & OPTIONAL_WORKFLOW_AGENTS)
        if workflow_agents:
            warning = (
                "Planner 建议可选工作流 "
                + ", ".join(workflow_agents)
                + "；本轮仅记录，不自动执行。"
            )
            if warning not in output.warnings:
                output.warnings.append(warning)
        return output
    except Exception as exc:
        return default_sales_plan(
            warning=f"Planner fallback 已启用：{type(exc).__name__}"
        )

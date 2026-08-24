from agents.sales_planner import default_sales_plan, run_sales_planner
from schemas.sales_collaboration import PlannerOutput


class FakeStructuredLLM:
    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.schema = None
        self.messages = None

    def with_structured_output(self, schema, **kwargs):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.messages = messages
        if self.error:
            raise self.error
        return self.output


def _valid_plan(extra_tasks=None):
    return {
        "tasks": [
            {
                "task_id": "technical",
                "agent": "rd",
                "objective": "分析技术风险",
            },
            {
                "task_id": "quality",
                "agent": "quality",
                "objective": "分析质量保障",
            },
            {
                "task_id": "review",
                "agent": "reviewer",
                "objective": "审核输出",
                "depends_on": ["technical", "quality"],
            },
            {
                "task_id": "writer",
                "agent": "writer",
                "objective": "生成方案",
                "depends_on": ["review"],
            },
            *(extra_tasks or []),
        ],
        "rationale": "需要跨专业协作。",
        "complexity": "collaboration",
        "warnings": [],
    }


def test_planner_accepts_valid_structured_output():
    llm = FakeStructuredLLM(_valid_plan())

    output = run_sales_planner(
        user_request="生成技术与质量联合售前方案。",
        customer_context={"customer": "测试客户"},
        session_id="session-1",
        llm=llm,
    )

    assert isinstance(output, PlannerOutput)
    assert output.rationale == "需要跨专业协作。"
    assert llm.schema is PlannerOutput
    assert {task.agent for task in output.tasks} == {
        "rd",
        "quality",
        "reviewer",
        "writer",
    }


def test_planner_invalid_agent_falls_back():
    invalid = _valid_plan()
    invalid["tasks"][0]["agent"] = "unregistered"

    output = run_sales_planner(
        user_request="生成售前方案。",
        customer_context={},
        llm=FakeStructuredLLM(invalid),
    )

    assert output.tasks[0].task_id == "rd_analysis"
    assert output.warnings
    assert "fallback" in output.warnings[0].lower()


def test_planner_llm_error_falls_back():
    output = run_sales_planner(
        user_request="生成售前方案。",
        customer_context={},
        llm=FakeStructuredLLM(error=RuntimeError("offline")),
    )

    assert output.tasks == default_sales_plan().tasks
    assert output.warnings == ["Planner fallback 已启用：RuntimeError"]


def test_default_plan_contains_all_core_agents():
    output = default_sales_plan()

    assert [task.agent for task in output.tasks] == [
        "rd",
        "quality",
        "reviewer",
        "writer",
    ]


def test_planner_records_fmea_audit_without_invoking_them():
    optional_tasks = [
        {
            "task_id": "optional-fmea",
            "agent": "fmea",
            "objective": "后续可选 FMEA",
            "required": False,
        },
        {
            "task_id": "optional-audit",
            "agent": "audit",
            "objective": "后续可选 Audit",
            "required": False,
        },
    ]
    output = run_sales_planner(
        user_request="分析风险，必要时建议专业工作流。",
        customer_context={},
        llm=FakeStructuredLLM(_valid_plan(optional_tasks)),
    )

    assert {task.agent for task in output.tasks} >= {"fmea", "audit"}
    assert any("不自动执行" in warning for warning in output.warnings)


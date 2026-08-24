from graphs.sales_collaboration_graph import (
    SALES_COLLABORATION_NODE_ORDER,
    build_sales_collaboration_graph,
)
from agents.sales_proposal_writer import REPORT_HEADINGS


def _fake_planner(**_kwargs):
    return {
        "tasks": [
            {
                "task_id": "rd_analysis",
                "agent": "rd",
                "objective": "分析技术风险",
            },
            {
                "task_id": "quality_analysis",
                "agent": "quality",
                "objective": "分析质量保障",
            },
            {
                "task_id": "review",
                "agent": "reviewer",
                "objective": "审核",
            },
            {
                "task_id": "proposal_writer",
                "agent": "writer",
                "objective": "写方案",
            },
        ],
        "rationale": "测试计划",
        "complexity": "collaboration",
        "warnings": [],
    }


def _fake_writer(**kwargs):
    citations = [
        *kwargs["rd_analysis"].get("citations", []),
        *kwargs["quality_analysis"].get("citations", []),
    ]
    report = "\n\n".join(
        (
            "# 售前协作方案",
            "## 1. 客户需求理解\n\n测试需求",
            "## 2. 技术与工艺风险\n\n测试技术风险",
            "## 3. 质量保障分析\n\n测试质量保障",
            "## 4. 信息缺口与人工确认项\n\n暂无",
            "## 5. 初步建议\n\n执行验证",
            "## 6. 引用依据\n\n测试引用",
        )
    )
    return {
        "final_report": report,
        "summary": "测试摘要",
        "citations": citations,
    }


def _fake_specialist(role: str):
    source_name = "fmea_manual" if role == "rd" else "xf_vda_manual"
    summary = "技术风险分析占位结果" if role == "rd" else "质量保障分析占位结果"
    category = "process" if role == "rd" else "quality_control"
    citation = {
        "citation_id": f"fake-{role}-citation-001",
        "source_type": "mock_document",
        "source_name": source_name,
    }

    def run_specialist(**_kwargs):
        return {
            "summary": summary,
            "claims": [
                {
                    "claim_id": f"{role}-claim-001",
                    "text": f"{summary}中的结论。",
                    "citations": [citation],
                    "confidence": "medium",
                    "requires_manual_check": False,
                }
            ],
            "risks": [
                {
                    "risk_id": f"{role}-risk-001",
                    "category": category,
                    "description": f"{summary}中的风险。",
                    "citations": [citation],
                    "requires_manual_check": True,
                }
            ],
            "recommendations": [
                {
                    "recommendation_id": f"{role}-rec-001",
                    "text": f"{summary}中的建议。",
                    "citations": [citation],
                    "requires_manual_check": False,
                }
            ],
            "missing_information": [],
            "citations": [citation],
            "confidence": "medium",
        }

    return run_specialist


def _invoke(user_request: str):
    graph = build_sales_collaboration_graph(
        planner=_fake_planner,
        rd_specialist=_fake_specialist("rd"),
        quality_specialist=_fake_specialist("quality"),
        writer=_fake_writer,
    )
    return graph.invoke(
        {
            "request_id": "test-sales-collaboration-001",
            "user_id": 1,
            "session_id": "test-session-001",
            "user_request": user_request,
        }
    )


def test_sales_collaboration_graph_completes_full_serial_flow():
    final_state = _invoke("请分析某汽车模具项目的技术风险和质量保障方案。")

    assert final_state["status"] == "completed"
    assert final_state["error"] is None
    assert final_state["execution_plan"]
    assert final_state["rd_analysis"]
    assert final_state["quality_analysis"]
    assert final_state["review_result"]["passed"] is True
    assert final_state["final_report"]

    for heading in REPORT_HEADINGS:
        assert heading in final_state["final_report"]

    steps = final_state["collaboration_steps"]
    assert [step["step_id"] for step in steps] == list(SALES_COLLABORATION_NODE_ORDER)
    assert all(step["status"] == "completed" for step in steps)
    assert {
        "planner",
        "rd_specialist",
        "quality_specialist",
        "reviewer",
        "proposal_writer",
        "final_verifier",
    }.issubset({step["step_id"] for step in steps})
    assert steps[-1]["output"] == {
        "persistence_requested": True,
        "mode": "api_repository",
    }


def test_specialist_outputs_follow_phase_b_contract_shape():
    final_state = _invoke("生成技术与质量联合售前建议。")

    for field in ("rd_analysis", "quality_analysis"):
        output = final_state[field]
        assert output["summary"]
        assert output["claims"]
        assert output["risks"]
        assert output["recommendations"]
        assert output["citations"]
        assert output["confidence"] == "medium"


def test_empty_user_request_fails_without_completing_run():
    final_state = _invoke("   ")

    assert final_state["status"] == "failed"
    assert final_state["error"]
    assert final_state["final_report"] == ""
    assert final_state["collaboration_steps"][0]["status"] == "failed"
    assert all(
        step["status"] == "skipped"
        for step in final_state["collaboration_steps"][1:]
    )

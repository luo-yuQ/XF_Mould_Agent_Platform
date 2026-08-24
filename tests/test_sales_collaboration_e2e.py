import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


try:
    import jose  # noqa: F401
except ModuleNotFoundError:
    jose_stub = ModuleType("jose")
    jose_stub.JWTError = type("JWTError", (Exception,), {})
    jose_stub.jwt = SimpleNamespace(
        encode=lambda *args, **kwargs: "",
        decode=lambda *args, **kwargs: {},
    )
    sys.modules["jose"] = jose_stub

try:
    import langchain_openai  # noqa: F401
except ModuleNotFoundError:
    langchain_openai_stub = ModuleType("langchain_openai")
    langchain_openai_stub.ChatOpenAI = type(
        "ChatOpenAI",
        (),
        {"__init__": lambda self, *args, **kwargs: None},
    )
    sys.modules["langchain_openai"] = langchain_openai_stub


if "api" not in sys.modules:
    graph_modules = {}
    for module_name, builder_name in (
        ("graph", "build_graph"),
        ("fmea_graph", "build_fmea_graph"),
        ("audit_graph", "build_audit_graph"),
        ("report_graph", "build_report_graph"),
    ):
        graph_modules[module_name] = sys.modules.get(module_name)
        module = ModuleType(module_name)
        setattr(module, builder_name, lambda: None)
        sys.modules[module_name] = module

    import api

    for module_name, original_module in graph_modules.items():
        if original_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = original_module
else:
    import api

from agents.sales_planner import default_sales_plan
from agents.sales_proposal_writer import run_sales_proposal_writer
from graphs.sales_collaboration_graph import build_sales_collaboration_graph
from models.base import Base
from models.collaboration import CollaborationRun, CollaborationStep
from models.user import User


CASES_PATH = (
    Path(__file__).resolve().parents[1]
    / "eval_cases"
    / "sales_collaboration_cases.json"
)
CASES = json.loads(CASES_PATH.read_text(encoding="utf-8"))
REQUIRED_STEP_IDS = {
    "planner",
    "rd_specialist",
    "quality_specialist",
    "reviewer",
    "proposal_writer",
    "final_verifier",
}
REQUIRED_REPORT_SECTIONS = (
    "客户需求理解",
    "技术与工艺风险",
    "质量保障分析",
    "信息缺口与人工确认项",
    "初步建议",
    "引用依据",
)


class OfflineWriterLLM:
    def with_structured_output(self, _schema, **kwargs):
        return self

    def invoke(self, _messages):
        raise RuntimeError("offline test uses deterministic writer fallback")


@pytest.fixture
def e2e_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    user = User(username="sales-e2e", password_hash="test")
    db.add(user)
    db.commit()
    db.refresh(user)

    def override_db():
        yield db

    def override_user():
        return user

    api.app.dependency_overrides[api.get_db] = override_db
    api.app.dependency_overrides[api.get_current_user] = override_user
    with TestClient(api.app) as client:
        yield SimpleNamespace(client=client, db=db, user=user)

    api.app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _planner(**_kwargs):
    return default_sales_plan()


def _specialist(role):
    def run_specialist(*, user_request, **_kwargs):
        insufficient = user_request.strip() == "帮我做一个售前方案。"
        is_rd = role == "rd"
        citation = {
            "citation_id": f"{role}-e2e-source",
            "source_type": "text",
            "source_name": "FMEA手册" if is_rd else "XF VDA6.4质量手册",
            "title": "风险分析" if is_rd else "过程控制",
        }
        if insufficient:
            summary = (
                "当前信息不足，仅能给出待验证的技术风险框架。"
                if is_rd
                else "当前信息不足，仅能给出待确认的质量保障框架。"
            )
        elif is_rd:
            summary = "技术分析以成型窗口、材料波动和试模验证风险为重点。"
        else:
            summary = "质量分析以过程质量门、审核证据和验收标准为重点。"

        return {
            "summary": summary,
            "claims": [
                {
                    "claim_id": f"{role}-claim",
                    "text": (
                        "关键成型窗口需要通过试模数据验证。"
                        if is_rd
                        else "项目需要建立过程质量门和审核记录。"
                    ),
                    "citations": [citation],
                    "confidence": "medium",
                    "requires_manual_check": insufficient,
                }
            ],
            "risks": [
                {
                    "risk_id": f"{role}-risk",
                    "category": "process" if is_rd else "quality_control",
                    "description": (
                        "材料与成型参数信息不足可能影响技术判断。"
                        if is_rd
                        else "验收标准和审核范围不明确可能造成质量口径不一致。"
                    ),
                    "citations": [citation],
                    "requires_manual_check": True,
                }
            ],
            "recommendations": [
                {
                    "recommendation_id": f"{role}-recommendation",
                    "text": (
                        "补充材料、关键尺寸和试模计划后再冻结技术方案。"
                        if is_rd
                        else "确认验收标准、审核范围和质量记录责任人。"
                    ),
                    "citations": [citation],
                    "requires_manual_check": False,
                }
            ],
            "missing_information": [
                {
                    "item_id": f"{role}-missing",
                    "question": (
                        "请补充材料、关键尺寸和目标产能。"
                        if is_rd
                        else "请补充客户验收标准和审核范围。"
                    ),
                    "reason": "需要完善售前判断依据。",
                    "required_for": "详细售前方案",
                }
            ],
            "citations": [citation],
            "confidence": "medium",
        }

    return run_specialist


def _writer(**kwargs):
    return run_sales_proposal_writer(**kwargs, llm=OfflineWriterLLM())


def _graph(*, quality_specialist=None):
    return build_sales_collaboration_graph(
        planner=_planner,
        rd_specialist=_specialist("rd"),
        quality_specialist=quality_specialist or _specialist("quality"),
        writer=_writer,
    )


def _post_case(context, case, graph=None):
    with patch(
        "api.get_sales_collaboration_graph",
        return_value=graph or _graph(),
    ):
        return context.client.post(
            "/sales/proposals/generate",
            json={
                **case["input"],
                "session_id": None,
            },
        )


@pytest.mark.parametrize("case", CASES, ids=[case["case_id"] for case in CASES])
def test_sales_collaboration_smoke_cases_end_to_end(e2e_context, case):
    response = _post_case(e2e_context, case)

    assert response.status_code == 201
    generated = response.json()
    run_id = generated["run_id"]
    run_response = e2e_context.client.get(f"/sales/proposals/{run_id}")
    steps_response = e2e_context.client.get(f"/sales/proposals/{run_id}/steps")

    assert run_response.status_code == 200
    assert steps_response.status_code == 200
    run = run_response.json()
    steps = steps_response.json()
    assert run["status"] == "completed"
    assert run["review_result"]
    assert "citations" in run
    assert REQUIRED_STEP_IDS.issubset({step["step_id"] for step in steps})
    assert all(section in run["final_report"] for section in REQUIRED_REPORT_SECTIONS)

    expected = case["expected"]
    assert run["status"] == expected["status"]
    for phrase in expected.get("forbidden_phrases", []):
        assert phrase not in run["final_report"]
    if expected.get("citations_non_empty"):
        assert run["citations"]
    if expected.get("manual_check_notice"):
        assert (
            "人工确认" in run["final_report"]
            or "请补充" in run["final_report"]
            or "确认" in run["final_report"]
        )
    if expected.get("information_gap_notice"):
        assert "信息不足" in run["final_report"] or "请补充" in run["final_report"]
    if expected.get("rd_focus"):
        assert "成型窗口" in run["final_report"]
    if expected.get("quality_focus"):
        assert "过程质量门" in run["final_report"]
    if "review_passed" in expected:
        assert run["review_result"]["passed"] is expected["review_passed"]
    if expected.get("overcommitment_warning"):
        assert any(
            "过度承诺风险" in item
            for item in run["review_result"]["conflicts"]
        )
        assert "当前售前方案不作零缺陷或绝对结果保证" in run["final_report"]


def test_empty_input_returns_400_without_completed_run(e2e_context):
    with patch("api.get_sales_collaboration_graph") as graph_getter:
        response = e2e_context.client.post(
            "/sales/proposals/generate",
            json={"user_request": "   ", "customer_context": {}, "session_id": None},
        )

    assert response.status_code == 400
    assert (
        e2e_context.db.query(CollaborationRun)
        .filter(CollaborationRun.status == "completed")
        .count()
        == 0
    )
    graph_getter.assert_not_called()


def test_node_failure_persists_failed_run_and_completed_steps(e2e_context):
    def failing_quality(**_kwargs):
        raise RuntimeError("quality specialist unavailable")

    case = CASES[0]
    response = _post_case(
        e2e_context,
        case,
        graph=_graph(quality_specialist=failing_quality),
    )

    assert response.status_code == 500
    run_id = response.json()["detail"]["run_id"]
    run = (
        e2e_context.db.query(CollaborationRun)
        .filter_by(run_id=run_id)
        .one()
    )
    steps = (
        e2e_context.db.query(CollaborationStep)
        .filter_by(run_id=run_id)
        .order_by(CollaborationStep.id)
        .all()
    )
    statuses = {step.step_id: step.status for step in steps}
    assert run.status == "failed"
    assert run.error == "Quality specialist failed: quality specialist unavailable"
    assert statuses["request_intake"] == "completed"
    assert statuses["planner"] == "completed"
    assert statuses["rd_specialist"] == "completed"
    assert statuses["quality_specialist"] == "failed"
    assert statuses["reviewer"] == "skipped"


def test_reviewer_failure_warning_survives_writer(e2e_context):
    overcommitment_case = next(
        case for case in CASES if case["category"] == "overcommitment"
    )
    response = _post_case(e2e_context, overcommitment_case)

    assert response.status_code == 201
    payload = response.json()
    assert payload["review_result"]["passed"] is False
    assert "过度承诺风险" in payload["final_report"]
    assert "质量承诺需由质量部门、合同责任人和授权审批人确认" in payload[
        "final_report"
    ]


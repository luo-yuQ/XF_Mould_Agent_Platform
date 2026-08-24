import sys
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

from models.base import Base
from models.chat import ChatSession
from models.collaboration import CollaborationRun, CollaborationStep
from models.user import User


class FakeSalesGraph:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.received_state = None

    async def ainvoke(self, state, config=None):
        self.received_state = state
        if self.error:
            raise self.error
        return {
            **state,
            "status": "completed",
            "execution_plan": [
                {
                    "task_id": "rd_analysis",
                    "agent": "rd",
                    "objective": "分析技术风险",
                }
            ],
            "rd_analysis": {"summary": "技术风险分析"},
            "quality_analysis": {"summary": "质量保障分析"},
            "review_result": {"passed": True},
            "final_report": "# 售前协作方案\n\n已完成技术与质量联合分析。",
            "citations": [
                {
                    "citation_id": "source-001",
                    "source_type": "text",
                    "source_name": "测试知识库",
                }
            ],
            "steps": [
                {
                    "step_id": "request_intake",
                    "step_name": "需求受理",
                    "agent": "intake",
                    "status": "completed",
                    "input_json": {"user_request": state["user_request"]},
                    "output_json": {"status": "running"},
                },
                {
                    "step_id": "planner",
                    "step_name": "协作规划",
                    "agent": "planner",
                    "status": "completed",
                    "input_json": {"user_request": state["user_request"]},
                    "output_json": {"tasks": ["rd_analysis"]},
                    "duration_ms": 5,
                },
                {
                    "step_id": "rd_specialist",
                    "step_name": "研发分析",
                    "agent": "rd",
                    "status": "completed",
                },
                {
                    "step_id": "quality_specialist",
                    "step_name": "质量分析",
                    "agent": "quality",
                    "status": "completed",
                },
                {
                    "step_id": "reviewer",
                    "step_name": "结果审核",
                    "agent": "reviewer",
                    "status": "completed",
                },
                {
                    "step_id": "proposal_writer",
                    "step_name": "方案编写",
                    "agent": "writer",
                    "status": "completed",
                },
                {
                    "step_id": "final_verifier",
                    "step_name": "最终校验",
                    "agent": "verifier",
                    "status": "completed",
                },
            ],
        }


class FailedStateGraph:
    async def ainvoke(self, state, config=None):
        return {
            **state,
            "status": "failed",
            "error": "Specialist validation failed.",
            "execution_plan": [{"task_id": "rd_analysis", "agent": "rd"}],
            "review_result": {},
            "final_report": "",
            "citations": [],
            "collaboration_steps": [
                {
                    "step_id": "request_intake",
                    "step_name": "需求受理",
                    "agent": "intake",
                    "status": "completed",
                    "output": {"status": "running"},
                },
                {
                    "step_id": "rd_specialist",
                    "step_name": "研发分析",
                    "agent": "rd",
                    "status": "failed",
                    "error": "Specialist validation failed.",
                },
            ],
        }


@pytest.fixture
def api_context():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    owner = User(username="sales-owner", password_hash="test")
    other = User(username="sales-other", password_hash="test")
    db.add_all([owner, other])
    db.flush()
    session = ChatSession(
        id="sales-session",
        user_id=owner.id,
        title="Sales collaboration",
    )
    db.add(session)
    db.commit()
    db.refresh(owner)
    db.refresh(other)

    current_user = {"value": owner}

    def override_db():
        yield db

    def override_user():
        return current_user["value"]

    api.app.dependency_overrides[api.get_db] = override_db
    api.app.dependency_overrides[api.get_current_user] = override_user

    with TestClient(api.app) as client:
        yield SimpleNamespace(
            client=client,
            db=db,
            owner=owner,
            other=other,
            session=session,
            current_user=current_user,
        )

    api.app.dependency_overrides.clear()
    db.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _generate(api_context, graph=None):
    fake_graph = graph or FakeSalesGraph()
    with patch("api.get_sales_collaboration_graph", return_value=fake_graph):
        response = api_context.client.post(
            "/sales/proposals/generate",
            json={
                "user_request": "请分析汽车覆盖件冲压模具的技术风险和质量保障方式。",
                "customer_context": {"customer": "测试客户"},
                "session_id": api_context.session.id,
            },
        )
    return response, fake_graph


def test_generate_sales_proposal_persists_run_and_steps(api_context):
    response, graph = _generate(api_context)

    assert response.status_code == 201
    payload = response.json()
    assert payload["run_id"].startswith("sales_")
    assert payload["status"] == "completed"
    assert payload["final_report"]
    assert payload["execution_plan"]
    assert payload["review_result"]["passed"] is True
    assert payload["citations"]
    assert graph.received_state["user_id"] == api_context.owner.id
    assert graph.received_state["customer_context"] == {"customer": "测试客户"}

    run = (
        api_context.db.query(CollaborationRun)
        .filter_by(run_id=payload["run_id"])
        .one()
    )
    steps = (
        api_context.db.query(CollaborationStep)
        .filter_by(run_id=payload["run_id"])
        .order_by(CollaborationStep.id)
        .all()
    )
    assert run.status == "completed"
    assert run.user_id == api_context.owner.id
    assert run.customer_context_json == {"customer": "测试客户"}
    assert [step.step_id for step in steps] == [
        "request_intake",
        "planner",
        "rd_specialist",
        "quality_specialist",
        "reviewer",
        "proposal_writer",
        "final_verifier",
    ]
    assert steps[1].duration_ms == 5


def test_empty_user_request_returns_400_without_creating_run(api_context):
    with patch("api.get_sales_collaboration_graph") as graph_getter:
        response = api_context.client.post(
            "/sales/proposals/generate",
            json={"user_request": "   ", "customer_context": {}, "session_id": None},
        )

    assert response.status_code == 400
    assert api_context.db.query(CollaborationRun).count() == 0
    graph_getter.assert_not_called()


def test_generated_run_and_steps_can_be_queried(api_context):
    generated, _ = _generate(api_context)
    run_id = generated.json()["run_id"]

    run_response = api_context.client.get(f"/sales/proposals/{run_id}")
    steps_response = api_context.client.get(f"/sales/proposals/{run_id}/steps")

    assert run_response.status_code == 200
    assert run_response.json()["run_id"] == run_id
    assert run_response.json()["customer_context"] == {"customer": "测试客户"}
    assert steps_response.status_code == 200
    assert [step["step_id"] for step in steps_response.json()] == [
        "request_intake",
        "planner",
        "rd_specialist",
        "quality_specialist",
        "reviewer",
        "proposal_writer",
        "final_verifier",
    ]
    assert set(steps_response.json()[0]) == {
        "step_id",
        "step_name",
        "agent",
        "status",
        "input_json",
        "output_json",
        "error",
        "started_at",
        "finished_at",
        "duration_ms",
        "model_info_json",
        "metrics_json",
    }


def test_missing_and_foreign_runs_return_404(api_context):
    missing = api_context.client.get("/sales/proposals/sales_missing")
    assert missing.status_code == 404

    generated, _ = _generate(api_context)
    run_id = generated.json()["run_id"]
    api_context.current_user["value"] = api_context.other

    assert api_context.client.get(f"/sales/proposals/{run_id}").status_code == 404
    assert (
        api_context.client.get(f"/sales/proposals/{run_id}/steps").status_code
        == 404
    )


def test_graph_exception_preserves_failed_run_and_stable_error(api_context):
    response, _ = _generate(
        api_context,
        graph=FakeSalesGraph(error=RuntimeError("internal secret traceback")),
    )

    assert response.status_code == 500
    detail = response.json()["detail"]
    assert detail["code"] == "sales_collaboration_failed"
    assert "internal secret traceback" not in response.text

    run = (
        api_context.db.query(CollaborationRun)
        .filter_by(run_id=detail["run_id"])
        .one()
    )
    assert run.status == "failed"
    assert run.error == "Sales collaboration graph execution failed."


def test_failed_graph_state_preserves_completed_and_failed_steps(api_context):
    response, _ = _generate(api_context, graph=FailedStateGraph())

    assert response.status_code == 500
    run_id = response.json()["detail"]["run_id"]
    run = (
        api_context.db.query(CollaborationRun)
        .filter_by(run_id=run_id)
        .one()
    )
    steps = (
        api_context.db.query(CollaborationStep)
        .filter_by(run_id=run_id)
        .order_by(CollaborationStep.id)
        .all()
    )
    assert run.status == "failed"
    assert run.error == "Specialist validation failed."
    assert [(step.step_id, step.status) for step in steps] == [
        ("request_intake", "completed"),
        ("rd_specialist", "failed"),
    ]

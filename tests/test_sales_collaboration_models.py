import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models import (
    ChatSession,
    CollaborationRun,
    CollaborationStep,
    User,
)
from models.base import Base
from time_utils import utc_now


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    user = User(username="collaboration-user", password_hash="test")
    session.add(user)
    session.flush()
    chat_session = ChatSession(
        id="collaboration-session",
        user_id=user.id,
        title="Collaboration test",
    )
    session.add(chat_session)
    session.commit()

    yield session, engine, user, chat_session

    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()


def _new_run(user_id: int, session_id: str) -> CollaborationRun:
    return CollaborationRun(
        run_id="collaboration-run-001",
        user_id=user_id,
        session_id=session_id,
        user_request="评估客户模具项目并给出技术和质量建议。",
        customer_context_json={
            "customer_name": "测试客户",
            "material": "PA66+GF30",
        },
        execution_plan_json=[
            {
                "task_id": "task-rd",
                "agent": "rd",
                "objective": "评估技术可行性。",
            },
            {
                "task_id": "task-quality",
                "agent": "quality",
                "objective": "评估质量风险。",
            },
        ],
        status="running",
        review_result_json={
            "passed": False,
            "manual_check_items": ["确认关键尺寸公差"],
        },
        citations_json=[
            {
                "citation_id": "citation-001",
                "source_type": "document",
                "source_name": "客户技术要求.pdf",
            }
        ],
        model_info_json={"planner": "not-implemented"},
        metrics_json={"step_count": 2},
    )


def test_collaboration_tables_can_be_created(db_session):
    _, engine, _, _ = db_session
    inspector = inspect(engine)

    assert "collaboration_runs" in inspector.get_table_names()
    assert "collaboration_steps" in inspector.get_table_names()


def test_run_and_json_fields_can_be_saved(db_session):
    session, _, user, chat_session = db_session
    run = _new_run(user.id, chat_session.id)

    session.add(run)
    session.commit()
    session.refresh(run)

    assert run.id is not None
    assert run.execution_plan_json[0]["agent"] == "rd"
    assert run.review_result_json["passed"] is False
    assert run.citations_json[0]["citation_id"] == "citation-001"
    assert run.customer_context_json["material"] == "PA66+GF30"
    assert run.created_at is not None
    assert run.updated_at is not None


def test_step_and_run_relationship_can_be_saved(db_session):
    session, _, user, chat_session = db_session
    run = _new_run(user.id, chat_session.id)
    step = CollaborationStep(
        step_id="step-rd",
        step_name="研发分析",
        agent="rd",
        status="completed",
        input_json={
            "objective": "评估技术可行性。",
            "required_sources": ["客户技术要求.pdf"],
        },
        output_json={
            "summary": "技术方案基本可行。",
            "confidence": "medium",
            "claims": [],
        },
        started_at=utc_now(),
        finished_at=utc_now(),
        duration_ms=1250,
        model_info_json={"model": "test-model"},
        metrics_json={"input_tokens": 100, "output_tokens": 50},
    )
    run.steps.append(step)

    session.add(run)
    session.commit()
    session.expire_all()

    saved_run = session.query(CollaborationRun).filter_by(run_id=run.run_id).one()
    saved_step = session.query(CollaborationStep).filter_by(step_id="step-rd").one()

    assert saved_run.steps == [saved_step]
    assert saved_step.run is saved_run
    assert saved_step.run_id == saved_run.run_id
    assert saved_step.input_json["required_sources"] == ["客户技术要求.pdf"]
    assert saved_step.output_json["confidence"] == "medium"
    assert saved_step.model_info_json["model"] == "test-model"
    assert saved_step.metrics_json["output_tokens"] == 50


def test_step_id_must_be_unique_within_a_run(db_session):
    session, _, user, chat_session = db_session
    run = _new_run(user.id, chat_session.id)
    run.steps.extend(
        [
            CollaborationStep(
                step_id="duplicate-step",
                step_name="研发分析",
                agent="rd",
                status="pending",
            ),
            CollaborationStep(
                step_id="duplicate-step",
                step_name="质量分析",
                agent="quality",
                status="pending",
            ),
        ]
    )
    session.add(run)

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_migration_declares_expected_tables_indexes_and_constraints():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "010_create_collaboration_runs_and_steps.py"
    )
    fake_op = MagicMock()
    fake_alembic = types.ModuleType("alembic")
    fake_alembic.op = fake_op
    spec = importlib.util.spec_from_file_location(
        "migration_010_collaboration",
        migration_path,
    )
    module = importlib.util.module_from_spec(spec)

    with patch.dict(sys.modules, {"alembic": fake_alembic}):
        assert spec.loader is not None
        spec.loader.exec_module(module)

    module.upgrade()

    assert module.revision == "010"
    assert module.down_revision == "009"
    assert [call.args[0] for call in fake_op.create_table.call_args_list] == [
        "collaboration_runs",
        "collaboration_steps",
    ]

    index_calls = {
        call.args[0]: call
        for call in fake_op.create_index.call_args_list
    }
    assert index_calls["ix_collaboration_runs_run_id"].kwargs["unique"] is True
    assert "ix_collaboration_steps_run_id" in index_calls

    step_table_args = fake_op.create_table.call_args_list[1].args
    constraint_names = {
        argument.name
        for argument in step_table_args
        if getattr(argument, "name", None)
    }
    assert "uq_collaboration_steps_run_step" in constraint_names
    assert "ck_collaboration_steps_status" in constraint_names

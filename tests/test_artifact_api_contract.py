import unittest
from datetime import datetime, timezone
import sys
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from audit_graph import save_audit_run_node
from fmea_graph import save_fmea_run_node

try:
    import jose  # noqa: F401
except ModuleNotFoundError:
    jose_stub = ModuleType("jose")
    jose_stub.JWTError = type("JWTError", (Exception,), {})
    jose_stub.jwt = SimpleNamespace(encode=lambda *args, **kwargs: "", decode=lambda *args, **kwargs: {})
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

from models.audit import AuditRun
from models.base import Base
from models.chat import ChatSession
from models.artifact_version import BusinessArtifactVersion
from models.fmea import FMEARun
from models.report import ReportRun
from models.user import User


class SavingGraph:
    """Replace generation nodes while retaining the real persistence node."""

    def __init__(self, artifact_type: str):
        self.artifact_type = artifact_type

    async def ainvoke(self, state, config=None):
        if self.artifact_type == "fmea":
            raw = state["fmea_input_raw"]
            state.update({
                "fmea_input": {
                    "fmea_type": "PFMEA",
                    "product": raw["product"],
                    "process": raw["process"],
                    "failure_phenomenon": raw["failure_phenomenon"],
                    "background": raw["background"],
                },
                "fmea_rows": [{
                    "failure_mode": "飞边",
                    "effect": "装配干涉",
                    "cause": "模具间隙偏大",
                    "recommended_action": "复核模具间隙",
                }],
                "fmea_markdown": "# FMEA 测试结果",
                "fmea_verification": {"passed": True},
                "citation_map": {
                    1: {
                        "source": "FMEA手册.pdf",
                        "section_title": "风险分析",
                        "chunk_uid": "fmea-test-ref",
                    }
                },
            })
            return await save_fmea_run_node(state)

        raw = state["audit_input_raw"]
        state.update({
            "audit_input": {
                "audit_type": raw["audit_type"],
                "content": raw["content"],
                "focus": raw["focus"],
                "background": raw["background"],
            },
            "audit_findings": [{
                "issue": "整改措施缺少验证记录",
                "category": "整改闭环",
                "risk_level": "中",
                "recommendation": "补充验证记录",
                "manual_check_required": True,
            }],
            "audit_markdown": "# Audit 测试结果",
            "audit_verification": {"passed": True},
            "citation_map": {
                1: {
                    "source": "VDA6.4.pdf",
                    "section_title": "整改闭环",
                    "chunk_uid": "audit-test-ref",
                }
            },
        })
        return await save_audit_run_node(state)


class ArtifactRunIdApiContractTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.db = self.SessionLocal()
        self.user = User(username="v45-user", password_hash="test")
        self.db.add(self.user)
        self.db.commit()
        self.db.refresh(self.user)
        self.session = ChatSession(
            id="v45-session",
            user_id=self.user.id,
            title="4.5 contract test",
        )
        self.db.add(self.session)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    async def test_fmea_response_run_id_can_query_persisted_record(self):
        request = api.FMEAGenerateRequest(
            session_id=self.session.id,
            product="注塑件外壳",
            process="注塑",
            failure_phenomenon="飞边",
            background="装配干涉",
        )

        with patch("api.get_fmea_graph", return_value=SavingGraph("fmea")):
            response = await api.generate_fmea(request, user=self.user, db=self.db)

        self.assertIsNotNone(response.fmea_run_id)
        self.assertEqual(response.artifact_id, response.fmea_run_id)
        self.assertIsNotNone(response.current_version_id)
        self.assertEqual(response.current_version_no, 1)
        run = self.db.get(FMEARun, int(response.fmea_run_id))
        self.assertIsNotNone(run)
        self.assertEqual(run.user_id, self.user.id)
        self.assertEqual(run.artifact_type, "fmea_run")
        version = self.db.get(BusinessArtifactVersion, response.current_version_id)
        self.assertIsNotNone(version)
        self.assertEqual(version.artifact_id, run.id)
        self.assertEqual(version.version_no, 1)
        self.assertEqual(version.operation_type, "create")
        self.assertIsNone(version.parent_version_id)
        self.assertEqual(version.input_snapshot_json, run.input_json)
        self.assertEqual(version.output_json, run.output_json)
        self.assertEqual(version.final_markdown, run.output_markdown)
        self.assertEqual(version.references_json, run.references_json)
        self.assertEqual(version.verify_result_json, run.verify_result_json)

        history = api.get_session_artifacts(
            self.session.id,
            artifact_type="fmea",
            limit=20,
            offset=0,
            user=self.user,
            db=self.db,
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].artifact_id, response.artifact_id)
        self.assertEqual(history[0].latest_version_id, response.current_version_id)
        self.assertEqual(history[0].latest_version_no, 1)

        versions = api.get_artifact_versions(
            response.artifact_id,
            artifact_type=None,
            user=self.user,
            db=self.db,
        )
        self.assertEqual(versions.artifact_type, "fmea")
        self.assertEqual([item.version_no for item in versions.versions], [1])

        detail = api.get_artifact_version_detail(
            response.artifact_id,
            response.current_version_id,
            artifact_type=None,
            user=self.user,
            db=self.db,
        )
        self.assertEqual(detail.final_markdown, run.output_markdown)

    async def test_audit_response_run_id_can_query_persisted_record(self):
        request = api.AuditCheckRequest(
            session_id=self.session.id,
            audit_type="quality_issue",
            content="注塑件外壳飞边造成装配干涉。",
            focus="整改闭环",
            background="客户装配反馈",
        )

        with patch("api.get_audit_graph", return_value=SavingGraph("audit")):
            response = await api.check_audit(request, user=self.user, db=self.db)

        self.assertIsNotNone(response.audit_run_id)
        run = self.db.get(AuditRun, int(response.audit_run_id))
        self.assertIsNotNone(run)
        self.assertEqual(run.user_id, self.user.id)
        self.assertEqual(run.artifact_type, "audit_run")


class ReportSourcesFallbackTests(unittest.TestCase):
    class Query:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def limit(self, value):
            return self

        def all(self):
            return self.rows

    class Database:
        def __init__(self, fmea_runs, audit_runs):
            self.fmea_runs = fmea_runs
            self.audit_runs = audit_runs

        def query(self, model):
            if model is FMEARun:
                return ReportSourcesFallbackTests.Query(self.fmea_runs)
            if model is AuditRun:
                return ReportSourcesFallbackTests.Query(self.audit_runs)
            raise AssertionError(f"unexpected model: {model}")

    def test_sources_endpoint_falls_back_for_legacy_empty_metadata(self):
        created_at = datetime(2026, 6, 1, 8, 30, 0, tzinfo=timezone.utc)
        fmea = SimpleNamespace(
            id=101,
            user_id=7,
            title=None,
            summary=None,
            keywords_json=None,
            artifact_type=None,
            product="注塑件外壳",
            process="注塑",
            failure_phenomenon="飞边",
            output_json={"rows": [{"failure_mode": "飞边"}]},
            created_at=created_at,
            updated_at=None,
        )
        audit = SimpleNamespace(
            id=201,
            user_id=7,
            title="",
            summary="",
            keywords_json={},
            artifact_type="",
            audit_type="quality_issue",
            focus="装配干涉",
            content_text="设备点检记录需要复核。",
            findings_json={
                "findings": [{"issue": "设备点检表缺失"}],
            },
            created_at=created_at,
            updated_at=None,
        )
        db = self.Database([fmea], [audit])
        user = SimpleNamespace(id=7)

        response = api.list_report_sources(user=user, db=db)
        fmea_item = response.fmea_runs[0]
        audit_item = response.audit_runs[0]

        self.assertEqual(fmea_item.title, "注塑件外壳 - 注塑")
        self.assertIn("问题现象：飞边", fmea_item.summary)
        self.assertEqual(fmea_item.keywords_json, [])
        self.assertEqual(fmea_item.artifact_type, "fmea_run")
        self.assertEqual(fmea_item.updated_at, created_at)
        self.assertEqual(fmea_item.created_at, created_at)

        self.assertEqual(audit_item.title, "quality_issue - 装配干涉")
        self.assertIn("设备点检表缺失", audit_item.summary)
        self.assertEqual(audit_item.keywords_json, [])
        self.assertEqual(audit_item.artifact_type, "audit_run")
        self.assertEqual(audit_item.updated_at, created_at)
        self.assertEqual(audit_item.created_at, created_at)

        serialized = response.model_dump(mode="json")
        self.assertTrue(serialized["fmea_runs"][0]["created_at"].endswith("Z"))
        self.assertTrue(serialized["audit_runs"][0]["updated_at"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()

import sys
import unittest
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.routing import APIRoute
from langchain_core.messages import AIMessage


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
    _graph_modules = {}
    for _module_name, _builder_name in (
        ("graph", "build_graph"),
        ("fmea_graph", "build_fmea_graph"),
        ("audit_graph", "build_audit_graph"),
        ("report_graph", "build_report_graph"),
    ):
        _graph_modules[_module_name] = sys.modules.get(_module_name)
        _module = ModuleType(_module_name)
        setattr(_module, _builder_name, lambda: None)
        sys.modules[_module_name] = _module

    import api

    for _module_name, _original_module in _graph_modules.items():
        if _original_module is None:
            sys.modules.pop(_module_name, None)
        else:
            sys.modules[_module_name] = _original_module
else:
    import api


class FakeGraph:
    def __init__(self, output=None, error=None):
        self.output = output or {}
        self.error = error
        self.received_state = None
        self.received_config = None

    async def ainvoke(self, state, config=None):
        self.received_state = state
        self.received_config = config
        if self.error:
            raise self.error
        return self.output


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return self.rows


class FakeReportSourcesDB:
    def __init__(self, fmea_rows, audit_rows):
        self.fmea_rows = fmea_rows
        self.audit_rows = audit_rows

    def query(self, model):
        if model.__name__ == "FMEARun":
            return FakeQuery(self.fmea_rows)
        if model.__name__ == "AuditRun":
            return FakeQuery(self.audit_rows)
        raise AssertionError(f"unexpected query model: {model}")


def _declared_status(path, method):
    for route in api.app.routes:
        if (
            isinstance(route, APIRoute)
            and route.path == path
            and method in route.methods
        ):
            return route.status_code or 200
    raise AssertionError(f"route not found: {method} {path}")


def _snapshot_with_ignored_fields(payload, ignored):
    result = dict(payload)
    for field in ignored:
        if field in result:
            result[field] = "<ignored>"
    return result


class QualityWorkflowApiSnapshotTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=7)
        self.session = SimpleNamespace(id="session-1", user_id=self.user.id)

    async def test_fmea_generate_response_snapshot(self):
        graph = FakeGraph(
            {
                "messages": [AIMessage(content="generated fmea markdown")],
                "fmea_run_id": "101",
                "fmea_current_version_id": "version-101",
                "fmea_current_version_no": 1,
                "fmea_rows": [{"failure_mode": "裂纹", "rpn": 120}],
                "fmea_verification": {"passed": True, "issues": []},
            }
        )
        request = api.FMEAGenerateRequest(
            session_id=self.session.id,
            product="覆盖件",
            process="拉延",
            failure_phenomenon="裂纹",
        )

        with patch("api._get_owned_session", return_value=self.session), patch(
            "api.get_fmea_graph",
            return_value=graph,
        ):
            response = await api.generate_fmea(
                request,
                user=self.user,
                db=SimpleNamespace(),
            )

        snapshot = _snapshot_with_ignored_fields(
            response.model_dump(),
            {
                "final_answer",
                "fmea_run_id",
                "artifact_id",
                "current_version_id",
            },
        )
        self.assertEqual(
            snapshot,
            {
                "final_answer": "<ignored>",
                "fmea_run_id": "<ignored>",
                "artifact_id": "<ignored>",
                "current_version_id": "<ignored>",
                "current_version_no": 1,
                "fmea_rows": [{"failure_mode": "裂纹", "rpn": 120}],
                "verify_result": {"passed": True, "issues": []},
            },
        )
        self.assertEqual(_declared_status("/quality/fmea/generate", "POST"), 200)
        self.assertEqual(graph.received_config, {"recursion_limit": 20})

    async def test_audit_check_response_snapshot(self):
        graph = FakeGraph(
            {
                "messages": [AIMessage(content="generated audit markdown")],
                "audit_run_id": "202",
                "audit_findings": [
                    {
                        "issue": "缺少验证记录",
                        "risk_level": "中",
                        "manual_check_required": True,
                    }
                ],
                "audit_verification": {"passed": True, "issues": []},
                "citation_map": {
                    1: {
                        "source": "VDA6.4.pdf",
                        "chapter": "4",
                        "section_title": "整改闭环",
                    }
                },
            }
        )
        request = api.AuditCheckRequest(
            session_id=self.session.id,
            audit_type="quality_issue",
            content="整改措施已完成",
        )

        with patch("api._get_owned_session", return_value=self.session), patch(
            "api.get_audit_graph",
            return_value=graph,
        ):
            response = await api.check_audit(
                request,
                user=self.user,
                db=SimpleNamespace(),
            )

        snapshot = _snapshot_with_ignored_fields(
            response.model_dump(),
            {"final_answer", "audit_run_id"},
        )
        self.assertEqual(
            snapshot,
            {
                "final_answer": "<ignored>",
                "audit_run_id": "<ignored>",
                "findings": [
                    {
                        "issue": "缺少验证记录",
                        "risk_level": "中",
                        "manual_check_required": True,
                    }
                ],
                "verify_result": {"passed": True, "issues": []},
                "references": [
                    {
                        "id": 1,
                        "source": "VDA6.4.pdf",
                        "chapter": "4",
                        "section_title": "整改闭环",
                    }
                ],
            },
        )
        self.assertEqual(_declared_status("/quality/audit/check", "POST"), 200)

    async def test_report_generate_response_snapshot(self):
        graph = FakeGraph(
            {
                "report_run_id": "303",
                "report_result": {
                    "final_markdown": "generated report markdown",
                    "verify_result": {"passed": True},
                    "references": [
                        {"source_type": "fmea", "source_id": "101"}
                    ],
                    "manual_check_items": ["确认客户特殊要求"],
                    "source_match_result": {
                        "matched": "yes",
                        "requires_manual_check": False,
                    },
                },
            }
        )
        request = api.ReportGenerateRequest(
            report_type="quality_issue_report",
            fmea_run_id="101",
        )

        with patch("api._ensure_owned_report_source_runs"), patch(
            "api.get_report_graph",
            return_value=graph,
        ):
            response = await api.generate_report(
                request,
                user=self.user,
                db=SimpleNamespace(),
            )

        snapshot = _snapshot_with_ignored_fields(
            response.model_dump(),
            {"final_markdown", "report_run_id"},
        )
        self.assertEqual(
            snapshot,
            {
                "final_markdown": "<ignored>",
                "report_run_id": "<ignored>",
                "verify_result": {"passed": True},
                "references": [
                    {"source_type": "fmea", "source_id": "101"}
                ],
                "manual_check_items": ["确认客户特殊要求"],
                "source_match_result": {
                    "matched": "yes",
                    "requires_manual_check": False,
                },
            },
        )
        self.assertEqual(_declared_status("/quality/report/generate", "POST"), 200)

    async def test_report_sources_response_snapshot(self):
        now = datetime(2026, 6, 8, 8, 0, tzinfo=timezone.utc)
        fmea_run = SimpleNamespace(
            id=101,
            user_id=self.user.id,
            title="拉延裂纹 FMEA",
            summary="覆盖件拉延裂纹风险分析",
            keywords_json=["拉延", "裂纹"],
            artifact_type="fmea_run",
            created_at=now,
            updated_at=now,
            output_json={"rows": [{"failure_mode": "裂纹"}]},
            product="覆盖件",
            process="拉延",
            failure_phenomenon="裂纹",
        )
        audit_run = SimpleNamespace(
            id=202,
            user_id=self.user.id,
            title="整改闭环审核",
            summary="审核整改记录完整性",
            keywords_json=["整改", "验证"],
            artifact_type="audit_run",
            created_at=now,
            updated_at=now,
            findings_json={"findings": [{"issue": "缺少验证记录"}]},
            audit_type="quality_issue",
            focus="整改闭环",
            content_text="检查整改证据",
        )
        db = FakeReportSourcesDB([fmea_run], [audit_run])

        response = api.list_report_sources(user=self.user, db=db)
        snapshot = response.model_dump()
        for group in ("fmea_runs", "audit_runs"):
            for item in snapshot[group]:
                item["id"] = "<ignored>"
                item["created_at"] = "<ignored>"
                item["updated_at"] = "<ignored>"

        self.assertEqual(
            snapshot,
            {
                "fmea_runs": [
                    {
                        "id": "<ignored>",
                        "title": "拉延裂纹 FMEA",
                        "summary": "覆盖件拉延裂纹风险分析",
                        "keywords_json": ["拉延", "裂纹"],
                        "artifact_type": "fmea_run",
                        "created_at": "<ignored>",
                        "updated_at": "<ignored>",
                    }
                ],
                "audit_runs": [
                    {
                        "id": "<ignored>",
                        "title": "整改闭环审核",
                        "summary": "审核整改记录完整性",
                        "keywords_json": ["整改", "验证"],
                        "artifact_type": "audit_run",
                        "created_at": "<ignored>",
                        "updated_at": "<ignored>",
                    }
                ],
            },
        )
        self.assertEqual(_declared_status("/quality/report/sources", "GET"), 200)

    async def test_current_error_status_mappings_are_frozen(self):
        fmea_request = api.FMEAGenerateRequest(
            session_id="missing",
            product="产品",
            process="工序",
            failure_phenomenon="问题",
        )
        audit_request = api.AuditCheckRequest(
            session_id="missing",
            audit_type="general",
            content="content",
        )
        report_request = api.ReportGenerateRequest(report_type="unsupported")

        with patch("api._get_owned_session", return_value=None):
            with self.assertRaises(HTTPException) as fmea_error:
                await api.generate_fmea(
                    fmea_request,
                    user=self.user,
                    db=SimpleNamespace(),
                )
            with self.assertRaises(HTTPException) as audit_error:
                await api.check_audit(
                    audit_request,
                    user=self.user,
                    db=SimpleNamespace(),
                )

        with self.assertRaises(HTTPException) as report_error:
            await api.generate_report(
                report_request,
                user=self.user,
                db=SimpleNamespace(),
            )

        self.assertEqual(fmea_error.exception.status_code, 404)
        self.assertEqual(audit_error.exception.status_code, 404)
        self.assertEqual(report_error.exception.status_code, 400)

    async def test_graph_exceptions_map_to_500_without_external_calls(self):
        cases = [
            (
                api.generate_fmea,
                api.FMEAGenerateRequest(
                    session_id=self.session.id,
                    product="产品",
                    process="工序",
                    failure_phenomenon="问题",
                ),
                "api.get_fmea_graph",
            ),
            (
                api.check_audit,
                api.AuditCheckRequest(
                    session_id=self.session.id,
                    audit_type="general",
                    content="content",
                ),
                "api.get_audit_graph",
            ),
        ]

        for endpoint, request, graph_getter in cases:
            with self.subTest(endpoint=endpoint.__name__), patch(
                "api._get_owned_session",
                return_value=self.session,
            ), patch(
                graph_getter,
                return_value=FakeGraph(error=RuntimeError("graph failed")),
            ):
                with self.assertRaises(HTTPException) as error:
                    await endpoint(
                        request,
                        user=self.user,
                        db=SimpleNamespace(),
                    )
                self.assertEqual(error.exception.status_code, 500)

        with patch("api._ensure_owned_report_source_runs"), patch(
            "api.get_report_graph",
            return_value=FakeGraph(error=RuntimeError("graph failed")),
        ):
            with self.assertRaises(HTTPException) as report_error:
                await api.generate_report(
                    api.ReportGenerateRequest(),
                    user=self.user,
                    db=SimpleNamespace(),
                )
        self.assertEqual(report_error.exception.status_code, 500)


if __name__ == "__main__":
    unittest.main()

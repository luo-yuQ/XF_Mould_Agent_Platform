import copy
import unittest
from unittest.mock import patch

from audit_graph import save_audit_run_node
from fmea_graph import save_fmea_run_node
from report_graph import save_report_run_node


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    def add(self, value):
        value.id = len(self.added) + 1
        self.added.append(value)

    def commit(self):
        self.committed = True

    def refresh(self, value):
        return None

    def rollback(self):
        self.rolled_back = True


class ArtifactMetadataPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_fmea_save_writes_metadata_and_preserves_retrieved_refs(self):
        db = FakeSession()
        citation_map = {
            1: {
                "source": "FMEA手册.pdf",
                "chapter": "风险分析",
                "section_title": "行动优先级",
                "chunk_uid": "fmea-1",
            }
        }
        original_refs = copy.deepcopy(citation_map)
        state = {
            "fmea_db_session": db,
            "fmea_user_id": 10,
            "fmea_session_id": "session-fmea",
            "fmea_input_raw": {"quality_case_id": "case-1"},
            "fmea_input": {
                "fmea_type": "PFMEA",
                "product": "座椅滑轨",
                "process": "冲压",
                "failure_phenomenon": "毛刺超标",
                "background": "",
            },
            "fmea_rows": [{
                "failure_mode": "边缘毛刺",
                "effect": "装配干涉",
                "cause": "模具间隙偏大",
                "recommended_action": "调整模具间隙",
                "action_priority": {"value": "H"},
                "rpn": 120,
            }],
            "fmea_markdown": "# PFMEA 分析报告",
            "fmea_verification": {"passed": True},
            "fmea_retrieval_queries": ["冲压 毛刺"],
            "citation_map": citation_map,
        }

        result = await save_fmea_run_node(state)
        run = db.added[0]

        self.assertTrue(db.committed)
        self.assertEqual(result["fmea_run_id"], "1")
        self.assertTrue(run.title)
        self.assertTrue(run.summary)
        self.assertIsInstance(run.keywords_json, list)
        self.assertEqual(run.artifact_type, "fmea_run")
        self.assertEqual(run.quality_case_id, "case-1")
        self.assertIn("模具间隙偏大", run.keywords_json)
        self.assertIsInstance(run.references_json, list)
        self.assertTrue(run.references_json)
        self.assertEqual(run.references_json[0]["source_id"], "1")
        self.assertEqual(run.retrieved_refs_json, original_refs)
        self.assertEqual(citation_map, original_refs)
        self.assertIsNotNone(run.updated_at)
        self.assertIsNotNone(run.updated_at.tzinfo)
        self.assertEqual(run.updated_at.utcoffset().total_seconds(), 0)
        self.assertEqual(run.created_at, run.updated_at)

    async def test_audit_save_writes_metadata_and_preserves_retrieved_refs(self):
        db = FakeSession()
        citation_map = {
            1: {
                "source": "VDA6.4.pdf",
                "chapter": "过程审核",
                "section_title": "整改闭环",
                "chunk_uid": "audit-1",
            }
        }
        original_refs = copy.deepcopy(citation_map)
        state = {
            "audit_db_session": db,
            "audit_user_id": 20,
            "audit_session_id": "session-audit",
            "audit_input_raw": {"quality_case_id": "case-2"},
            "audit_input": {
                "audit_type": "pfmea",
                "content": "整改措施未指定责任人。",
                "focus": "整改闭环",
                "background": "",
            },
            "audit_findings": [{
                "issue": "整改措施缺少责任人",
                "category": "整改措施不闭环",
                "risk_level": "高",
                "recommendation": "补充责任人和期限",
                "manual_check_required": True,
            }],
            "audit_markdown": "# 审核检查报告",
            "audit_verification": {"passed": True},
            "audit_retrieval_queries": ["整改闭环"],
            "citation_map": citation_map,
        }

        result = await save_audit_run_node(state)
        run = db.added[0]

        self.assertTrue(db.committed)
        self.assertEqual(result["audit_run_id"], "1")
        self.assertTrue(run.title)
        self.assertTrue(run.summary)
        self.assertIsInstance(run.keywords_json, list)
        self.assertEqual(run.artifact_type, "audit_run")
        self.assertEqual(run.quality_case_id, "case-2")
        self.assertIn("高", run.keywords_json)
        self.assertIsInstance(run.references_json, list)
        self.assertTrue(run.references_json)
        self.assertEqual(run.references_json[0]["source_id"], "1")
        self.assertEqual(run.retrieved_refs_json, original_refs)
        self.assertEqual(citation_map, original_refs)
        self.assertIsNotNone(run.updated_at)
        self.assertIsNotNone(run.updated_at.tzinfo)
        self.assertEqual(run.updated_at.utcoffset().total_seconds(), 0)
        self.assertEqual(run.created_at, run.updated_at)

    async def test_report_save_writes_metadata_and_source_match_result(self):
        db = FakeSession()
        state = {
            "report_db_session": db,
            "report_user_id": 30,
            "report_input": {
                "report_type": "quality_issue_report",
                "title": "冲压毛刺质量问题分析报告",
                "fmea_run_id": "11",
                "audit_run_id": "12",
                "extra_background": "客户装配反馈",
                "quality_case_id": "case-3",
            },
            "report_context": {
                "title": "冲压毛刺质量问题分析报告",
                "references": [{"source_type": "fmea", "source_id": "11"}],
            },
            "report_source_snapshot": {
                "fmea_source": {
                    "status": "found",
                    "product": "座椅滑轨",
                    "process": "冲压",
                    "failure_phenomenon": "毛刺超标",
                },
                "audit_source": {
                    "status": "found",
                    "findings_json": {
                        "findings": [{"issue": "检验记录不完整", "risk_level": "中"}]
                    },
                },
            },
            "report_markdown": "# 冲压毛刺质量问题分析报告",
            "report_verify_result": {"passed": True},
            "report_source_match_result": {
                "matched": "yes",
                "score": 80,
                "common_keywords": ["座椅滑轨", "冲压"],
                "fmea_keywords": ["座椅滑轨", "冲压"],
                "audit_keywords": ["座椅滑轨", "冲压"],
                "mismatch_reasons": [],
                "manual_check_required": False,
                "warning_message": "来源匹配提示：规则检查未发现明显冲突。",
            },
        }

        result = await save_report_run_node(state)
        run = db.added[0]

        self.assertTrue(db.committed)
        self.assertEqual(result["report_run_id"], "1")
        self.assertEqual(run.artifact_type, "report_run")
        self.assertEqual(run.quality_case_id, "case-3")
        self.assertTrue(run.summary)
        self.assertIsInstance(run.keywords_json, list)
        self.assertIn("质量问题：毛刺超标", run.summary)
        self.assertIn("检验记录不完整", run.keywords_json)
        self.assertIsInstance(run.source_match_result_json, dict)
        self.assertEqual(run.source_match_result_json["matched"], "yes")
        self.assertEqual(
            result["report_result"]["source_match_result"],
            run.source_match_result_json,
        )
        self.assertIsNotNone(run.updated_at)
        self.assertIsNotNone(run.updated_at.tzinfo)
        self.assertEqual(run.updated_at.utcoffset().total_seconds(), 0)
        self.assertEqual(run.created_at, run.updated_at)

    async def test_metadata_failure_does_not_block_saves(self):
        fmea_db = FakeSession()
        fmea_state = {
            "fmea_db_session": fmea_db,
            "fmea_user_id": 1,
            "fmea_session_id": "session-fmea",
            "fmea_input": {
                "fmea_type": "PFMEA",
                "product": "产品",
                "process": "工序",
                "failure_phenomenon": "问题",
                "background": "",
            },
            "fmea_rows": [],
            "citation_map": {},
        }
        audit_db = FakeSession()
        audit_state = {
            "audit_db_session": audit_db,
            "audit_user_id": 1,
            "audit_session_id": "session-audit",
            "audit_input": {
                "audit_type": "general",
                "content": "待审核内容",
                "focus": None,
                "background": None,
            },
            "audit_findings": [],
            "citation_map": {},
        }
        report_db = FakeSession()
        report_state = {
            "report_db_session": report_db,
            "report_user_id": 1,
            "report_input": {"report_type": "quality_issue_report"},
            "report_context": {"references": []},
            "report_source_snapshot": {},
            "report_markdown": "",
            "report_verify_result": {},
        }

        with patch("fmea_graph.build_fmea_metadata", side_effect=RuntimeError("metadata failed")):
            fmea_result = await save_fmea_run_node(fmea_state)
        with patch("audit_graph.build_audit_metadata", side_effect=RuntimeError("metadata failed")):
            audit_result = await save_audit_run_node(audit_state)
        with patch("report_graph.build_report_metadata", side_effect=RuntimeError("metadata failed")):
            report_result = await save_report_run_node(report_state)

        self.assertEqual(fmea_result["fmea_run_id"], "1")
        self.assertEqual(audit_result["audit_run_id"], "1")
        self.assertEqual(report_result["report_run_id"], "1")
        self.assertEqual(fmea_db.added[0].keywords_json, [])
        self.assertEqual(audit_db.added[0].references_json, [])
        self.assertEqual(report_db.added[0].summary, "")


if __name__ == "__main__":
    unittest.main()

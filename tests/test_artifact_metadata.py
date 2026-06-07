import copy
import unittest

from agents.artifact_metadata import (
    build_audit_metadata,
    build_fmea_metadata,
    build_references_summary,
    build_report_metadata,
)


class ArtifactMetadataTests(unittest.TestCase):
    def test_build_fmea_metadata_from_structured_data(self):
        refs = [{
            "chunk_uid": "chunk-1",
            "doc_source": "FMEA手册.pdf",
            "doc_chapter": "风险分析",
            "doc_section": "行动优先级",
            "text": "行动优先级应结合严重度、发生度和探测度判断。",
            "score": 0.92,
        }]
        original_refs = copy.deepcopy(refs)

        metadata = build_fmea_metadata(
            {
                "product": "座椅滑轨",
                "process": "冲压",
                "failure_phenomenon": "毛刺超标",
            },
            {
                "rows": [{
                    "failure_mode": "边缘毛刺",
                    "failure_effect": "装配干涉",
                    "potential_cause": "模具间隙偏大",
                    "recommended_action": "调整模具间隙",
                    "ap": {"value": "H"},
                    "rpn": 120,
                }],
                "manual_check_items": ["确认实测毛刺高度"],
            },
            retrieved_refs=refs,
        )

        self.assertEqual(metadata["artifact_type"], "fmea_run")
        self.assertEqual(metadata["title"], "座椅滑轨 - 冲压 - 边缘毛刺")
        self.assertIn("失效模式：边缘毛刺", metadata["summary"])
        self.assertIn("模具间隙偏大", metadata["keywords_json"])
        self.assertIsInstance(metadata["keywords_json"], list)
        self.assertEqual(metadata["references_json"][0]["source_id"], "chunk-1")
        self.assertEqual(refs, original_refs)

    def test_build_audit_metadata_marks_manual_findings(self):
        metadata = build_audit_metadata(
            {"audit_type": "pfmea", "focus": "整改闭环"},
            {
                "findings": [{
                    "issue": "整改措施缺少责任人",
                    "category": "整改措施不闭环",
                    "risk_level": "高",
                    "recommendation": "补充责任人和完成期限",
                    "manual_check_required": True,
                }]
            },
        )

        self.assertEqual(metadata["artifact_type"], "audit_run")
        self.assertEqual(metadata["title"], "pfmea - 整改措施缺少责任人")
        self.assertIn("审核发现：整改措施缺少责任人", metadata["summary"])
        self.assertIn("高", metadata["keywords_json"])

    def test_build_report_metadata_uses_source_snapshot(self):
        metadata = build_report_metadata(
            {"title": "冲压毛刺质量问题分析报告", "extra_background": "客户装配反馈"},
            source_snapshot={
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
        )

        self.assertEqual(metadata["artifact_type"], "report_run")
        self.assertIn("质量问题：毛刺超标", metadata["summary"])
        self.assertIn("检验记录不完整", metadata["keywords_json"])

    def test_missing_or_invalid_inputs_return_safe_shapes(self):
        fmea = build_fmea_metadata(None)
        audit = build_audit_metadata(object())
        report = build_report_metadata()

        self.assertEqual(fmea["title"], "FMEA分析")
        self.assertEqual(audit["title"], "审核检查")
        self.assertEqual(report["summary"], "报告：质量问题分析报告")
        self.assertEqual(fmea["references_json"], [])
        self.assertIsInstance(audit["keywords_json"], list)

    def test_reference_builder_accepts_wrapped_json_and_deduplicates(self):
        raw = {
            "retrieved_refs": [
                {"id": 7, "source": "VDA6.4", "section_title": "过程审核"},
                {"id": 7, "source": "VDA6.4", "section_title": "过程审核"},
            ]
        }

        references = build_references_summary(raw)

        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["source_id"], "7")
        self.assertEqual(references[0]["title"], "VDA6.4 / 过程审核")

    def test_reference_builder_accepts_citation_map(self):
        citation_map = {
            1: {
                "source": "FMEA手册.pdf",
                "chapter": "风险分析",
                "section_title": "严重度",
                "chunk_uid": "chunk-1",
            }
        }

        references = build_references_summary(citation_map)

        self.assertEqual(len(references), 1)
        self.assertEqual(references[0]["source_id"], "1")
        self.assertEqual(references[0]["source"], "FMEA手册.pdf")


if __name__ == "__main__":
    unittest.main()

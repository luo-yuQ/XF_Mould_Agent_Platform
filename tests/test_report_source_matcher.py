import unittest

from agents.report_source_matcher import check_report_source_match


class ReportSourceMatcherTests(unittest.TestCase):
    def test_missing_source_requires_manual_check(self):
        result = check_report_source_match(
            {"status": "found", "keywords_json": ["座椅滑轨", "冲压", "毛刺"]},
            None,
        )

        self.assertEqual(result["matched"], "uncertain")
        self.assertTrue(result["manual_check_required"])
        self.assertIn("Audit", result["warning_message"])

    def test_multiple_common_business_keywords_match(self):
        result = check_report_source_match(
            {
                "status": "found",
                "keywords_json": ["座椅滑轨", "冲压", "尺寸超差", "装配干涉"],
                "title": "座椅滑轨 - 冲压 - 尺寸超差",
            },
            {
                "status": "found",
                "keywords_json": ["座椅滑轨", "冲压", "尺寸超差", "整改闭环"],
                "summary": "审核发现装配尺寸超差，需完成整改闭环。",
            },
            "座椅滑轨冲压尺寸问题",
        )

        self.assertEqual(result["matched"], "yes")
        self.assertGreaterEqual(result["score"], 60)
        self.assertIn("座椅滑轨", result["common_keywords"])
        self.assertFalse(result["manual_check_required"])
        self.assertLess(result["score"], 100)

    def test_single_common_keyword_is_uncertain(self):
        result = check_report_source_match(
            {"status": "found", "keywords_json": ["注塑件A", "短射"]},
            {"status": "found", "keywords_json": ["模具B", "短射"]},
        )

        self.assertEqual(result["matched"], "uncertain")
        self.assertTrue(result["manual_check_required"])
        self.assertEqual(result["common_keywords"], ["短射"])

    def test_no_common_keyword_is_no(self):
        result = check_report_source_match(
            {"status": "found", "keywords_json": ["产品A", "冲压", "毛刺"]},
            {"status": "found", "keywords_json": ["产品B", "注塑", "缩水"]},
        )

        self.assertEqual(result["matched"], "no")
        self.assertEqual(result["score"], 0)
        self.assertTrue(result["manual_check_required"])
        self.assertTrue(result["mismatch_reasons"])

    def test_markdown_quality_terms_are_used_as_fallback(self):
        result = check_report_source_match(
            {"status": "found", "output_markdown": "发现短射并造成装配干涉。"},
            {"status": "found", "final_markdown": "审核确认短射，整改闭环不足。"},
        )

        self.assertIn("短射", result["common_keywords"])
        self.assertGreater(result["score"], 0)


if __name__ == "__main__":
    unittest.main()

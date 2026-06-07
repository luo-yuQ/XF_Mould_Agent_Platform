import unittest

from agents.report_agent import ensure_source_match_warning
from report_graph import report_source_match_node


class ReportSourceMatchIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_graph_node_uses_selected_sources_without_replacing_ids(self):
        state = {
            "report_input": {
                "report_type": "quality_issue_report",
                "fmea_run_id": "11",
                "audit_run_id": "12",
                "extra_background": "座椅滑轨冲压尺寸问题",
            },
            "report_fmea_source": {
                "status": "found",
                "run_id": "11",
                "keywords_json": ["座椅滑轨", "冲压", "尺寸超差"],
            },
            "report_audit_source": {
                "status": "found",
                "run_id": "12",
                "keywords_json": ["座椅滑轨", "冲压", "尺寸超差"],
            },
        }

        result = await report_source_match_node(state)

        self.assertEqual(result["report_source_match_result"]["matched"], "yes")
        self.assertEqual(result["report_input"]["fmea_run_id"], "11")
        self.assertEqual(result["report_input"]["audit_run_id"], "12")
        self.assertFalse(result["task_completed"])

    def test_manual_warning_is_inserted_in_required_section(self):
        warning = "来源匹配提示：所选来源缺少共同关键词，需人工确认。"
        markdown = (
            "# 报告\n\n"
            "## 需人工确认事项\n\n"
            "- 确认现场数据\n\n"
            "## 结论\n\n"
            "保持现有结论。"
        )

        updated = ensure_source_match_warning(
            markdown,
            {
                "manual_check_required": True,
                "warning_message": warning,
            },
        )

        manual_section = updated.split("## 需人工确认事项", 1)[1].split("## 结论", 1)[0]
        self.assertIn(warning, manual_section)
        self.assertEqual(updated.count(warning), 1)
        self.assertIn("## 结论", updated)

    def test_manual_warning_adds_missing_section(self):
        warning = "来源匹配提示：缺少 Audit 来源，需人工确认。"
        updated = ensure_source_match_warning(
            "# 报告\n\n## 结论\n\n结论内容。",
            {
                "manual_check_required": True,
                "warning_message": warning,
            },
        )

        self.assertIn("## 需人工确认事项", updated)
        self.assertIn(warning, updated)

    def test_no_manual_check_leaves_markdown_unchanged(self):
        markdown = "# 报告\n\n## 需人工确认事项\n\n- 暂无"

        updated = ensure_source_match_warning(
            markdown,
            {
                "manual_check_required": False,
                "warning_message": "不应写入",
            },
        )

        self.assertEqual(updated, markdown)


if __name__ == "__main__":
    unittest.main()

"""
Report Workflow MVP eval 测试脚本。

运行方式：
  python eval_cases/report/test_report.py
  python eval_cases/report/test_report.py case_001_full_sources

本脚本不访问真实数据库、不调用真实 RAG、不调用真实 LLM。它通过 case 中的
mock_sources / mock_markdown 验证 Report workflow 的编排和 verifier 规则。
"""
import asyncio
import json
import re
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, "/app")

CASES_DIR = Path(__file__).parent

FIXED_SECTIONS = [
    "问题背景",
    "分析对象与范围",
    "参考依据",
    "FMEA分析摘要",
    "审核发现摘要",
    "风险判断",
    "改进措施建议",
    "需人工确认事项",
    "结论",
]


def _section(markdown: str, heading: str) -> str:
    """提取指定 Markdown 章节内容。"""
    pattern = re.compile(rf"^##\s*{re.escape(heading)}\s*$", re.MULTILINE)
    match = pattern.search(markdown)
    if not match:
        return ""
    next_match = re.search(r"^##\s+.+$", markdown[match.end():], re.MULTILINE)
    end = match.end() + next_match.start() if next_match else len(markdown)
    return markdown[match.end():end].strip()


def _has_all_sections(markdown: str) -> bool:
    """检查固定章节是否全部存在。"""
    return all(f"## {heading}" in markdown for heading in FIXED_SECTIONS)


def _has_fabricated_clause(markdown: str) -> bool:
    """检查疑似编造标准条款、页码或章节编号。"""
    patterns = [
        r"第\s*[0-9一二三四五六七八九十]+(?:\.[0-9]+)*\s*条",
        r"第\s*[0-9一二三四五六七八九十]+(?:\.[0-9]+)*\s*章",
        r"[0-9]+(?:\.[0-9]+){1,3}\s*(?:条|章节|节)",
        r"(?:第\s*)?[0-9]+\s*页",
        r"clause\s+[0-9]+(?:\.[0-9]+)*",
        r"section\s+[0-9]+(?:\.[0-9]+)*",
    ]
    return any(re.search(pattern, markdown, flags=re.I) for pattern in patterns)


def _has_specific_sod_ap_values(markdown: str) -> bool:
    """检查是否出现具体 S/O/D/AP 数值。"""
    patterns = [
        r"\bS\s*[=:：]\s*\d+",
        r"\bO\s*[=:：]\s*\d+",
        r"\bD\s*[=:：]\s*\d+",
        r"\bAP\s*[=:：]\s*[HML]",
        r"严重度\s*[=:：]\s*\d+",
        r"发生度\s*[=:：]\s*\d+",
        r"探测度\s*[=:：]\s*\d+",
    ]
    return any(re.search(pattern, markdown, flags=re.I) for pattern in patterns)


async def run_case(case_path: Path) -> dict:
    """运行单个 report eval case。"""
    import report_graph

    case = json.loads(case_path.read_text(encoding="utf-8"))
    case_id = case.get("case_id", case_path.stem)
    inp = case["input"]
    expected = case.get("expected", {})
    errors: list[str] = []

    print(f"\n{'=' * 60}")
    print(f"[{case_id}] title={inp.get('title', '-')}")
    print(f"         fmea_run_id={inp.get('fmea_run_id')} audit_run_id={inp.get('audit_run_id')}")
    print(f"{'=' * 60}")

    original_load_sources = report_graph.load_report_sources
    original_generate = report_graph.generate_report_markdown
    original_repair = report_graph.repair_report_once

    def fake_load_sources(user_id, fmea_run_id=None, audit_run_id=None, db=None):
        """返回 case 中定义的模拟来源。"""
        return case["mock_sources"]

    async def fake_generate(report_context, skill_text):
        """返回 case 中定义的模拟报告。"""
        return case["mock_markdown"]

    async def fake_repair(report_context, final_markdown, verify_result, skill_text):
        """eval 中不扩展修复行为，直接返回原报告。"""
        return final_markdown

    report_graph.load_report_sources = fake_load_sources
    report_graph.generate_report_markdown = fake_generate
    report_graph.repair_report_once = fake_repair

    try:
        state = {
            "messages": [],
            "sender": "user",
            "next_agent": "report",
            "intent": "quality_issue_report",
            "agent_override": "",
            "rag_result": "",
            "rag_chunks": [],
            "citation_map": {},
            "citation_ids": [],
            "rag_is_relevant": False,
            "task_completed": False,
            "report_input_raw": inp,
            "report_user_id": 1001,
            "report_include_rag": False,
        }
        graph = report_graph.build_report_graph()
        final_state = await graph.ainvoke(state, config={"recursion_limit": 20})
    except Exception as exc:
        report_graph.load_report_sources = original_load_sources
        report_graph.generate_report_markdown = original_generate
        report_graph.repair_report_once = original_repair
        print(f"  [FAIL] workflow 执行异常: {exc}")
        return {"case_id": case_id, "passed": False, "errors": [str(exc)]}
    finally:
        report_graph.load_report_sources = original_load_sources
        report_graph.generate_report_markdown = original_generate
        report_graph.repair_report_once = original_repair

    markdown = final_state.get("report_markdown", "")
    verify_result = final_state.get("report_verify_result", {})
    sources = final_state.get("report_sources", {})
    source_match_result = final_state.get("report_source_match_result", {})
    report_result = final_state.get("report_result", {})

    if expected.get("report_generated") and (
        not markdown.strip() or final_state.get("report_error")
    ):
        errors.append("来源匹配检查阻止了报告生成")

    matched_in = expected.get("source_match_matched_in")
    if matched_in and source_match_result.get("matched") not in matched_in:
        errors.append(
            f"source match={source_match_result.get('matched')}，"
            f"期望属于 {matched_in}"
        )

    if (
        expected.get("common_keywords_non_empty")
        and not source_match_result.get("common_keywords")
    ):
        errors.append("source match 未返回共同关键词")

    manual_required = expected.get("manual_check_required")
    if (
        manual_required is not None
        and source_match_result.get("manual_check_required") is not manual_required
    ):
        errors.append(
            "source match 的 manual_check_required 与期望不一致"
        )

    if expected.get("source_match_warning_in_manual_items"):
        warning = source_match_result.get("warning_message", "")
        manual_items = report_result.get("manual_check_items", [])
        if not warning or not any(warning in item for item in manual_items):
            errors.append("报告需人工确认事项未包含来源匹配提醒")

    if expected.get("required_sections") and not _has_all_sections(markdown):
        errors.append("报告缺少固定章节")

    fmea_expected = expected.get("fmea_summary_from_fmea_run")
    if fmea_expected and fmea_expected not in _section(markdown, "FMEA分析摘要"):
        errors.append("FMEA分析摘要未体现 fmea_run 来源内容")

    audit_expected = expected.get("audit_summary_from_audit_run")
    if audit_expected and audit_expected not in _section(markdown, "审核发现摘要"):
        errors.append("审核发现摘要未体现 audit_run 来源内容")

    audit_missing_notice = expected.get("audit_missing_notice")
    if audit_missing_notice and audit_missing_notice not in _section(markdown, "审核发现摘要"):
        errors.append("缺少审核结果缺失提示")

    fmea_missing_notice = expected.get("fmea_missing_notice")
    if fmea_missing_notice and fmea_missing_notice not in _section(markdown, "FMEA分析摘要"):
        errors.append("缺少 FMEA 结果缺失提示")

    if expected.get("manual_check_notice") and "需人工确认" not in markdown:
        errors.append("报告未包含需人工确认提示")

    manual_min = expected.get("manual_check_notice_count_min")
    if manual_min is not None and markdown.count("需人工确认") < int(manual_min):
        errors.append(f"需人工确认提示少于 {manual_min} 处")

    if expected.get("no_fabricated_clause") and _has_fabricated_clause(markdown):
        errors.append("报告疑似编造标准条款、页码或章节编号")

    if expected.get("no_specific_sod_ap_values") and _has_specific_sod_ap_values(markdown):
        errors.append("背景草稿中出现具体 S/O/D/AP 数值")

    if expected.get("no_fabricated_audit_finding"):
        audit_section = _section(markdown, "审核发现摘要")
        if "未提供审核检查结果" not in audit_section or "审核发现为" in audit_section:
            errors.append("Audit 缺失时疑似编造 audit finding")

    if expected.get("no_fabricated_fmea"):
        fmea_section = _section(markdown, "FMEA分析摘要")
        if "未提供FMEA分析结果" not in fmea_section or "失效模式" in fmea_section:
            errors.append("FMEA 缺失时疑似编造 FMEA")

    leaked = expected.get("no_other_user_data_leak")
    if leaked and leaked in markdown:
        errors.append("报告泄露了其他用户数据")

    if expected.get("reject_or_not_found"):
        fmea_status = sources.get("fmea_source", {}).get("status")
        audit_status = sources.get("audit_source", {}).get("status")
        if fmea_status != "not_found" or audit_status != "not_found":
            errors.append("权限 case 未返回 not_found 来源状态")

    passed = not errors
    print(f"  verifier passed={verify_result.get('passed')}")
    print(f"  结果: {'PASS' if passed else 'FAIL'}")
    for error in errors:
        print(f"    - {error}")

    return {
        "case_id": case_id,
        "passed": passed,
        "verify_passed": verify_result.get("passed", False),
        "source_match": source_match_result.get("matched"),
        "errors": errors,
    }


async def main():
    """运行全部或指定 report eval case。"""
    if len(sys.argv) > 1:
        case_files = [CASES_DIR / f"{sys.argv[1]}.json"]
    else:
        case_files = sorted(CASES_DIR.glob("case_*.json"))

    if not case_files:
        print("没有找到 report eval case")
        sys.exit(1)

    results = []
    for case_file in case_files:
        if not case_file.exists():
            print(f"用例不存在: {case_file}")
            continue
        results.append(await run_case(case_file))

    print(f"\n{'=' * 60}")
    print("汇总")
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"  {result['case_id']}: {status} "
            f"(verify={result.get('verify_passed')}, "
            f"source_match={result.get('source_match')})"
        )
    print(f"\n总计: {passed}/{total} 通过")

    if passed != total:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

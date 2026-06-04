"""
Audit Agent 端到端测试脚本。

在 docker 容器内运行: docker exec mould-backend python eval_cases/audit/test_audit.py
或单跑某个 case:       docker exec mould-backend python eval_cases/audit/test_audit.py case_001_quality_issue
"""
import asyncio
import json
import re
import sys
from pathlib import Path

# 兼容 docker 容器路径和本地从项目根目录运行
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, "/app")

CASES_DIR = Path(__file__).parent

GENERIC_RECOMMENDATIONS = {
    "加强管理",
    "提高意识",
    "加强培训",
    "完善流程",
    "持续改进",
    "加强管控",
}


async def run_case(case_path: Path) -> dict:
    """运行单个 audit eval case，返回测试结果。"""
    from audit_graph import build_audit_graph
    from langchain_core.messages import HumanMessage

    case = json.loads(case_path.read_text(encoding="utf-8"))
    case_id = case.get("case_id", case_path.stem)
    inp = case["input"]

    print(f"\n{'=' * 60}")
    print(f"[{case_id}] audit_type={inp['audit_type']}  focus={inp.get('focus', '-')}")
    print(f"         content={inp.get('content', '')[:80]}...")
    print(f"{'=' * 60}")

    state = {
        "messages": [HumanMessage(content=json.dumps(inp, ensure_ascii=False), name="user")],
        "sender": "user",
        "next_agent": "audit",
        "intent": "audit_check",
        "agent_override": "",
        "rag_result": "",
        "rag_chunks": [],
        "citation_map": {},
        "citation_ids": [],
        "rag_is_relevant": False,
        "task_completed": False,
        "audit_input_raw": inp,
    }

    graph = build_audit_graph()
    try:
        final_state = await graph.ainvoke(state, config={"recursion_limit": 20})
    except Exception as e:
        print(f"  [FAIL] Graph 执行异常: {e}")
        return {"case_id": case_id, "passed": False, "error": str(e)}

    findings = final_state.get("audit_findings", [])
    markdown = final_state.get("audit_markdown", "")
    verification = final_state.get("audit_verification", {})
    errors = []

    if not findings:
        errors.append("未生成任何审核发现")
    else:
        print(f"  生成了 {len(findings)} 条审核发现")

    required_fields = case.get("expected_required_fields", [])
    for i, finding in enumerate(findings):
        for field in required_fields:
            val = finding.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(f"Finding[{i}] 缺少字段: {field}")

    if case.get("expected_manual_check_notice"):
        has_manual_notice = False
        for finding in findings:
            if finding.get("manual_check_required") is True:
                has_manual_notice = True
            for field in ("risk_level", "basis", "risk_explanation", "evidence_from_input"):
                text = finding.get(field, "")
                if isinstance(text, str) and "需人工确认" in text:
                    has_manual_notice = True
        if not has_manual_notice:
            errors.append("未体现需人工确认提示")

    if case.get("expected_no_fabricated_clause"):
        pattern = re.compile(
            r"(根据|依据|参照)?第\s*[A-Za-z0-9一二三四五六七八九十百千万点.\-_/]+\s*(条|章|节|款|项|页)"
            r"|某标准明确要求|标准明确要求"
        )
        for i, finding in enumerate(findings):
            for field in ("basis", "risk_explanation", "recommendation"):
                text = finding.get(field, "")
                if isinstance(text, str) and pattern.search(text):
                    errors.append(f"Finding[{i}] {field} 疑似编造标准条款")

    if case.get("expected_recommendation_not_empty"):
        for i, finding in enumerate(findings):
            recommendation = str(finding.get("recommendation") or "").strip()
            compact = re.sub(r"\s+", "", recommendation)
            if not recommendation:
                errors.append(f"Finding[{i}] recommendation 为空")
            elif compact in GENERIC_RECOMMENDATIONS:
                errors.append(f"Finding[{i}] recommendation 过于空泛: {recommendation}")

    verify_passed = verification.get("passed", False)
    verify_issues = verification.get("issues", [])
    if verify_issues:
        print(f"  verifier 发现 {len(verify_issues)} 个问题")
        for issue in verify_issues[:5]:
            print(f"    - {issue}")

    if not markdown or len(markdown) < 100:
        errors.append("Markdown 输出为空或过短")

    passed = len(errors) == 0
    print(f"\n  结果: {'PASS' if passed else 'FAIL'}")
    if errors:
        for err in errors:
            print(f"    - {err}")

    if markdown:
        preview = markdown[:500].replace("\n", "\n  ")
        print(f"\n  Markdown 预览:\n  {preview}...")

    return {
        "case_id": case_id,
        "passed": passed,
        "finding_count": len(findings),
        "verify_passed": verify_passed,
        "errors": errors,
    }


async def main():
    if len(sys.argv) > 1:
        case_files = [CASES_DIR / f"{sys.argv[1]}.json"]
    else:
        case_files = sorted(CASES_DIR.glob("case_*.json"))

    if not case_files:
        print("没有找到测试用例")
        sys.exit(1)

    results = []
    for cf in case_files:
        if not cf.exists():
            print(f"用例不存在: {cf}")
            continue
        result = await run_case(cf)
        results.append(result)

    print(f"\n{'=' * 60}")
    print("汇总")
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(
            f"  {r['case_id']}: {status} "
            f"(findings={r.get('finding_count', 0)}, verify={r.get('verify_passed', '-')})"
        )
    print(f"\n总计: {passed}/{total} 通过")


if __name__ == "__main__":
    asyncio.run(main())

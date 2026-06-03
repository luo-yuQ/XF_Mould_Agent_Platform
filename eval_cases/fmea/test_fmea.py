"""
FMEA Agent 端到端测试脚本。
在 docker 容器内运行: docker exec mould-backend python eval_cases/fmea/test_fmea.py
或单跑某个 case:       docker exec mould-backend python eval_cases/fmea/test_fmea.py case_001
"""
import asyncio
import json
import sys
from pathlib import Path

# 确保能 import 到项目根目录的模块
sys.path.insert(0, "/app")

CASES_DIR = Path(__file__).parent


async def run_case(case_path: Path) -> dict:
    """运行单个 eval case，返回测试结果。"""
    from fmea_graph import build_fmea_graph
    from langchain_core.messages import HumanMessage

    case = json.loads(case_path.read_text(encoding="utf-8"))
    case_id = case["case_id"]
    inp = case["input"]

    print(f"\n{'='*60}")
    print(f"[{case_id}] product={inp['product']}  process={inp['process']}")
    print(f"         phenomenon={inp.get('failure_phenomenon', '-')}  background={inp.get('background', '-')}")
    print(f"{'='*60}")

    # 构建初始 state
    state = {
        "messages": [HumanMessage(content=json.dumps(inp, ensure_ascii=False))],
        "fmea_input_raw": inp,
    }

    # 运行 FMEA graph
    graph = build_fmea_graph()
    try:
        final_state = await graph.ainvoke(state, config={"recursion_limit": 20})
    except Exception as e:
        print(f"  [FAIL] Graph 执行异常: {e}")
        return {"case_id": case_id, "passed": False, "error": str(e)}

    # 提取结果
    rows = final_state.get("fmea_rows", [])
    markdown = final_state.get("fmea_markdown", "")
    verification = final_state.get("fmea_verification", {})
    errors = []

    # 检查 1: 是否生成了行
    if not rows:
        errors.append("未生成任何 FMEA 行")
    else:
        print(f"  生成了 {len(rows)} 行 FMEA")

    # 检查 2: 每行必填字段
    required_fields = case.get("expected_required_fields", [])
    for i, row in enumerate(rows):
        for field in required_fields:
            val = row.get(field)
            if not val or (isinstance(val, str) and not val.strip()):
                errors.append(f"Row[{i}] 缺少字段: {field}")

    # 检查 3: S/O/D 标记为建议值
    if case.get("expected_manual_check_notice"):
        for i, row in enumerate(rows):
            sev = row.get("severity", {})
            occ = row.get("occurrence", {})
            det = row.get("detection", {})
            for score_name, score in [("severity", sev), ("occurrence", occ), ("detection", det)]:
                if isinstance(score, dict) and not score.get("suggested"):
                    errors.append(f"Row[{i}] {score_name} 未标记 suggested=true")

    # 检查 4: 不得编造标准条款
    if case.get("expected_no_fabricated_clause"):
        import re
        pattern = re.compile(r"根据第.{1,5}条|依据第.{1,5}条|标准第.{1,5}条")
        for i, row in enumerate(rows):
            for field in ["evidence", "recommended_action"]:
                text = row.get(field, "")
                if isinstance(text, str) and pattern.search(text):
                    errors.append(f"Row[{i}] {field} 疑似编造标准条款")

    # 检查 5: 验证器结果
    verify_passed = verification.get("passed", False)
    verify_issues = verification.get("issues", [])
    if verify_issues:
        print(f"  验证器发现 {len(verify_issues)} 个问题:")
        for issue in verify_issues[:5]:
            print(f"    - {issue}")

    # 检查 6: Markdown 输出非空
    if not markdown or len(markdown) < 100:
        errors.append("Markdown 输出为空或过短")

    passed = len(errors) == 0
    print(f"\n  结果: {'PASS ✓' if passed else 'FAIL ✗'}")
    if errors:
        for err in errors:
            print(f"    ✗ {err}")

    # 打印前几行 markdown 预览
    if markdown:
        preview = markdown[:500].replace("\n", "\n  ")
        print(f"\n  Markdown 预览:\n  {preview}...")

    return {
        "case_id": case_id,
        "passed": passed,
        "row_count": len(rows),
        "verify_passed": verify_passed,
        "errors": errors,
    }


async def main():
    # 确定要跑哪些 case
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

    # 汇总
    print(f"\n{'='*60}")
    print("汇总:")
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  {r['case_id']}: {status} (rows={r.get('row_count', 0)}, verify={r.get('verify_passed', '-')})")
    print(f"\n总计: {passed}/{total} 通过")


if __name__ == "__main__":
    asyncio.run(main())

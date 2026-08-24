from agents.sales_reviewer import run_sales_reviewer


def _citation():
    return {
        "citation_id": "source-001",
        "source_type": "text",
        "source_name": "测试手册",
    }


def _analysis(role):
    is_rd = role == "rd"
    return {
        "summary": "技术风险分析。" if is_rd else "质量保障分析。",
        "claims": [
            {
                "claim_id": f"{role}-claim",
                "text": "需要验证成型窗口。" if is_rd else "需要建立过程质量门。",
                "citations": [_citation()],
                "confidence": "medium",
                "requires_manual_check": False,
            }
        ],
        "risks": [
            {
                "risk_id": f"{role}-risk",
                "category": "process" if is_rd else "quality",
                "description": "存在待确认风险。",
                "citations": [_citation()],
                "requires_manual_check": False,
            }
        ],
        "recommendations": [
            {
                "recommendation_id": f"{role}-rec",
                "text": "执行验证。" if is_rd else "保存审核证据。",
                "citations": [_citation()],
                "requires_manual_check": False,
            }
        ],
        "missing_information": [],
        "citations": [_citation()],
        "confidence": "medium",
    }


def _review(rd=None, quality=None):
    return run_sales_reviewer(
        user_request="生成联合售前方案。",
        execution_plan=[],
        rd_analysis=_analysis("rd") if rd is None else rd,
        quality_analysis=_analysis("quality") if quality is None else quality,
    )


def test_reviewer_fails_when_specialist_analysis_is_missing():
    output = _review(rd={})

    assert output.passed is False
    assert "技术与工艺风险" in output.missing_sections


def test_reviewer_marks_uncited_strong_claim():
    rd = _analysis("rd")
    rd["claims"][0]["citations"] = []

    output = _review(rd=rd)

    assert output.passed is False
    assert any("rd-claim" in item for item in output.unsupported_claims)


def test_reviewer_marks_rd_quality_capability_overreach():
    rd = _analysis("rd")
    rd["claims"][0]["text"] = "公司质量体系完善并已通过 VDA 认证。"

    output = _review(rd=rd)

    assert output.passed is False
    assert any("R&D 越权" in item for item in output.conflicts)


def test_reviewer_marks_quality_technical_solution_overreach():
    quality = _analysis("quality")
    quality["claims"][0]["text"] = "模具结构采用四工位方案，冲压间隙设定为固定值。"

    output = _review(quality=quality)

    assert output.passed is False
    assert any("Quality 越权" in item for item in output.conflicts)


def test_reviewer_passes_normal_supported_inputs():
    output = _review()

    assert output.passed is True
    assert output.conflicts == []
    assert output.unsupported_claims == []
    assert output.missing_sections == []


def test_reviewer_marks_zero_defect_overcommitment_for_manual_approval():
    output = run_sales_reviewer(
        user_request="请直接承诺一定可以保证零缺陷量产。",
        execution_plan=[],
        rd_analysis=_analysis("rd"),
        quality_analysis=_analysis("quality"),
    )

    assert output.passed is False
    assert any("过度承诺风险" in item for item in output.conflicts)
    assert any("合同责任人" in item for item in output.manual_check_items)

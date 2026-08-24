from agents.sales_proposal_writer import REPORT_HEADINGS, run_sales_proposal_writer


class FakeStructuredLLM:
    def __init__(self, output):
        self.output = output

    def with_structured_output(self, _schema, **kwargs):
        return self

    def invoke(self, _messages):
        return self.output


def _citation(citation_id, source):
    return {
        "citation_id": citation_id,
        "source_type": "text",
        "source_name": source,
        "title": "测试章节",
    }


def _analysis(role):
    is_rd = role == "rd"
    citation = _citation(
        "rd-source" if is_rd else "quality-source",
        "FMEA手册" if is_rd else "VDA6.4手册",
    )
    return {
        "summary": "技术风险需验证。" if is_rd else "质量保障需建立质量门。",
        "claims": [
            {
                "claim_id": f"{role}-claim",
                "text": "材料窗口需要验证。" if is_rd else "审核记录需要保存。",
                "citations": [citation],
                "confidence": "medium",
            }
        ],
        "risks": [
            {
                "risk_id": f"{role}-risk",
                "category": role,
                "description": "试模数据不足。" if is_rd else "验收口径未确认。",
                "citations": [citation],
            }
        ],
        "recommendations": [
            {
                "recommendation_id": f"{role}-rec",
                "text": "安排试模验证。" if is_rd else "建立质量证据清单。",
                "citations": [citation],
            }
        ],
        "missing_information": [
            {
                "item_id": f"{role}-missing",
                "question": "请补充材料参数。" if is_rd else "请确认验收标准。",
                "reason": "需要确认",
            }
        ],
        "citations": [citation],
        "confidence": "medium",
    }


def _write(review_result=None, llm_output=None):
    return run_sales_proposal_writer(
        user_request="开发汽车覆盖件冲压模具。",
        execution_plan=[],
        rd_analysis=_analysis("rd"),
        quality_analysis=_analysis("quality"),
        review_result=review_result
        or {
            "passed": True,
            "conflicts": [],
            "unsupported_claims": [],
            "missing_sections": [],
            "manual_check_items": ["确认目标产能"],
            "repair_instructions": [],
        },
        llm=FakeStructuredLLM(
            llm_output
            or {
                "rd_claim_ids": ["rd-claim"],
                "rd_risk_ids": ["rd-risk"],
                "rd_recommendation_ids": ["rd-rec"],
                "quality_claim_ids": ["quality-claim"],
                "quality_risk_ids": ["quality-risk"],
                "quality_recommendation_ids": ["quality-rec"],
            }
        ),
    )


def test_writer_outputs_six_fixed_sections():
    output = _write()

    assert all(heading in output.final_report for heading in REPORT_HEADINGS)


def test_writer_includes_manual_check_items():
    output = _write()

    assert "确认目标产能" in output.final_report


def test_writer_preserves_conflicts_and_unsupported_claims():
    output = _write(
        {
            "passed": False,
            "conflicts": ["技术与质量结论冲突"],
            "unsupported_claims": ["质量能力声明缺少依据"],
            "missing_sections": [],
            "manual_check_items": [],
            "repair_instructions": ["补充依据"],
        }
    )

    assert "冲突：技术与质量结论冲突" in output.final_report
    assert "无依据声明：质量能力声明缺少依据" in output.final_report


def test_writer_renders_specialist_citations():
    output = _write()

    assert "[rd-source] FMEA手册" in output.final_report
    assert "[quality-source] VDA6.4手册" in output.final_report
    assert {citation.citation_id for citation in output.citations} == {
        "rd-source",
        "quality-source",
    }


def test_writer_cannot_add_unknown_key_fact_from_llm_selection():
    output = _write(
        llm_output={
            "rd_claim_ids": ["unknown-production-claim"],
            "rd_risk_ids": [],
            "rd_recommendation_ids": [],
            "quality_claim_ids": [],
            "quality_risk_ids": [],
            "quality_recommendation_ids": [],
            "invented_fact": "承诺年产一百万套",
        }
    )

    assert "承诺年产一百万套" not in output.final_report
    assert "unknown-production-claim" not in output.final_report
    assert "材料窗口需要验证" in output.final_report


def test_writer_reframes_zero_defect_request_without_making_commitment():
    output = run_sales_proposal_writer(
        user_request="请保证零缺陷量产。",
        execution_plan=[],
        rd_analysis=_analysis("rd"),
        quality_analysis=_analysis("quality"),
        review_result={
            "passed": False,
            "conflicts": ["客户请求包含过度承诺风险：保证零缺陷"],
            "unsupported_claims": [],
            "missing_sections": [],
            "manual_check_items": ["质量承诺需合同责任人确认。"],
            "repair_instructions": ["改写为待审批事项。"],
        },
        llm=FakeStructuredLLM({}),
    )

    assert "当前售前方案不作零缺陷或绝对结果保证" in output.final_report
    assert "\n请保证零缺陷量产。\n" not in output.final_report

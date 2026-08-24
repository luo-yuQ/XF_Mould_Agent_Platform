import pytest

from agents.sales_quality_specialist import run_sales_quality_specialist
from agents.sales_rd_specialist import run_sales_rd_specialist
from config import MILVUS_COLLECTION_FMEA, MILVUS_COLLECTION_QUALITY
from schemas.sales_collaboration import SpecialistOutput


class FakeStructuredLLM:
    def __init__(self, output):
        self.output = output
        self.messages = None
        self.schema = None

    def with_structured_output(self, schema, **kwargs):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.messages = messages
        return self.output


def _plan():
    return [
        {
            "task_id": "rd_analysis",
            "agent": "rd",
            "objective": "分析技术与工艺风险",
            "required_sources": ["fmea_manual"],
            "depends_on": [],
            "required": True,
        },
        {
            "task_id": "quality_analysis",
            "agent": "quality",
            "objective": "分析质量保障方式",
            "required_sources": ["xf_vda_manual"],
            "depends_on": [],
            "required": True,
        },
    ]


def _structured_output(*, role: str, citation_id: str, confidence: str = "medium"):
    is_rd = role == "rd"
    return {
        "summary": "识别出技术与工艺风险。" if is_rd else "形成质量保障分析。",
        "claims": [
            {
                "claim_id": f"{role}-claim-001",
                "text": "需要建立工艺验证窗口。" if is_rd else "需要建立过程质量门。",
                "citations": [
                    {
                        "citation_id": citation_id,
                        "source_type": "hallucinated",
                        "source_name": "hallucinated",
                    }
                ],
                "confidence": confidence,
                "requires_manual_check": False,
            }
        ],
        "risks": [
            {
                "risk_id": f"{role}-risk-001",
                "category": "process" if is_rd else "quality_assurance",
                "description": (
                    "关键成型参数缺少验证。"
                    if is_rd
                    else "审核和过程控制证据可能不完整。"
                ),
                "citations": [
                    {
                        "citation_id": citation_id,
                        "source_type": "hallucinated",
                        "source_name": "hallucinated",
                    }
                ],
                "requires_manual_check": True,
            }
        ],
        "recommendations": [
            {
                "recommendation_id": f"{role}-rec-001",
                "text": "执行工艺验证。" if is_rd else "建立质量保障和审核证据清单。",
                "citations": [
                    {
                        "citation_id": citation_id,
                        "source_type": "hallucinated",
                        "source_name": "hallucinated",
                    }
                ],
                "requires_manual_check": False,
            }
        ],
        "missing_information": [],
        "citations": [
            {
                "citation_id": citation_id,
                "source_type": "hallucinated",
                "source_name": "hallucinated",
            }
        ],
        "confidence": confidence,
    }


def test_rd_specialist_uses_fmea_retrieval_and_maps_citations():
    calls = []
    chunks = [
        {
            "chunk_uid": "fmea-chunk-001",
            "text": "应识别潜在失效并规划预防和探测控制。",
            "doc_source": "FMEA手册",
            "doc_chapter": "3",
            "doc_section": "风险分析",
            "heading_path": "3 > 风险分析",
            "chunk_type": "text",
        }
    ]

    def retriever(query, collection):
        calls.append((query, collection))
        return chunks

    llm = FakeStructuredLLM(
        _structured_output(role="rd", citation_id="fmea-chunk-001")
    )
    output = run_sales_rd_specialist(
        user_request="分析冲压模具技术风险。",
        customer_context={"material": "DP780"},
        execution_plan=_plan(),
        retriever=retriever,
        llm=llm,
    )

    assert isinstance(output, SpecialistOutput)
    assert calls[0][1] == MILVUS_COLLECTION_FMEA
    assert "DP780" in calls[0][0]
    assert output.risks
    assert "技术与工艺风险" in output.summary
    assert output.citations[0].citation_id == "fmea-chunk-001"
    assert output.citations[0].source_name == "FMEA手册"
    assert output.claims[0].citations[0].source_type == "text"
    assert llm.schema is SpecialistOutput
    assert "不生成正式 DFMEA/PFMEA 表格" in llm.messages[0].content


def test_quality_specialist_uses_quality_retrieval_and_maps_citations():
    calls = []
    chunks = [
        {
            "chunk_uid": "quality-chunk-001",
            "text": "过程应规定审核、监视、测量和记录控制要求。",
            "doc_source": "XF模具VDA6.4质量手册",
            "doc_chapter": "8",
            "doc_section": "过程控制",
            "heading_path": "8 > 过程控制",
            "chunk_type": "text",
        }
    ]

    def retriever(query, collection):
        calls.append((query, collection))
        return chunks

    llm = FakeStructuredLLM(
        _structured_output(role="quality", citation_id="quality-chunk-001")
    )
    output = run_sales_quality_specialist(
        user_request="说明项目质量保障和审核安排。",
        customer_context={"customer": "测试客户"},
        execution_plan=_plan(),
        retriever=retriever,
        llm=llm,
    )

    assert isinstance(output, SpecialistOutput)
    assert calls[0][1] == MILVUS_COLLECTION_QUALITY
    assert "测试客户" in calls[0][0]
    assert output.risks
    assert "质量保障分析" in output.summary
    assert output.citations[0].citation_id == "quality-chunk-001"
    assert output.citations[0].source_name == "XF模具VDA6.4质量手册"
    assert output.recommendations[0].citations[0].chunk_id == "quality-chunk-001"
    assert llm.schema is SpecialistOutput
    assert "不生成正式 Audit 报告" in llm.messages[0].content


@pytest.mark.parametrize(
    ("runner", "role"),
    [
        (run_sales_rd_specialist, "rd"),
        (run_sales_quality_specialist, "quality"),
    ],
)
def test_specialist_without_retrieval_results_downgrades_output(runner, role):
    llm = FakeStructuredLLM(
        _structured_output(role=role, citation_id="invented-source", confidence="high")
    )

    output = runner(
        user_request="生成售前分析。",
        customer_context={},
        execution_plan=_plan(),
        retriever=lambda _query, _collection: [],
        llm=llm,
    )

    assert output.citations == []
    assert output.confidence != "high"
    assert output.missing_information
    assert all(not claim.citations for claim in output.claims)
    assert all(not risk.citations for risk in output.risks)
    assert all(not recommendation.citations for recommendation in output.recommendations)


import pytest
from pydantic import ValidationError

from schemas.sales_collaboration import (
    Citation,
    Claim,
    PlannerOutput,
    PlannerTask,
    ReviewerOutput,
    SpecialistOutput,
)


def test_planner_output_accepts_valid_data():
    output = PlannerOutput(
        tasks=[
            {
                "task_id": "task-1",
                "agent": "rd",
                "objective": "Assess product feasibility.",
                "required_sources": ["customer-requirements"],
            }
        ],
        rationale="Technical assessment is required before drafting.",
        complexity="collaboration",
    )

    assert output.tasks[0].agent == "rd"
    assert output.tasks[0].depends_on == []
    assert output.warnings == []


def test_planner_task_rejects_unknown_agent():
    with pytest.raises(ValidationError):
        PlannerTask(
            task_id="task-1",
            agent="unknown",
            objective="Perform an unsupported task.",
        )


def test_specialist_output_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        SpecialistOutput(summary="Assessment complete.", confidence="certain")


def test_specialist_output_requires_summary():
    with pytest.raises(ValidationError):
        SpecialistOutput(confidence="high")


def test_reviewer_output_accepts_valid_data():
    output = ReviewerOutput(
        passed=False,
        conflicts=["RD and quality conclusions differ."],
        unsupported_claims=["claim-2"],
        missing_sections=["Commercial impact"],
        manual_check_items=["Confirm the customer tolerance."],
        repair_instructions=["Reconcile the conflicting conclusions."],
    )

    assert output.passed is False
    assert output.unsupported_claims == ["claim-2"]


def test_citation_accepts_minimum_required_fields():
    citation = Citation(
        citation_id="citation-1",
        source_type="document",
        source_name="customer-requirements.pdf",
    )

    assert citation.title is None
    assert citation.page is None
    assert citation.chunk_id is None
    assert citation.quote is None


def test_output_schema_field_names_are_stable():
    assert set(PlannerOutput.model_fields) == {
        "tasks",
        "rationale",
        "complexity",
        "warnings",
    }
    assert set(SpecialistOutput.model_fields) == {
        "summary",
        "claims",
        "risks",
        "recommendations",
        "missing_information",
        "citations",
        "confidence",
    }
    assert set(ReviewerOutput.model_fields) == {
        "passed",
        "conflicts",
        "unsupported_claims",
        "missing_sections",
        "manual_check_items",
        "repair_instructions",
    }


def test_list_defaults_are_not_shared_between_instances():
    first = SpecialistOutput(summary="First.", confidence="high")
    second = SpecialistOutput(summary="Second.", confidence="low")

    first.claims.append(
        Claim(
            claim_id="claim-1",
            text="A claim added after validation.",
            confidence="medium",
        )
    )

    assert second.claims == []

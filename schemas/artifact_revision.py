"""业务产物追改与版本记录 API/服务契约。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ArtifactType = Literal["fmea", "audit", "report"]


class ArtifactRevisionInput(BaseModel):
    artifact_type: ArtifactType
    base_version_id: str = Field(min_length=1, max_length=64)
    revision_instruction: str = Field(max_length=4000)

    @field_validator("base_version_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("revision_instruction")
    @classmethod
    def strip_revision_instruction(cls, value: str) -> str:
        return value.strip()


class ArtifactVersionOutput(BaseModel):
    artifact_id: str
    version_id: str
    version_no: int = Field(ge=1)
    parent_version_id: str | None = None
    artifact_type: ArtifactType
    output_json: dict[str, Any]
    final_markdown: str
    diff_summary: list[dict[str, Any]] = Field(default_factory=list)
    verify_result: dict[str, Any] = Field(default_factory=dict)
    references: list[Any] = Field(default_factory=list)
    created_at: datetime


class ArtifactListItem(BaseModel):
    artifact_id: str
    artifact_type: ArtifactType
    title: str
    latest_version_id: str | None = None
    latest_version_no: int | None = Field(default=None, ge=1)
    created_at: datetime
    updated_at: datetime
    summary: str


class ArtifactVersionSummary(BaseModel):
    version_id: str
    version_no: int = Field(ge=1)
    parent_version_id: str | None = None
    operation_type: Literal["create", "revise", "repair"]
    revision_instruction: str | None = None
    created_at: datetime
    diff_summary: list[dict[str, Any]] = Field(default_factory=list)


class ArtifactVersionsOutput(BaseModel):
    artifact_id: str
    artifact_type: ArtifactType
    versions: list[ArtifactVersionSummary] = Field(default_factory=list)


class ArtifactRevisionResult(BaseModel):
    artifact_id: str
    base_version_id: str
    new_version_id: str
    artifact_type: ArtifactType
    output_json: dict[str, Any]
    final_markdown: str
    diff_summary_json: list[dict[str, Any]] = Field(default_factory=list)
    verify_result_json: dict[str, Any] = Field(default_factory=dict)
    references_json: list[Any] = Field(default_factory=list)

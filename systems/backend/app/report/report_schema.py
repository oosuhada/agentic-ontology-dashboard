from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ExportFormat = Literal["json", "csv", "pdf"]
ExportScope = Literal["dashboard", "event", "role_workspace"]
Role = Literal["manager", "engineer", "executive"]
ReportType = Literal[
    "inspection-summary",
    "operations-decision",
    "executive-brief",
    "maintenance-effect",
    "weekly-risk",
]
AppLocale = Literal["ko-KR", "en-US"]
ReportContentOrigin = Literal["generated", "edited", "translated"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportSection(StrictModel):
    section_id: str
    title: str
    body: str
    evidence_field_ids: list[str] = Field(default_factory=list)


class ReportAction(StrictModel):
    action_id: str
    label: str
    kind: Literal["monitor", "inspect", "review_shutdown", "verify_data", "report"]
    requires_human_approval: bool = True
    source_refs: list[str] = Field(default_factory=list)


class GroundedReport(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    report_id: str
    event_id: str
    role: Role
    report_type: ReportType
    locale: AppLocale = "ko-KR"
    mode: Literal["deterministic", "llm", "deterministic_fallback"]
    headline: str
    summary: str
    status: str
    confidence: str
    recommended_decision: str
    sections: list[ReportSection]
    actions: list[ReportAction]
    citations: list[str]
    limitations: list[str]
    generated_at: str


class ReportRequest(StrictModel):
    role: Role
    report_type: ReportType | None = None
    locale: AppLocale = "ko-KR"
    use_llm: bool = True


class ReportDraftSection(StrictModel):
    section_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=12000)
    evidence_field_ids: list[str] = Field(default_factory=list)


class ReportDraftSaveRequest(StrictModel):
    workspace_id: str
    event_id: str = Field(min_length=1, max_length=160)
    role: Role = "engineer"
    locale: AppLocale = "ko-KR"
    base_revision: int = Field(default=0, ge=0)
    headline: str = Field(min_length=1, max_length=240)
    summary: str = Field(min_length=1, max_length=12000)
    sections: list[ReportDraftSection]
    content_origin: ReportContentOrigin = "edited"
    source_locale: AppLocale | None = None
    source_revision: int | None = Field(default=None, ge=1)


class ReportDraftRecord(StrictModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    event_id: str
    role: Role
    locale: AppLocale
    revision: int
    headline: str
    summary: str
    sections: list[ReportDraftSection]
    content_origin: ReportContentOrigin
    source_locale: AppLocale | None = None
    source_revision: int | None = None
    updated_by: str
    updated_at: str


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    format: ExportFormat
    scope: ExportScope = "dashboard"
    event_id: str | None = None
    title: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def require_event_id(self) -> "ExportRequest":
        if self.scope == "event" and not self.event_id:
            raise ValueError("event scope export requires event_id")
        if self.scope != "event" and self.event_id is not None:
            raise ValueError("event_id is only allowed for event scope export")
        return self


class ExportCheckpoint(BaseModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    scope: ExportScope
    format: ExportFormat
    event_id: str | None
    filename: str
    media_type: str
    content_bytes: int
    snapshot_hash: str
    content_hash: str
    requested_by: str
    requested_by_name: str
    created_at: str


class ExportArtifact(BaseModel):
    checkpoint: ExportCheckpoint
    content: bytes

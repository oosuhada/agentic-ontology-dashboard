"""Stable request, report, and layout contracts for the demo runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["manager", "engineer"]
AppLocale = Literal["ko-KR", "en-US"]
Intent = Literal[
    "overview",
    "explain-risk",
    "compare",
    "summarize-manager",
    "detail-engineer",
    "recommend-check",
    "show-model-details",
]


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


class UIBlock(StrictModel):
    block_id: str
    type: Literal[
        "StatusSummary",
        "RiskKpi",
        "PriorityList",
        "ImpactSummary",
        "ManagerDecisionCard",
        "SensorLineChart",
        "AnomalyTimeline",
        "FactorContribution",
        "EvidenceTable",
        "RecommendedActions",
        "EngineerChecklist",
        "DataQualityWarning",
        "ModelDetails",
        "ConversationThread",
    ]
    title: str
    order: int = Field(ge=1)
    emphasis: Literal["primary", "secondary", "detail"]
    data_fields: list[str]
    collapsed: bool = False


class UILayout(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    layout_id: str
    event_id: str
    role: Role
    intent: Intent
    mode: Literal["deterministic", "llm", "deterministic_fallback"]
    blocks: list[UIBlock]
    generated_at: str


class ReportRequest(StrictModel):
    role: Role
    locale: AppLocale = "ko-KR"
    use_llm: bool = True


class LayoutRequest(StrictModel):
    role: Role
    locale: AppLocale = "ko-KR"
    intent: Intent = "overview"
    use_llm: bool = True


class DecisionRequest(StrictModel):
    actor: str = Field(min_length=1)
    decision: Literal["continue_monitoring", "request_inspection", "review_shutdown", "hold_for_data_check"]
    note: str = ""


class NoteRequest(StrictModel):
    actor: str = Field(min_length=1)
    body: str = Field(min_length=1, max_length=4000)


class FollowUpRequest(StrictModel):
    role: Role
    locale: AppLocale = "ko-KR"
    question: str = Field(min_length=1, max_length=1000)


class FollowUpResponse(StrictModel):
    thread_id: str
    event_id: str
    role: Role
    intent: Intent
    answer: str
    report: GroundedReport
    layout: UILayout
    supported: bool
    audit: dict[str, Any]


class ErrorEnvelope(StrictModel):
    error: dict[str, Any]

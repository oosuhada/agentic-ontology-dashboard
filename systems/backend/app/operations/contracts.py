"""Stable request, report, and layout contracts for the operations runtime."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from app.report.report_schema import GroundedReport, ReportAction, ReportRequest, ReportSection

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


from app.maintenance.maintenance_schema import OperationalDecisionKind


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    locale: AppLocale = "ko-KR"
    intent: Intent
    mode: Literal["deterministic", "llm", "deterministic_fallback"]
    blocks: list[UIBlock]
    generated_at: str


class LayoutRequest(StrictModel):
    role: Role
    locale: AppLocale = "ko-KR"
    intent: Intent = "overview"
    use_llm: bool = True


class DecisionRequest(StrictModel):
    actor: str = Field(min_length=1)
    decision: OperationalDecisionKind
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


AgentRoute = Literal["auto", "relational", "graph", "vector", "hybrid"]
AgentAudience = Literal["engineering", "operations", "executive", "maintenance"]


class AgentQueryRequest(StrictModel):
    project_id: str = Field(min_length=1, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=1000)
    route: AgentRoute = "auto"
    audience: AgentAudience | None = None
    object_type: str | None = Field(default=None, max_length=80)
    object_id: str | None = Field(default=None, max_length=160)
    event_id: str | None = Field(default=None, max_length=240)
    top_k: int = Field(default=8, ge=1, le=20)


class ErrorEnvelope(StrictModel):
    error: dict[str, Any]

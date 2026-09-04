"""Planner-owned UI plan and conversation state contracts."""

from __future__ import annotations

from typing import Literal

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


class StrictPlannerStateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UIBlock(StrictPlannerStateModel):
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


class UILayout(StrictPlannerStateModel):
    schema_version: Literal["1.0"] = "1.0"
    layout_id: str
    event_id: str
    role: Role
    locale: AppLocale = "ko-KR"
    intent: Intent
    mode: Literal["deterministic", "llm", "deterministic_fallback"]
    blocks: list[UIBlock]
    generated_at: str


__all__ = ["AppLocale", "Intent", "Role", "UIBlock", "UILayout"]

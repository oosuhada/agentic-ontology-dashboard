from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .dashboard_models import DashboardParameterDefinition, DashboardTab


PlannerMode = Literal["deterministic", "llm", "deterministic_fallback"]
FilterOperator = Literal["eq", "contains", "gte", "lte"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ObjectQueryFilter(StrictModel):
    field: str = Field(min_length=1, max_length=120)
    operator: FilterOperator = "eq"
    value: str | int | float | bool


class ObjectQueryIntent(StrictModel):
    object_type: str
    search: str | None = Field(default=None, max_length=160)
    filters: list[ObjectQueryFilter] = Field(default_factory=list)
    limit: int = Field(default=20, ge=1, le=50)
    rationale: str = Field(min_length=1, max_length=500)
    source_terms: list[str] = Field(default_factory=list)


class NaturalLanguageObjectQueryRequest(StrictModel):
    workspace_id: str
    query: str = Field(min_length=2, max_length=500)
    use_llm: bool = True
    limit: int = Field(default=20, ge=1, le=50)


class ObjectQueryPlanResponse(StrictModel):
    mode: PlannerMode
    provider: str
    fallback_reason: str | None = None
    intent: ObjectQueryIntent
    preview_total: int
    preview_items: list[dict[str, Any]]
    validation: dict[str, Any]
    requires_approval: bool = False


class BoardRecommendationRequest(StrictModel):
    workspace_id: str
    goal: str = Field(min_length=2, max_length=700)
    use_llm: bool = True
    limit: int = Field(default=5, ge=1, le=10)


class BoardRecommendationItem(StrictModel):
    definition_id: str
    display_name: str
    category: str
    score: float = Field(ge=0, le=1)
    reason: str
    already_present: bool
    preference_signals: list[str] = Field(default_factory=list)


class BoardRecommendationResponse(StrictModel):
    mode: PlannerMode
    provider: str
    fallback_reason: str | None = None
    role_code: str
    goal: str
    recommendations: list[BoardRecommendationItem]
    current_board_ids: list[str]
    requires_approval: bool = True
    persisted: bool = False


class DashboardDraftRequest(StrictModel):
    workspace_id: str
    target_role: str
    goal: str = Field(min_length=2, max_length=1000)
    use_llm: bool = True
    max_new_boards: int = Field(default=4, ge=1, le=8)


class DashboardDraftResponse(StrictModel):
    mode: PlannerMode
    provider: str
    fallback_reason: str | None = None
    workspace_id: str
    target_role: str
    display_name: str
    tabs: list[DashboardTab]
    parameter_definitions: list[DashboardParameterDefinition]
    recommended_definition_ids: list[str]
    validation: dict[str, Any]
    requires_approval: bool = True
    persisted: bool = False


class GroundedNarrativeRequest(StrictModel):
    workspace_id: str
    event_id: str
    goal: str = Field(default="현재 위험과 다음 확인 사항을 설명해 주세요.", min_length=2, max_length=700)
    use_llm: bool = True


class GroundedNarrativeClaim(StrictModel):
    text: str = Field(min_length=1, max_length=1000)
    evidence_field_ids: list[str] = Field(min_length=1)


class GroundedNarrativeResponse(StrictModel):
    mode: PlannerMode
    provider: str
    fallback_reason: str | None = None
    event_id: str
    goal: str
    headline: str
    summary: str
    claims: list[GroundedNarrativeClaim]
    citations: list[str]
    grounded: bool = True
    requires_approval: bool = False

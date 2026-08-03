from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

VisualizationKind = Literal[
    "metric",
    "table",
    "bar",
    "stacked_bar",
    "line",
    "area",
    "pie",
    "histogram",
    "scatter",
    "heatmap",
]
SemanticType = Literal["identifier", "categorical", "ordinal", "quantitative", "temporal", "boolean", "text", "geo"]
PhysicalType = Literal["number", "string", "boolean", "date", "mixed", "unknown"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldMapping(StrictModel):
    x: str | None = None
    y: str | None = None
    value: str | None = None
    series: str | None = None
    row: str | None = None
    column: str | None = None


class FieldProfile(StrictModel):
    id: str
    semantic_type: SemanticType
    physical_type: PhysicalType
    null_ratio: float = Field(ge=0, le=1)
    distinct_count: int = Field(ge=0)
    cardinality_ratio: float = Field(ge=0, le=1)
    min: float | str | None = None
    max: float | str | None = None
    sample_values: list[str | int | float | bool] = Field(default_factory=list)


class VisualizationCandidate(StrictModel):
    kind: VisualizationKind
    score: float = Field(ge=0, le=1)
    field_mapping: FieldMapping = Field(default_factory=FieldMapping)
    reason_codes: list[str] = Field(default_factory=list)
    rationale: str


class VisualizationUnavailable(StrictModel):
    kind: VisualizationKind
    reason: str


class VisualizationRecommendation(StrictModel):
    profile: list[FieldProfile]
    profile_hash: str
    recommended: VisualizationCandidate
    alternatives: list[VisualizationCandidate]
    unavailable: list[VisualizationUnavailable]


class VisualizationDefinition(StrictModel):
    kind: VisualizationKind
    display_name: str
    intent: Literal["comparison", "trend", "composition", "distribution", "relationship", "detail", "summary"]
    required_channels: list[str]
    supports_selection: bool
    supports_brush: bool
    supports_series: bool
    supports_stack: bool


JsonRow = dict[str, Any]

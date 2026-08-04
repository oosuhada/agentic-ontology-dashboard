from __future__ import annotations

from datetime import datetime
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
SemanticRole = Literal["identifier", "dimension", "measure", "timestamp", "status", "text"]
VisualizationIntent = Literal["comparison", "trend", "composition", "distribution", "relationship", "detail", "summary"]
Aggregation = Literal["none", "count", "count_distinct", "sum", "avg", "min", "max"]
SemanticFilterOperator = Literal["eq", "in", "gte", "lte", "between"]
TimeGrain = Literal["raw", "10m", "1h", "1d"]
SortDirection = Literal["asc", "desc"]
GraphReadiness = Literal[
    "pending",
    "indexing",
    "ready",
    "degraded",
    "failed",
    "unavailable",
]
SemanticSourceRole = Literal[
    "cnc_sensor_observation",
    "compressor_sensor_observation",
    "prediction_timeline",
    "result_artifact",
]
UnitStatus = Literal["known", "unitless", "source_raw_unspecified"]


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


class SemanticFieldCatalogEntry(StrictModel):
    field_id: str
    semantic_role: SemanticRole
    domain_concept: str
    physical_type: str
    unit: str | None = None
    unit_status: UnitStatus = "unitless"
    allowed_aggregations: list[Aggregation] = Field(default_factory=list)
    grain: str
    timezone: str | None = None
    allowed_filters: list[SemanticFilterOperator] = Field(default_factory=list)
    cardinality_limit: int | None = Field(default=None, ge=1)
    source_roles: list[SemanticSourceRole]
    source_expressions: dict[str, str] = Field(exclude=True)
    source_role: str
    dataset_version: str
    source_version: str
    bundle_checksum_sha256: str
    model_version: str | None = None
    result_artifact_schema_version: str | None = None
    graph_readiness: GraphReadiness
    relational_fallback_capability: bool = True
    derived_expression_id: str | None = None
    ordered_values: list[str] = Field(default_factory=list)
    queryable: bool = True
    runtime_allowed: bool = True
    governance_only: bool = False


class SemanticCatalogContext(StrictModel):
    dataset_version: str
    source_version: str
    bundle_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_version: str | None = None
    result_artifact_schema_version: str | None = None
    release_gates: dict[str, Any] = Field(default_factory=dict)
    graph_readiness: GraphReadiness = "ready"
    relational_fallback_capability: bool = True


class GovernedVisualizationSource(StrictModel):
    organization_id: str
    project_id: str
    workspace_id: str
    dataset_id: str
    dataset_version_id: str
    source_role: SemanticSourceRole
    dataset_version: str
    source_version: str
    bundle_checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_version: str | None = None
    result_artifact_schema_version: str | None = None
    release_gates: dict[str, Any] = Field(default_factory=dict)
    graph_readiness: GraphReadiness = "ready"
    relational_fallback_capability: bool = True


class SemanticMeasure(StrictModel):
    field_id: str
    aggregation: Aggregation = "avg"
    alias: str | None = None


class SemanticQueryFilter(StrictModel):
    field_id: str
    operator: SemanticFilterOperator
    value: str | int | float | bool | list[str | int | float | bool]


class SemanticTimeWindow(StrictModel):
    start: datetime
    end: datetime


class SemanticTimeSpec(StrictModel):
    field_id: str
    grain: TimeGrain = "raw"
    window: SemanticTimeWindow


class SemanticOrder(StrictModel):
    field_id: str
    direction: SortDirection = "desc"


class SemanticChannelMapping(StrictModel):
    x: str | None = None
    y: str | None = None
    value: str | None = None
    series: str | None = None
    row: str | None = None
    column: str | None = None
    threshold: str | None = None


class VisualizationAnnotation(StrictModel):
    kind: Literal["threshold", "range"]
    field_id: str
    values: list[float]
    label: str


class VisualizationOverride(StrictModel):
    version: Literal[2] = 2
    catalog_version: str
    dataset_version: str
    source_version: str
    chart_kind: VisualizationKind
    dimensions: list[str] = Field(default_factory=list)
    measures: list[SemanticMeasure] = Field(default_factory=list)
    channel_mapping: SemanticChannelMapping


class OverrideCompatibility(StrictModel):
    status: Literal["compatible", "migration_required", "incompatible", "not_provided"]
    reasons: list[str] = Field(default_factory=list)


class TypedVisualizationQueryPlan(StrictModel):
    catalog_version: str
    source: GovernedVisualizationSource
    intent: VisualizationIntent
    dimensions: list[str] = Field(default_factory=list)
    measures: list[SemanticMeasure] = Field(default_factory=list)
    time: SemanticTimeSpec | None = None
    filters: list[SemanticQueryFilter] = Field(default_factory=list)
    order: list[SemanticOrder] = Field(default_factory=list)
    limit: int = Field(default=500, ge=1, le=50000)
    chart_kind: VisualizationKind
    channel_mapping: SemanticChannelMapping
    annotations: list[VisualizationAnnotation] = Field(default_factory=list)
    selection_reason: str
    fallback_reason: str | None = None
    profile_hash: str


class CompiledVisualizationQuery(StrictModel):
    sql: str
    params: list[Any]
    query_hash: str
    selected_fields: list[str]
    units: dict[str, str | None]
    clamped: bool = False
    warnings: list[str] = Field(default_factory=list)


class SemanticVisualizationPlanRequest(StrictModel):
    source: GovernedVisualizationSource
    goal: str = Field(min_length=2, max_length=700)
    intent: VisualizationIntent
    dimensions: list[str] = Field(default_factory=list, max_length=3)
    measures: list[SemanticMeasure] = Field(default_factory=list, max_length=4)
    time: SemanticTimeSpec | None = None
    filters: list[SemanticQueryFilter] = Field(default_factory=list, max_length=20)
    order: list[SemanticOrder] = Field(default_factory=list, max_length=4)
    limit: int = Field(default=500, ge=1, le=50000)
    chart_kind: VisualizationKind | None = None
    field_cardinalities: dict[str, int] = Field(default_factory=dict)
    result_profile: list[FieldProfile] = Field(default_factory=list, max_length=100)
    saved_override: VisualizationOverride | None = None
    clamp_limits: bool = True
    use_llm: bool = True


class SemanticVisualizationPlanResponse(StrictModel):
    mode: Literal["deterministic", "llm", "deterministic_fallback"]
    provider: str
    fallback_reason: str | None = None
    plan: TypedVisualizationQueryPlan
    compiled_query: CompiledVisualizationQuery
    candidates: list[VisualizationCandidate]
    semantic_fields: list[SemanticFieldCatalogEntry]
    override_compatibility: OverrideCompatibility
    validation: dict[str, Any]


JsonRow = dict[str, Any]

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import (
    FieldMapping,
    FieldProfile,
    VisualizationCandidate,
    VisualizationDefinition,
    VisualizationKind,
    VisualizationRecommendation,
    VisualizationUnavailable,
)
from .profiler import profile_rows

VISUALIZATION_REGISTRY = [
    VisualizationDefinition(kind="metric", display_name="Metric", intent="summary", required_channels=["value"], supports_selection=False, supports_brush=False, supports_series=False, supports_stack=False),
    VisualizationDefinition(kind="table", display_name="Table", intent="detail", required_channels=[], supports_selection=True, supports_brush=False, supports_series=False, supports_stack=False),
    VisualizationDefinition(kind="bar", display_name="Bar chart", intent="comparison", required_channels=["x", "y"], supports_selection=True, supports_brush=True, supports_series=True, supports_stack=False),
    VisualizationDefinition(kind="stacked_bar", display_name="Stacked bar", intent="composition", required_channels=["x", "y", "series"], supports_selection=True, supports_brush=True, supports_series=True, supports_stack=True),
    VisualizationDefinition(kind="line", display_name="Line chart", intent="trend", required_channels=["x", "y"], supports_selection=True, supports_brush=True, supports_series=True, supports_stack=False),
    VisualizationDefinition(kind="area", display_name="Area chart", intent="trend", required_channels=["x", "y"], supports_selection=True, supports_brush=True, supports_series=True, supports_stack=True),
    VisualizationDefinition(kind="pie", display_name="Pie / donut", intent="composition", required_channels=["x", "value"], supports_selection=True, supports_brush=False, supports_series=False, supports_stack=False),
    VisualizationDefinition(kind="histogram", display_name="Histogram", intent="distribution", required_channels=["value"], supports_selection=True, supports_brush=True, supports_series=False, supports_stack=False),
    VisualizationDefinition(kind="scatter", display_name="Scatter plot", intent="relationship", required_channels=["x", "y"], supports_selection=True, supports_brush=True, supports_series=True, supports_stack=False),
    VisualizationDefinition(kind="heatmap", display_name="Heatmap", intent="relationship", required_channels=["row", "column", "value"], supports_selection=True, supports_brush=False, supports_series=False, supports_stack=False),
]


def _candidate(kind: VisualizationKind, score: float, mapping: FieldMapping, reasons: list[str], rationale: str) -> VisualizationCandidate:
    return VisualizationCandidate(kind=kind, score=max(0, min(1, score)), field_mapping=mapping, reason_codes=reasons, rationale=rationale)


def _profile_hash(profile: list[FieldProfile]) -> str:
    payload = [[item.id, item.semantic_type, item.distinct_count, round(item.null_ratio, 2)] for item in profile]
    return "profile-" + hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()[:12]


def _unavailable_reason(kind: VisualizationKind, numeric_count: int, category_count: int, has_temporal: bool) -> str:
    if kind == "scatter":
        return "Two quantitative fields are required."
    if kind in {"heatmap", "stacked_bar"}:
        return "Two categorical dimensions and one quantitative field are required."
    if kind in {"line", "area"}:
        return "A temporal field and quantitative value are required." if not has_temporal else "A quantitative value field is required."
    if kind in {"pie", "bar"}:
        return "A categorical field and quantitative value are required." if not category_count else "A quantitative value field is required."
    if kind in {"histogram", "metric"}:
        return "A quantitative field is required." if not numeric_count else "Current mapping is unavailable."
    return "The current field profile is not compatible."


def recommend_visualization(rows: list[dict[str, Any]], fallback_render_spec: dict[str, Any] | None = None) -> VisualizationRecommendation:
    profile = profile_rows(rows)
    temporal = next((field for field in profile if field.semantic_type == "temporal"), None)
    quantitative = [field for field in profile if field.semantic_type == "quantitative"]
    categorical = [field for field in profile if field.semantic_type in {"categorical", "boolean"}]
    first_numeric = quantitative[0] if quantitative else None
    second_numeric = quantitative[1] if len(quantitative) > 1 else None
    first_category = categorical[0] if categorical else next((field for field in profile if field.semantic_type == "identifier"), None)
    second_category = categorical[1] if len(categorical) > 1 else None
    candidates: list[VisualizationCandidate] = []
    if len(rows) <= 2 and first_numeric:
        candidates.append(_candidate("metric", .96, FieldMapping(value=first_numeric.id), ["small_summary_record", "numeric_measure"], f"Small result set with numeric measure {first_numeric.id}."))
    if temporal and first_numeric:
        candidates.extend([
            _candidate("line", .94, FieldMapping(x=temporal.id, y=first_numeric.id, series=first_category.id if first_category else None), ["temporal_sequence", "continuous_numeric_measure"], f"{temporal.id} is ordered time data and {first_numeric.id} is quantitative."),
            _candidate("area", .86, FieldMapping(x=temporal.id, y=first_numeric.id, series=first_category.id if first_category else None), ["temporal_sequence", "magnitude_emphasis"], f"Area emphasizes the magnitude of {first_numeric.id} over time."),
        ])
    if first_category and first_numeric:
        candidates.append(_candidate("bar", .82 if first_category.distinct_count > 20 else .9, FieldMapping(x=first_category.id, y=first_numeric.id), ["categorical_comparison", "numeric_measure"], f"{first_category.id} categories can be compared by {first_numeric.id}."))
        if 1 < first_category.distinct_count <= 8:
            candidates.append(_candidate("pie", .75, FieldMapping(x=first_category.id, value=first_numeric.id), ["low_category_cardinality", "part_to_whole"], f"{first_category.distinct_count} categories are suitable for a donut composition."))
    if first_category and second_category and first_numeric:
        candidates.extend([
            _candidate("stacked_bar", .84, FieldMapping(x=first_category.id, y=first_numeric.id, series=second_category.id), ["two_categorical_dimensions", "composition_comparison"], f"{second_category.id} can be stacked within {first_category.id}."),
            _candidate("heatmap", .8, FieldMapping(row=first_category.id, column=second_category.id, value=first_numeric.id), ["categorical_matrix", "numeric_intensity"], f"{first_category.id} × {second_category.id} forms a matrix for {first_numeric.id}."),
        ])
    if first_numeric:
        candidates.append(_candidate("histogram", .78, FieldMapping(value=first_numeric.id), ["numeric_distribution"], f"{first_numeric.id} can be inspected as a distribution."))
    if first_numeric and second_numeric:
        candidates.append(_candidate("scatter", .87, FieldMapping(x=first_numeric.id, y=second_numeric.id, series=first_category.id if first_category else None), ["two_numeric_measures", "relationship"], f"{first_numeric.id} and {second_numeric.id} can be compared for correlation."))
    candidates.append(_candidate("table", .88 if len(profile) > 6 else .62, FieldMapping(), ["detail_fallback", "all_fields_available"], "Table preserves every available field without aggregation."))
    if fallback_render_spec:
        fallback_kind = fallback_render_spec.get("kind")
        registry_kinds = {item.kind for item in VISUALIZATION_REGISTRY}
        if fallback_kind in registry_kinds and not any(item.kind == fallback_kind for item in candidates):
            candidates.append(_candidate(fallback_kind, .65, FieldMapping(x=fallback_render_spec.get("x_field"), y=fallback_render_spec.get("y_field"), value=fallback_render_spec.get("value_field"), series=fallback_render_spec.get("group_field")), ["api_render_spec"], "API render specification provides a compatible fallback."))
    unique: dict[VisualizationKind, VisualizationCandidate] = {}
    for item in sorted(candidates, key=lambda candidate: candidate.score, reverse=True):
        unique.setdefault(item.kind, item)
    ranked = list(unique.values())
    recommended = ranked[0]
    supported = set(unique)
    unavailable = [
        VisualizationUnavailable(kind=item.kind, reason=_unavailable_reason(item.kind, len(quantitative), len(categorical), temporal is not None))
        for item in VISUALIZATION_REGISTRY
        if item.kind not in supported
    ]
    return VisualizationRecommendation(profile=profile, profile_hash=_profile_hash(profile), recommended=recommended, alternatives=ranked[1:6], unavailable=unavailable)

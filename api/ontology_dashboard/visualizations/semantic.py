from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from typing import Any

from .models import (
    Aggregation,
    CompiledVisualizationQuery,
    FieldMapping,
    GovernedVisualizationSource,
    OverrideCompatibility,
    SemanticCatalogContext,
    SemanticChannelMapping,
    SemanticFieldCatalogEntry,
    SemanticMeasure,
    SemanticOrder,
    SemanticVisualizationPlanRequest,
    TypedVisualizationQueryPlan,
    VisualizationAnnotation,
    VisualizationCandidate,
    VisualizationKind,
    VisualizationOverride,
)

CATALOG_VERSION = "pm-semantic-catalog-v3.1.0"
V3_1_DATASET_VERSION = "canonical-ai4i-physics-v3.1"
V3_1_RESULT_SCHEMA_VERSION = "result-artifact-v1.0"
MAX_TIME_RANGE = timedelta(days=31)
MAX_QUERY_ROWS = 5000

DERIVED_EXPRESSION_REGISTRY: dict[str, str] = {
    "power_w": "(q.torque_nm * q.rotational_speed_rpm * 2.0 * pi() / 60.0)",
    "temperature_gap_k": "(q.process_temperature_k - q.air_temperature_k)",
    "overstrain_load": "(q.tool_wear_min * q.torque_nm)",
    "overstrain_threshold": (
        "(CASE q.product_type WHEN 'L' THEN 11000.0 WHEN 'M' THEN 12000.0 "
        "WHEN 'H' THEN 13000.0 ELSE NULL END)"
    ),
    "overstrain_margin": (
        "((q.tool_wear_min * q.torque_nm) - "
        "(CASE q.product_type WHEN 'L' THEN 11000.0 WHEN 'M' THEN 12000.0 "
        "WHEN 'H' THEN 13000.0 ELSE NULL END))"
    ),
}

SOURCE_SQL: dict[str, str] = {
    "cnc_sensor_observation": "pm_cnc_observations q",
    "compressor_sensor_observation": "pm_compressor_observations q",
    "prediction_timeline": (
        "pm_prediction_timeline q JOIN pm_assets a ON "
        "a.organization_id=q.organization_id AND a.project_id=q.project_id "
        "AND a.workspace_id=q.workspace_id AND a.dataset_version_id=q.dataset_version_id "
        "AND a.asset_id=q.asset_id"
    ),
    "result_artifact": (
        "pm_result_artifacts q JOIN pm_assets a ON "
        "a.organization_id=q.organization_id AND a.project_id=q.project_id "
        "AND a.workspace_id=q.workspace_id AND a.dataset_version_id=q.dataset_version_id "
        "AND a.asset_id=q.asset_id"
    ),
}

REQUIRED_CHANNELS: dict[VisualizationKind, tuple[str, ...]] = {
    "metric": ("value",),
    "table": (),
    "bar": ("x", "y"),
    "stacked_bar": ("x", "y", "series"),
    "line": ("x", "y"),
    "area": ("x", "y"),
    "pie": ("x", "value"),
    "histogram": ("value",),
    "scatter": ("x", "y"),
    "heatmap": ("row", "column", "value"),
}


def _entry(
    context: SemanticCatalogContext,
    *,
    field_id: str,
    semantic_role: str,
    domain_concept: str,
    physical_type: str,
    unit: str | None,
    unit_status: str,
    allowed_aggregations: list[Aggregation],
    grain: str,
    allowed_filters: list[str],
    source_expressions: dict[str, str],
    source_role: str,
    timezone: str | None = None,
    cardinality_limit: int | None = None,
    derived_expression_id: str | None = None,
    ordered_values: list[str] | None = None,
    queryable: bool = True,
    runtime_allowed: bool = True,
    governance_only: bool = False,
) -> SemanticFieldCatalogEntry:
    return SemanticFieldCatalogEntry(
        field_id=field_id,
        semantic_role=semantic_role,
        domain_concept=domain_concept,
        physical_type=physical_type,
        unit=unit,
        unit_status=unit_status,
        allowed_aggregations=allowed_aggregations,
        grain=grain,
        timezone=timezone,
        allowed_filters=allowed_filters,
        cardinality_limit=cardinality_limit,
        source_roles=list(source_expressions),
        source_expressions=source_expressions,
        source_role=source_role,
        dataset_version=context.dataset_version,
        source_version=context.source_version,
        bundle_checksum_sha256=context.bundle_checksum_sha256,
        model_version=context.model_version,
        result_artifact_schema_version=context.result_artifact_schema_version,
        graph_readiness=context.graph_readiness,
        relational_fallback_capability=context.relational_fallback_capability,
        derived_expression_id=derived_expression_id,
        ordered_values=ordered_values or [],
        queryable=queryable,
        runtime_allowed=runtime_allowed,
        governance_only=governance_only,
    )


def build_v3_1_semantic_catalog(context: SemanticCatalogContext) -> dict[str, SemanticFieldCatalogEntry]:
    """Build the runtime-safe catalog. Evaluation and hidden truth never enter this registry."""

    common_sources = {
        "cnc_sensor_observation": "q.asset_id",
        "compressor_sensor_observation": "q.asset_id",
        "prediction_timeline": "q.asset_id",
        "result_artifact": "q.asset_id",
    }
    asset_join_sources = {
        "cnc_sensor_observation": "q.site_id",
        "compressor_sensor_observation": "q.site_id",
        "prediction_timeline": "a.site_id",
        "result_artifact": "a.site_id",
    }
    cell_join_sources = {
        "cnc_sensor_observation": "q.cell_id",
        "compressor_sensor_observation": "q.cell_id",
        "prediction_timeline": "a.cell_id",
        "result_artifact": "a.cell_id",
    }
    asset_type_sources = {
        "prediction_timeline": "q.asset_type",
        "result_artifact": "q.asset_type",
    }
    entries = [
        _entry(
            context,
            field_id="asset_id",
            semantic_role="identifier",
            domain_concept="equipment_identity",
            physical_type="string",
            unit=None,
            unit_status="unitless",
            allowed_aggregations=["none", "count", "count_distinct"],
            grain="asset",
            allowed_filters=["eq", "in"],
            source_expressions=common_sources,
            source_role="canonical_asset_identity",
            cardinality_limit=5000,
        ),
        _entry(
            context,
            field_id="site_id",
            semantic_role="dimension",
            domain_concept="manufacturing_site",
            physical_type="string",
            unit=None,
            unit_status="unitless",
            allowed_aggregations=["none", "count", "count_distinct"],
            grain="site",
            allowed_filters=["eq", "in"],
            source_expressions=asset_join_sources,
            source_role="canonical_asset_dimension",
            cardinality_limit=50,
        ),
        _entry(
            context,
            field_id="cell_id",
            semantic_role="dimension",
            domain_concept="production_cell",
            physical_type="string",
            unit=None,
            unit_status="unitless",
            allowed_aggregations=["none", "count", "count_distinct"],
            grain="cell",
            allowed_filters=["eq", "in"],
            source_expressions=cell_join_sources,
            source_role="canonical_asset_dimension",
            cardinality_limit=100,
        ),
        _entry(
            context,
            field_id="asset_type",
            semantic_role="dimension",
            domain_concept="equipment_type",
            physical_type="enum",
            unit=None,
            unit_status="unitless",
            allowed_aggregations=["none", "count", "count_distinct"],
            grain="asset",
            allowed_filters=["eq", "in"],
            source_expressions=asset_type_sources,
            source_role="result_or_timeline_dimension",
            cardinality_limit=2,
            ordered_values=["compressor", "cnc"],
        ),
        _entry(
            context,
            field_id="observed_at",
            semantic_role="timestamp",
            domain_concept="observation_time",
            physical_type="timestamptz",
            unit=None,
            unit_status="unitless",
            allowed_aggregations=["none", "min", "max"],
            grain="source_event",
            timezone="Asia/Seoul",
            allowed_filters=["gte", "lte", "between"],
            source_expressions={role: "q.observed_at" for role in SOURCE_SQL},
            source_role="canonical_or_derived_observation_time",
        ),
        _entry(
            context,
            field_id="operating_state",
            semantic_role="status",
            domain_concept="equipment_operating_state",
            physical_type="enum",
            unit=None,
            unit_status="unitless",
            allowed_aggregations=["none", "count", "count_distinct"],
            grain="observation",
            allowed_filters=["eq", "in"],
            source_expressions={
                "cnc_sensor_observation": "q.operating_state",
                "compressor_sensor_observation": "q.operating_state",
            },
            source_role="canonical_sensor_status",
            cardinality_limit=10,
        ),
        _entry(
            context,
            field_id="product_type",
            semantic_role="dimension",
            domain_concept="ai4i_product_quality_type",
            physical_type="enum",
            unit=None,
            unit_status="unitless",
            allowed_aggregations=["none", "count", "count_distinct"],
            grain="cnc_observation",
            allowed_filters=["eq", "in"],
            source_expressions={"cnc_sensor_observation": "q.product_type"},
            source_role="canonical_cnc_sensor",
            cardinality_limit=3,
            ordered_values=["L", "M", "H"],
        ),
    ]

    sensor_measures = [
        ("air_temperature_k", "ambient_air_temperature", "K", "known"),
        ("process_temperature_k", "cnc_process_temperature", "K", "known"),
        ("rotational_speed_rpm", "cnc_spindle_rotational_speed", "rpm", "known"),
        ("torque_nm", "cnc_spindle_torque", "N·m", "known"),
        ("tool_wear_min", "cnc_tool_wear_elapsed", "minute", "known"),
    ]
    for field_id, concept, unit, unit_status in sensor_measures:
        entries.append(
            _entry(
                context,
                field_id=field_id,
                semantic_role="measure",
                domain_concept=concept,
                physical_type="double_precision",
                unit=unit,
                unit_status=unit_status,
                allowed_aggregations=["none", "avg", "min", "max"],
                grain="10_minute_cnc_observation",
                allowed_filters=["eq", "gte", "lte", "between"],
                source_expressions={"cnc_sensor_observation": f"q.{field_id}"},
                source_role="canonical_cnc_sensor",
            )
        )

    for field_id, concept in [
        ("voltage_raw", "compressor_voltage_raw_signal"),
        ("rotation_raw", "compressor_rotation_raw_signal"),
        ("pressure_raw", "compressor_pressure_raw_signal"),
        ("vibration_raw", "compressor_vibration_raw_signal"),
    ]:
        entries.append(
            _entry(
                context,
                field_id=field_id,
                semantic_role="measure",
                domain_concept=concept,
                physical_type="double_precision_raw_signal",
                unit=None,
                unit_status="source_raw_unspecified",
                allowed_aggregations=["none", "avg", "min", "max"],
                grain="10_minute_compressor_observation",
                allowed_filters=["eq", "gte", "lte", "between"],
                source_expressions={"compressor_sensor_observation": f"q.{field_id}"},
                source_role="canonical_compressor_sensor",
            )
        )

    for field_id, concept, unit in [
        ("power_w", "ai4i_mechanical_power", "W"),
        ("temperature_gap_k", "ai4i_process_air_temperature_gap", "K"),
        ("overstrain_load", "ai4i_tool_wear_torque_load", "minute·N·m"),
        ("overstrain_threshold", "ai4i_product_type_overstrain_threshold", "minute·N·m"),
        ("overstrain_margin", "ai4i_product_type_overstrain_margin", "minute·N·m"),
    ]:
        entries.append(
            _entry(
                context,
                field_id=field_id,
                semantic_role="measure",
                domain_concept=concept,
                physical_type="derived_double_precision",
                unit=unit,
                unit_status="known",
                allowed_aggregations=["none", "avg", "min", "max"],
                grain="10_minute_cnc_observation",
                allowed_filters=["eq", "gte", "lte", "between"],
                source_expressions={"cnc_sensor_observation": DERIVED_EXPRESSION_REGISTRY[field_id]},
                source_role="allowlisted_ai4i_derived_measure",
                derived_expression_id=field_id,
            )
        )

    result_and_timeline = {
        "prediction_timeline": "q.failure_probability",
        "result_artifact": "q.failure_probability",
    }
    entries.extend(
        [
            _entry(
                context,
                field_id="failure_probability",
                semantic_role="measure",
                domain_concept="binary_failure_within_horizon_probability",
                physical_type="probability",
                unit="probability",
                unit_status="known",
                allowed_aggregations=["none", "avg", "min", "max"],
                grain="prediction",
                allowed_filters=["eq", "gte", "lte", "between"],
                source_expressions=result_and_timeline,
                source_role="derived_prediction_result",
            ),
            _entry(
                context,
                field_id="confidence",
                semantic_role="measure",
                domain_concept="binary_decision_boundary_confidence",
                physical_type="probability_like",
                unit="probability_like",
                unit_status="known",
                allowed_aggregations=["none", "avg", "min", "max"],
                grain="latest_result_artifact",
                allowed_filters=["eq", "gte", "lte", "between"],
                source_expressions={"result_artifact": "q.confidence"},
                source_role="result_artifact",
            ),
            _entry(
                context,
                field_id="status_grade",
                semantic_role="status",
                domain_concept="ordered_product_risk_status",
                physical_type="ordered_enum",
                unit=None,
                unit_status="unitless",
                allowed_aggregations=["none", "count", "count_distinct"],
                grain="latest_result_artifact",
                allowed_filters=["eq", "in"],
                source_expressions={"result_artifact": "q.status_grade"},
                source_role="result_artifact",
                cardinality_limit=4,
                ordered_values=["normal", "attention", "warning", "critical"],
            ),
            _entry(
                context,
                field_id="predicted_failure_type",
                semantic_role="dimension",
                domain_concept="binary_generic_failure_class",
                physical_type="binary_enum",
                unit=None,
                unit_status="unitless",
                allowed_aggregations=["none", "count", "count_distinct"],
                grain="latest_result_artifact",
                allowed_filters=["eq", "in"],
                source_expressions={"result_artifact": "q.predicted_failure_type"},
                source_role="result_artifact",
                cardinality_limit=2,
                ordered_values=["no_significant_risk", "failure_risk"],
            ),
            _entry(
                context,
                field_id="recommended_action.action",
                semantic_role="dimension",
                domain_concept="policy_recommended_action_not_executed_work_order",
                physical_type="enum",
                unit=None,
                unit_status="unitless",
                allowed_aggregations=["none", "count", "count_distinct"],
                grain="latest_result_artifact",
                allowed_filters=["eq", "in"],
                source_expressions={"result_artifact": "q.recommended_action->>'action'"},
                source_role="result_artifact",
                cardinality_limit=4,
            ),
            _entry(
                context,
                field_id="recommended_action.priority",
                semantic_role="status",
                domain_concept="ordered_policy_recommendation_priority",
                physical_type="ordered_enum",
                unit=None,
                unit_status="unitless",
                allowed_aggregations=["none", "count", "count_distinct"],
                grain="latest_result_artifact",
                allowed_filters=["eq", "in"],
                source_expressions={"result_artifact": "q.recommended_action->>'priority'"},
                source_role="result_artifact",
                cardinality_limit=4,
                ordered_values=["routine", "medium", "high", "urgent"],
            ),
        ]
    )

    for field_id, concept in [
        ("top_factors.feature", "model_top_factor_feature"),
        ("top_factors.direction", "model_top_factor_direction"),
        ("top_factors.signed_contribution", "model_top_factor_signed_contribution"),
    ]:
        entries.append(
            _entry(
                context,
                field_id=field_id,
                semantic_role="text" if field_id != "top_factors.signed_contribution" else "measure",
                domain_concept=concept,
                physical_type="nested_result_artifact_array",
                unit=None if field_id != "top_factors.signed_contribution" else "model_logit_contribution",
                unit_status="unitless" if field_id != "top_factors.signed_contribution" else "known",
                allowed_aggregations=[],
                grain="top_factor",
                allowed_filters=[],
                source_expressions={"result_artifact": "q.top_factors"},
                source_role="result_artifact",
                queryable=False,
            )
        )

    for field_id, concept, expression in [
        ("model_version", "result_model_provenance", "q.model_version"),
        ("result_artifact_schema_version", "result_schema_provenance", "q.schema_version"),
        ("dataset_version", "dataset_version_provenance", "q.dataset_version_id"),
    ]:
        entries.append(
            _entry(
                context,
                field_id=field_id,
                semantic_role="text",
                domain_concept=concept,
                physical_type="provenance_text",
                unit=None,
                unit_status="unitless",
                allowed_aggregations=["none", "count_distinct"],
                grain="result_artifact",
                allowed_filters=["eq", "in"],
                source_expressions={"result_artifact": expression},
                source_role="result_artifact_provenance",
            )
        )

    entries.append(
        _entry(
            context,
            field_id="release_gates",
            semantic_role="status",
            domain_concept="dataset_governance_release_status",
            physical_type="governance_object",
            unit=None,
            unit_status="unitless",
            allowed_aggregations=[],
            grain="dataset_version",
            allowed_filters=[],
            source_expressions={"result_artifact": "NULL"},
            source_role="dataset_version_governance",
            queryable=False,
            governance_only=True,
        )
    )
    return {entry.field_id: entry for entry in entries}


def _field(catalog: dict[str, SemanticFieldCatalogEntry], field_id: str, source_role: str) -> SemanticFieldCatalogEntry:
    entry = catalog.get(field_id)
    if entry is None or not entry.runtime_allowed:
        raise ValueError(f"unknown or runtime-forbidden semantic field: {field_id}")
    if not entry.queryable:
        raise ValueError(f"semantic field is not directly queryable: {field_id}")
    if source_role not in entry.source_expressions:
        raise ValueError(f"semantic field {field_id} is unavailable for source {source_role}")
    return entry


def _measure_output(measure: SemanticMeasure) -> str:
    return measure.alias or measure.field_id


def _candidate(
    kind: VisualizationKind,
    score: float,
    mapping: FieldMapping,
    reasons: list[str],
    rationale: str,
) -> VisualizationCandidate:
    return VisualizationCandidate(
        kind=kind,
        score=max(0.0, min(1.0, score)),
        field_mapping=mapping,
        reason_codes=reasons,
        rationale=rationale,
    )


def semantic_candidates(
    request: SemanticVisualizationPlanRequest,
    catalog: dict[str, SemanticFieldCatalogEntry],
) -> list[VisualizationCandidate]:
    source_role = request.source.source_role
    dimensions = [_field(catalog, field_id, source_role) for field_id in request.dimensions]
    measures = [_field(catalog, item.field_id, source_role) for item in request.measures]
    time_field = _field(catalog, request.time.field_id, source_role) if request.time else None
    first_dimension = dimensions[0].field_id if dimensions else None
    second_dimension = dimensions[1].field_id if len(dimensions) > 1 else None
    first_measure = _measure_output(request.measures[0]) if request.measures else None
    second_measure = _measure_output(request.measures[1]) if len(request.measures) > 1 else None
    candidates: list[VisualizationCandidate] = []

    if request.intent == "trend" and time_field and first_measure:
        candidates.extend(
            [
                _candidate(
                    "line",
                    0.97,
                    FieldMapping(x=time_field.field_id, y=first_measure, series=first_dimension),
                    ["semantic_intent_trend", "governed_timestamp", "unit_preserving_measure"],
                    f"Trend intent uses governed time field {time_field.field_id} and measure {first_measure}.",
                ),
                _candidate(
                    "area",
                    0.86,
                    FieldMapping(x=time_field.field_id, y=first_measure, series=first_dimension),
                    ["semantic_intent_trend", "magnitude_emphasis"],
                    f"Area is compatible when the magnitude of {first_measure} should be emphasized.",
                ),
            ]
        )
    if request.intent == "comparison" and first_dimension and first_measure:
        candidates.append(
            _candidate(
                "bar",
                0.96,
                FieldMapping(x=first_dimension, y=first_measure, series=second_dimension),
                ["semantic_intent_comparison", "ordered_or_categorical_dimension"],
                f"Bar compares {first_measure} across {first_dimension}.",
            )
        )
    if request.intent == "distribution" and first_measure:
        candidates.append(
            _candidate(
                "histogram",
                0.98,
                FieldMapping(value=first_measure),
                ["semantic_intent_distribution", "continuous_measure"],
                f"Histogram shows the distribution of {first_measure} without inventing categories.",
            )
        )
    if request.intent == "relationship" and first_measure and second_measure:
        candidates.append(
            _candidate(
                "scatter",
                0.98,
                FieldMapping(x=first_measure, y=second_measure, series=first_dimension),
                ["semantic_intent_relationship", "two_physical_measures"],
                f"Scatter preserves the distinct units of {first_measure} and {second_measure} on separate axes.",
            )
        )
    if request.intent == "relationship" and first_dimension and second_dimension and first_measure:
        candidates.append(
            _candidate(
                "heatmap",
                0.94,
                FieldMapping(row=first_dimension, column=second_dimension, value=first_measure),
                ["semantic_intent_relationship", "bounded_categorical_matrix"],
                f"Heatmap maps {first_dimension} × {second_dimension} to {first_measure}.",
            )
        )
    if request.intent == "composition" and first_dimension and first_measure:
        if second_dimension:
            candidates.append(
                _candidate(
                    "stacked_bar",
                    0.96,
                    FieldMapping(x=first_dimension, y=first_measure, series=second_dimension),
                    ["semantic_intent_composition", "two_bounded_dimensions"],
                    f"Stacked bar composes {second_dimension} within {first_dimension}.",
                )
            )
        candidates.append(
            _candidate(
                "bar",
                0.9,
                FieldMapping(x=first_dimension, y=first_measure),
                ["semantic_intent_composition", "safe_bar_fallback"],
                f"Bar is a readable composition fallback for {first_dimension}.",
            )
        )
    if request.intent == "summary" and first_measure:
        candidates.append(
            _candidate(
                "metric",
                0.98,
                FieldMapping(value=first_measure),
                ["semantic_intent_summary", "single_measure"],
                f"Metric summarizes {first_measure}.",
            )
        )
    if request.intent == "detail":
        candidates.append(
            _candidate(
                "table",
                0.99,
                FieldMapping(),
                ["semantic_intent_detail", "lossless_rows"],
                "Table preserves governed source rows and provenance fields.",
            )
        )

    candidates.append(
        _candidate(
            "table",
            0.6 if request.intent != "detail" else 0.99,
            FieldMapping(),
            ["relational_detail_fallback"],
            "Table remains available from the relational source even when graph readiness is degraded.",
        )
    )
    unique: dict[str, VisualizationCandidate] = {}
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        unique.setdefault(candidate.kind, candidate)
    return list(unique.values())


def _validate_cardinality(
    kind: VisualizationKind,
    dimensions: list[str],
    cardinalities: dict[str, int],
    catalog: dict[str, SemanticFieldCatalogEntry],
) -> None:
    for field_id in dimensions:
        actual = cardinalities.get(field_id)
        catalog_limit = catalog[field_id].cardinality_limit
        if actual is not None and catalog_limit is not None and actual > catalog_limit:
            raise ValueError(f"field cardinality exceeds catalog limit: {field_id}={actual}>{catalog_limit}")
    if kind == "pie" and dimensions and cardinalities.get(dimensions[0], 0) > 8:
        raise ValueError("pie chart cardinality exceeds 8 categories")
    if kind == "heatmap":
        for field_id in dimensions[:2]:
            if cardinalities.get(field_id, 0) > 50:
                raise ValueError(f"heatmap dimension cardinality exceeds 50: {field_id}")


def _validate_units(
    kind: VisualizationKind,
    measures: list[SemanticMeasure],
    catalog: dict[str, SemanticFieldCatalogEntry],
) -> None:
    if kind in {"scatter", "table"} or len(measures) < 2:
        return
    units = {
        (catalog[item.field_id].unit_status, catalog[item.field_id].unit)
        for item in measures
        if item.aggregation not in {"count", "count_distinct"}
    }
    if len(units) > 1:
        raise ValueError("multiple measures with incompatible units cannot share one chart value axis")


def _validate_chart_shape(
    kind: VisualizationKind,
    request: SemanticVisualizationPlanRequest,
) -> None:
    dimension_count = len(request.dimensions)
    measure_count = len(request.measures)
    if kind in {"line", "area"} and (request.time is None or measure_count < 1):
        raise ValueError(f"{kind} requires a governed time field and measure")
    if kind in {"bar", "pie"} and (dimension_count < 1 or measure_count < 1):
        raise ValueError(f"{kind} requires a dimension and measure")
    if kind == "stacked_bar" and (dimension_count < 2 or measure_count < 1):
        raise ValueError("stacked_bar requires two dimensions and one measure")
    if kind == "histogram" and measure_count != 1:
        raise ValueError("histogram requires exactly one measure")
    if kind == "histogram" and request.measures[0].aggregation != "none":
        raise ValueError("histogram requires a raw measure without aggregation")
    if kind == "scatter" and measure_count < 2:
        raise ValueError("scatter requires two measures")
    if kind == "scatter" and any(item.aggregation != "none" for item in request.measures):
        raise ValueError("scatter requires raw measures without aggregation")
    if kind == "heatmap" and (dimension_count < 2 or measure_count < 1):
        raise ValueError("heatmap requires two dimensions and one measure")
    if kind == "metric" and measure_count != 1:
        raise ValueError("metric requires exactly one measure")


def _annotations(measures: list[SemanticMeasure]) -> list[VisualizationAnnotation]:
    field_ids = {item.field_id for item in measures}
    annotations: list[VisualizationAnnotation] = []
    if "power_w" in field_ids:
        annotations.append(
            VisualizationAnnotation(
                kind="range",
                field_id="power_w",
                values=[3500.0, 9000.0],
                label="AI4I power failure range boundary",
            )
        )
    if "temperature_gap_k" in field_ids:
        annotations.append(
            VisualizationAnnotation(
                kind="threshold",
                field_id="temperature_gap_k",
                values=[8.6],
                label="AI4I heat-dissipation temperature-gap threshold",
            )
        )
    if "overstrain_load" in field_ids or "overstrain_margin" in field_ids:
        annotations.append(
            VisualizationAnnotation(
                kind="range",
                field_id="overstrain_load",
                values=[11000.0, 12000.0, 13000.0],
                label="Product-type overstrain thresholds L/M/H",
            )
        )
    return annotations


def _profile_hash(request: SemanticVisualizationPlanRequest, kind: VisualizationKind) -> str:
    payload = {
        "catalog": CATALOG_VERSION,
        "source": request.source.model_dump(mode="json"),
        "intent": request.intent,
        "dimensions": request.dimensions,
        "measures": [item.model_dump(mode="json") for item in request.measures],
        "time": request.time.model_dump(mode="json") if request.time else None,
        "kind": kind,
        "cardinality": request.field_cardinalities,
        "result_profile": [item.model_dump(mode="json") for item in request.result_profile],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"semantic-profile-{digest[:16]}"


def validate_result_profile_compatibility(
    plan: TypedVisualizationQueryPlan,
    result_profile: list[Any],
) -> None:
    if not result_profile:
        return
    fields = {item.id: item for item in result_profile}
    mapping = plan.channel_mapping.model_dump(exclude_none=True)
    channel_fields = {
        channel: str(field_id)
        for channel, field_id in mapping.items()
        if channel != "threshold"
    }
    missing = sorted(set(channel_fields.values()) - set(fields))
    if missing:
        raise ValueError(
            f"query result profile is missing chart channel fields: {','.join(missing)}"
        )

    numeric_channels: set[str] = set()
    if plan.chart_kind in {"metric", "histogram", "pie", "heatmap"}:
        numeric_channels.add("value")
    if plan.chart_kind in {"bar", "stacked_bar", "line", "area"}:
        numeric_channels.add("y")
    if plan.chart_kind == "scatter":
        numeric_channels.update({"x", "y"})
    for channel in numeric_channels:
        field_id = channel_fields.get(channel)
        if field_id and fields[field_id].physical_type != "number":
            raise ValueError(
                f"chart channel {channel} requires numeric query result field: {field_id}"
            )

    if plan.chart_kind in {"line", "area"} and plan.time:
        x_field = channel_fields.get("x")
        if x_field and fields[x_field].semantic_type != "temporal":
            raise ValueError(
                f"chart channel x requires temporal query result field: {x_field}"
            )


def build_typed_query_plan(
    request: SemanticVisualizationPlanRequest,
    catalog: dict[str, SemanticFieldCatalogEntry],
    *,
    selected_kind: VisualizationKind | None = None,
) -> tuple[TypedVisualizationQueryPlan, list[VisualizationCandidate]]:
    if request.source.dataset_version != V3_1_DATASET_VERSION:
        raise ValueError("V3.1 semantic planner requires canonical-ai4i-physics-v3.1")
    if request.source.source_version != V3_1_DATASET_VERSION:
        raise ValueError("source version does not match the V3.1 semantic catalog")
    source_role = request.source.source_role
    for field_id in request.dimensions:
        entry = _field(catalog, field_id, source_role)
        if entry.semantic_role not in {"identifier", "dimension", "status", "text"}:
            raise ValueError(f"field is not a valid dimension: {field_id}")
    for measure in request.measures:
        entry = _field(catalog, measure.field_id, source_role)
        if measure.aggregation not in entry.allowed_aggregations:
            raise ValueError(
                f"aggregation {measure.aggregation} is not allowed for {measure.field_id}"
            )
        if measure.aggregation == "sum" and entry.unit_status != "unitless":
            raise ValueError(f"sum is unsafe for physical/probability field {measure.field_id}")
    if request.time:
        time_entry = _field(catalog, request.time.field_id, source_role)
        if time_entry.semantic_role != "timestamp":
            raise ValueError(f"time field is not a governed timestamp: {request.time.field_id}")
    for item in request.filters:
        entry = _field(catalog, item.field_id, source_role)
        if item.operator not in entry.allowed_filters:
            raise ValueError(f"filter {item.operator} is not allowed for {item.field_id}")
    for item in request.order:
        _field(catalog, item.field_id, source_role)

    candidates = semantic_candidates(request, catalog)
    kind = selected_kind or request.chart_kind or candidates[0].kind
    candidate = next((item for item in candidates if item.kind == kind), None)
    if candidate is None:
        raise ValueError(f"chart {kind} is outside deterministic semantic candidates")
    _validate_chart_shape(kind, request)
    _validate_cardinality(kind, request.dimensions, request.field_cardinalities, catalog)
    _validate_units(kind, request.measures, catalog)

    fallback_reason = None
    if request.source.graph_readiness != "ready":
        if not request.source.relational_fallback_capability:
            raise ValueError("graph is degraded and relational fallback is unavailable")
        fallback_reason = f"graph_{request.source.graph_readiness}_using_relational_source"
    resolved_order = request.order
    if not resolved_order and kind == "bar" and request.measures:
        resolved_order = [
            SemanticOrder(
                field_id=_measure_output(request.measures[0]),
                direction="desc",
            )
        ]
    plan = TypedVisualizationQueryPlan(
            catalog_version=CATALOG_VERSION,
            source=request.source,
            intent=request.intent,
            dimensions=request.dimensions,
            measures=request.measures,
            time=request.time,
            filters=request.filters,
            order=resolved_order,
            limit=request.limit,
            chart_kind=kind,
            channel_mapping=SemanticChannelMapping(**candidate.field_mapping.model_dump()),
            annotations=_annotations(request.measures),
            selection_reason=candidate.rationale,
            fallback_reason=fallback_reason,
            profile_hash=_profile_hash(request, kind),
    )
    validate_result_profile_compatibility(plan, request.result_profile)
    return plan, candidates


def _safe_alias(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    if not normalized or not re.match(r"^[a-zA-Z_]", normalized):
        normalized = f"field_{normalized}"
    return normalized[:63]


def _time_expression(expression: str, grain: str) -> str:
    if grain == "raw":
        return expression
    if grain == "10m":
        return (
            "date_trunc('hour', {0}) + "
            "floor(date_part('minute', {0}) / 10) * interval '10 minutes'"
        ).format(expression)
    if grain == "1h":
        return f"date_trunc('hour', {expression})"
    if grain == "1d":
        return f"date_trunc('day', {expression})"
    raise ValueError(f"unsupported time grain: {grain}")


def _aggregate(expression: str, aggregation: Aggregation) -> str:
    if aggregation == "none":
        return expression
    if aggregation == "count":
        return "COUNT(*)"
    if aggregation == "count_distinct":
        return f"COUNT(DISTINCT {expression})"
    registry = {"sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX"}
    function = registry.get(aggregation)
    if function is None:
        raise ValueError(f"unsupported aggregation: {aggregation}")
    return f"{function}({expression})"


def compile_postgresql_query(
    plan: TypedVisualizationQueryPlan,
    catalog: dict[str, SemanticFieldCatalogEntry],
    *,
    clamp_limits: bool = True,
) -> CompiledVisualizationQuery:
    source_role = plan.source.source_role
    source_sql = SOURCE_SQL[source_role]
    params: list[Any] = [
        plan.source.organization_id,
        plan.source.project_id,
        plan.source.workspace_id,
        plan.source.dataset_version_id,
    ]
    where = [
        "q.organization_id=%s",
        "q.project_id=%s",
        "q.workspace_id=%s",
        "q.dataset_version_id=%s",
    ]
    warnings: list[str] = []
    clamped = False

    time_expression: str | None = None
    time_alias: str | None = None
    if plan.time:
        if plan.time.window.start.tzinfo is None or plan.time.window.end.tzinfo is None:
            raise ValueError("time range timestamps must include timezone")
        if plan.time.window.end <= plan.time.window.start:
            raise ValueError("time range end must be after start")
        start = plan.time.window.start
        end = plan.time.window.end
        if end - start > MAX_TIME_RANGE:
            if not clamp_limits:
                raise ValueError("time range exceeds 31 days")
            start = end - MAX_TIME_RANGE
            clamped = True
            warnings.append("time_range_clamped_to_31_days")
        time_field = _field(catalog, plan.time.field_id, source_role)
        raw_time = time_field.source_expressions[source_role]
        where.extend([f"{raw_time}>=%s", f"{raw_time}<%s"])
        params.extend([start, end])
        time_expression = _time_expression(raw_time, plan.time.grain)
        time_alias = _safe_alias(plan.time.field_id)

    for item in plan.filters:
        entry = _field(catalog, item.field_id, source_role)
        expression = entry.source_expressions[source_role]
        if item.operator == "eq":
            where.append(f"{expression}=%s")
            params.append(item.value)
        elif item.operator in {"gte", "lte"}:
            operator = ">=" if item.operator == "gte" else "<="
            where.append(f"{expression}{operator}%s")
            params.append(item.value)
        elif item.operator == "in":
            if not isinstance(item.value, list) or not item.value:
                raise ValueError("in filter requires a non-empty list")
            if len(item.value) > 100:
                raise ValueError("in filter exceeds 100 values")
            where.append(f"{expression}=ANY(%s)")
            params.append(item.value)
        elif item.operator == "between":
            if not isinstance(item.value, list) or len(item.value) != 2:
                raise ValueError("between filter requires exactly two values")
            where.append(f"{expression} BETWEEN %s AND %s")
            params.extend(item.value)
        else:
            raise ValueError(f"unsupported filter operator: {item.operator}")

    selected: list[str] = []
    selected_fields: list[str] = []
    group_by: list[str] = []
    output_expressions: dict[str, str] = {}
    units: dict[str, str | None] = {}
    if time_expression and time_alias:
        selected.append(f"{time_expression} AS {time_alias}")
        selected_fields.append(plan.time.field_id if plan.time else time_alias)
        output_expressions[plan.time.field_id if plan.time else time_alias] = time_expression
        group_by.append(time_expression)
        units[plan.time.field_id if plan.time else time_alias] = None

    for field_id in plan.dimensions:
        entry = _field(catalog, field_id, source_role)
        expression = entry.source_expressions[source_role]
        alias = _safe_alias(field_id)
        selected.append(f"{expression} AS {alias}")
        selected_fields.append(field_id)
        output_expressions[field_id] = expression
        group_by.append(expression)
        units[field_id] = entry.unit

    aggregated = any(item.aggregation != "none" for item in plan.measures)
    if aggregated and any(item.aggregation == "none" for item in plan.measures):
        raise ValueError("aggregated and raw measures cannot be mixed in one query plan")
    for item in plan.measures:
        entry = _field(catalog, item.field_id, source_role)
        expression = entry.source_expressions[source_role]
        output = _measure_output(item)
        alias = _safe_alias(output)
        rendered = _aggregate(expression, item.aggregation)
        selected.append(f"{rendered} AS {alias}")
        selected_fields.append(output)
        output_expressions[output] = rendered
        units[output] = None if item.aggregation in {"count", "count_distinct"} else entry.unit

    if not selected:
        raise ValueError("query plan must select at least one field")
    if not aggregated:
        group_by = []

    order_sql: list[str] = []
    for item in plan.order:
        if item.field_id not in output_expressions:
            raise ValueError(f"order field is not selected: {item.field_id}")
        order_sql.append(f"{_safe_alias(item.field_id)} {item.direction.upper()}")
    if not order_sql and time_alias:
        order_sql.append(f"{time_alias} ASC")

    limit = plan.limit
    if limit > MAX_QUERY_ROWS:
        if not clamp_limits:
            raise ValueError("row limit exceeds 5000")
        limit = MAX_QUERY_ROWS
        clamped = True
        warnings.append("row_limit_clamped_to_5000")
    sql_parts = [
        "SELECT " + ", ".join(selected),
        "FROM " + source_sql,
        "WHERE " + " AND ".join(where),
    ]
    if aggregated and group_by:
        sql_parts.append("GROUP BY " + ", ".join(group_by))
    if order_sql:
        sql_parts.append("ORDER BY " + ", ".join(order_sql))
    sql_parts.append("LIMIT %s")
    params.append(limit)
    sql = "\n".join(sql_parts)
    query_hash = hashlib.sha256(
        json.dumps({"sql": sql, "params": [str(item) for item in params]}, separators=(",", ":")).encode()
    ).hexdigest()
    return CompiledVisualizationQuery(
        sql=sql,
        params=params,
        query_hash=f"semantic-query-{query_hash[:16]}",
        selected_fields=selected_fields,
        units=units,
        clamped=clamped,
        warnings=warnings,
    )


def validate_override(
    override: VisualizationOverride | None,
    plan: TypedVisualizationQueryPlan,
    catalog: dict[str, SemanticFieldCatalogEntry],
) -> OverrideCompatibility:
    if override is None:
        return OverrideCompatibility(status="not_provided")
    reasons: list[str] = []
    migration = False
    if override.catalog_version != CATALOG_VERSION:
        reasons.append("catalog_version_changed")
        migration = True
    if override.dataset_version != plan.source.dataset_version:
        reasons.append("dataset_version_changed")
        migration = True
    if override.source_version != plan.source.source_version:
        reasons.append("source_version_changed")
        migration = True
    referenced = set(override.dimensions)
    referenced.update(item.field_id for item in override.measures)
    missing = sorted(field_id for field_id in referenced if field_id not in catalog)
    if missing:
        return OverrideCompatibility(
            status="incompatible",
            reasons=[*reasons, f"fields_missing:{','.join(missing)}"],
        )
    if migration:
        return OverrideCompatibility(status="migration_required", reasons=reasons)
    return OverrideCompatibility(status="compatible", reasons=[])


def validate_override_channel_mapping(
    override: VisualizationOverride,
    plan: TypedVisualizationQueryPlan,
) -> None:
    selected_fields = set(plan.dimensions)
    selected_fields.update(_measure_output(item) for item in plan.measures)
    if plan.time:
        selected_fields.add(plan.time.field_id)
    mapping = override.channel_mapping.model_dump(exclude_none=True)
    missing_channels = [
        channel for channel in REQUIRED_CHANNELS[override.chart_kind] if channel not in mapping
    ]
    if missing_channels:
        raise ValueError(
            f"override channel mapping is missing required channels: {','.join(missing_channels)}"
        )
    unknown = sorted(
        {
            str(field_id)
            for channel, field_id in mapping.items()
            if channel != "threshold" and str(field_id) not in selected_fields
        }
    )
    if unknown:
        raise ValueError(
            f"override channel mapping references unselected fields: {','.join(unknown)}"
        )


def context_from_source(source: GovernedVisualizationSource) -> SemanticCatalogContext:
    return SemanticCatalogContext(
        dataset_version=source.dataset_version,
        source_version=source.source_version,
        bundle_checksum_sha256=source.bundle_checksum_sha256,
        model_version=source.model_version,
        result_artifact_schema_version=(
            source.result_artifact_schema_version or V3_1_RESULT_SCHEMA_VERSION
        ),
        release_gates=source.release_gates,
        graph_readiness=source.graph_readiness,
        relational_fallback_capability=source.relational_fallback_capability,
    )

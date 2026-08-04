from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ontology_dashboard.dashboard_models import DashboardPreferenceSaveRequest
from ontology_dashboard.dashboard_service import DashboardService
from ontology_dashboard.dependencies import get_predictive_maintenance_runtime_service
from ontology_dashboard.identity import (
    CSRF_COOKIE,
    AuthError,
    IdentityService,
    LoginRequest,
    Principal,
)
from ontology_dashboard.main import (
    app,
    get_identity_service,
    get_ontology_planner_service,
    get_service,
)
from ontology_dashboard.planner import OntologyDashboardPlannerService
from ontology_dashboard.predictive_maintenance_runtime.models import (
    DatasetVersionRuntimeContext,
    GovernanceProvenance,
    GraphReadiness,
    SemanticQueryCapability,
)
from ontology_dashboard.service import ManufacturingPredictiveMaintenanceService
from ontology_dashboard.visualizations import (
    CATALOG_VERSION,
    DERIVED_EXPRESSION_REGISTRY,
    FieldProfile,
    GovernedVisualizationSource,
    SemanticMeasure,
    SemanticOrder,
    SemanticQueryFilter,
    SemanticVisualizationPlanRequest,
    VisualizationOverride,
    build_typed_query_plan,
    build_v3_1_semantic_catalog,
    compile_postgresql_query,
    context_from_source,
    validate_override,
)

ROOT = Path(__file__).resolve().parents[1]
SEOUL = timezone(timedelta(hours=9))
START = datetime(2026, 8, 1, 0, 0, tzinfo=SEOUL)
END = datetime(2026, 8, 2, 0, 0, tzinfo=SEOUL)
CHECKSUM = "a" * 64


def governed_source(
    source_role: str,
    *,
    organization_id: str = "org-a",
    project_id: str = "project-a",
    workspace_id: str = "workspace-a",
    dataset_version: str = "canonical-ai4i-physics-v3.1",
    source_version: str = "canonical-ai4i-physics-v3.1",
    graph_readiness: str = "ready",
    relational_fallback_capability: bool = True,
) -> GovernedVisualizationSource:
    return GovernedVisualizationSource(
        organization_id=organization_id,
        project_id=project_id,
        workspace_id=workspace_id,
        dataset_id="dataset-pm",
        dataset_version_id="dsv-v3-1",
        source_role=source_role,
        dataset_version=dataset_version,
        source_version=source_version,
        bundle_checksum_sha256=CHECKSUM,
        model_version="independent-logreg-v3.1",
        result_artifact_schema_version=(
            "result-artifact-v1.0" if source_role == "result_artifact" else None
        ),
        release_gates={
            "tool_wear_continuity": {"pass": True}
        },
        graph_readiness=graph_readiness,
        relational_fallback_capability=relational_fallback_capability,
    )


def semantic_request(
    source_role: str,
    *,
    intent: str,
    dimensions: list[str] | None = None,
    measures: list[SemanticMeasure] | None = None,
    time_field: str | None = None,
    time_grain: str = "1h",
    start: datetime = START,
    end: datetime = END,
    chart_kind: str | None = None,
    limit: int = 500,
    graph_readiness: str = "ready",
    relational_fallback_capability: bool = True,
    goal: str = "governed visualization",
    use_llm: bool = False,
) -> SemanticVisualizationPlanRequest:
    return SemanticVisualizationPlanRequest(
        source=governed_source(
            source_role,
            graph_readiness=graph_readiness,
            relational_fallback_capability=relational_fallback_capability,
        ),
        goal=goal,
        intent=intent,
        dimensions=dimensions or [],
        measures=measures or [],
        time=(
            {
                "field_id": time_field,
                "grain": time_grain,
                "window": {"start": start, "end": end},
            }
            if time_field
            else None
        ),
        filters=[],
        order=[],
        limit=limit,
        chart_kind=chart_kind,
        field_cardinalities={"site_id": 5, "status_grade": 4, "asset_id": 100},
        clamp_limits=True,
        use_llm=use_llm,
    )


def catalog_for(request: SemanticVisualizationPlanRequest):
    return build_v3_1_semantic_catalog(context_from_source(request.source))


def authoritative_runtime_context(
    source: GovernedVisualizationSource,
    *,
    checksum: str | None = None,
    graph_status: str | None = None,
) -> DatasetVersionRuntimeContext:
    resolved_graph_status = graph_status or source.graph_readiness
    if resolved_graph_status == "degraded":
        resolved_graph_status = "failed"
    return DatasetVersionRuntimeContext(
        organization_id=source.organization_id,
        project_id=source.project_id,
        workspace_id=source.workspace_id,
        dataset_id=source.dataset_id,
        dataset_version_id=source.dataset_version_id,
        source_version="canonical-ai4i-physics-v3.1",
        bundle_checksum_sha256=checksum or source.bundle_checksum_sha256,
        version_number=31,
        record_count=100,
        dataset_status="published",
        row_counts={"result_artifact": 100},
        source_contract={
            "result_artifact_schema_version": "result-artifact-v1.0",
            "model_version": "independent-logreg-v3.1",
        },
        governance=GovernanceProvenance(
            release_identity={"dataset_version": "canonical-ai4i-physics-v3.1"},
            tool_wear_continuity={"pass": True, "aligned_reset_transition_count": 731},
            agent_example_evaluation={"pass": True},
            ai4i_physics={"pass": True},
            ai4i_contract={"predicted_failure_type": "binary_generic_class"},
            query_time_derived_measures=DERIVED_EXPRESSION_REGISTRY,
        ),
        graph=GraphReadiness(
            status=resolved_graph_status,
            record_count=100,
        ),
        semantic_query=SemanticQueryCapability(
            dimensions=["asset_id", "site_id", "status_grade", "observed_at"],
            canonical_measures=["failure_probability", "torque_nm"],
            derived_measures=DERIVED_EXPRESSION_REGISTRY,
            latest_result_contract="result_artifact",
            supported_grains=["raw", "10m", "1h"],
        ),
    )


def build(request: SemanticVisualizationPlanRequest):
    catalog = catalog_for(request)
    plan, candidates = build_typed_query_plan(request, catalog)
    return catalog, plan, candidates


def test_v3_1_semantic_field_catalog_preserves_units_provenance_and_runtime_boundaries() -> None:
    request = semantic_request("cnc_sensor_observation", intent="detail")
    catalog = catalog_for(request)

    assert CATALOG_VERSION == "pm-semantic-catalog-v3.1.0"
    assert catalog["air_temperature_k"].unit == "K"
    assert catalog["process_temperature_k"].unit == "K"
    assert catalog["rotational_speed_rpm"].unit == "rpm"
    assert catalog["torque_nm"].unit == "N·m"
    assert catalog["tool_wear_min"].unit == "minute"
    assert catalog["power_w"].unit == "W"
    assert catalog["temperature_gap_k"].unit == "K"
    assert catalog["overstrain_load"].unit == "minute·N·m"
    assert catalog["overstrain_margin"].derived_expression_id == "overstrain_margin"
    assert set(DERIVED_EXPRESSION_REGISTRY) == {
        "power_w",
        "temperature_gap_k",
        "overstrain_load",
        "overstrain_threshold",
        "overstrain_margin",
    }

    for field_id in ("voltage_raw", "rotation_raw", "pressure_raw", "vibration_raw"):
        assert catalog[field_id].unit is None
        assert catalog[field_id].unit_status == "source_raw_unspecified"

    for entry in catalog.values():
        assert entry.dataset_version == "canonical-ai4i-physics-v3.1"
        assert entry.source_version == "canonical-ai4i-physics-v3.1"
        assert entry.bundle_checksum_sha256 == CHECKSUM
        assert entry.model_version == "independent-logreg-v3.1"
        assert entry.result_artifact_schema_version == "result-artifact-v1.0"
        assert entry.relational_fallback_capability is True

    assert catalog["predicted_failure_type"].domain_concept == "binary_generic_failure_class"
    assert catalog["predicted_failure_type"].ordered_values == [
        "no_significant_risk",
        "failure_risk",
    ]
    assert catalog["release_gates"].governance_only is True
    assert catalog["release_gates"].queryable is False
    assert catalog["release_gates"].allowed_aggregations == []
    assert catalog["recommended_action.action"].domain_concept.endswith(
        "not_executed_work_order"
    )


@pytest.mark.parametrize(
    ("plan_request", "expected_kind"),
    [
        (
            semantic_request(
                "prediction_timeline",
                intent="trend",
                dimensions=["asset_id"],
                measures=[SemanticMeasure(field_id="failure_probability", aggregation="avg")],
                time_field="observed_at",
                goal="risk timeline 시간 추세",
            ),
            "line",
        ),
        (
            semantic_request(
                "result_artifact",
                intent="comparison",
                dimensions=["asset_id", "status_grade"],
                measures=[SemanticMeasure(field_id="failure_probability", aggregation="max")],
                goal="설비별 현재 status와 probability 비교",
            ),
            "bar",
        ),
        (
            semantic_request(
                "result_artifact",
                intent="distribution",
                measures=[SemanticMeasure(field_id="failure_probability", aggregation="none")],
                goal="failure probability 분포",
            ),
            "histogram",
        ),
        (
            semantic_request(
                "cnc_sensor_observation",
                intent="relationship",
                dimensions=["product_type"],
                measures=[
                    SemanticMeasure(field_id="torque_nm", aggregation="none"),
                    SemanticMeasure(field_id="rotational_speed_rpm", aggregation="none"),
                ],
                goal="torque와 RPM 관계",
            ),
            "scatter",
        ),
        (
            semantic_request(
                "cnc_sensor_observation",
                intent="trend",
                dimensions=["asset_id"],
                measures=[SemanticMeasure(field_id="temperature_gap_k", aggregation="avg")],
                time_field="observed_at",
                goal="process air temperature gap 추세",
            ),
            "line",
        ),
        (
            semantic_request(
                "cnc_sensor_observation",
                intent="trend",
                dimensions=["asset_id"],
                measures=[SemanticMeasure(field_id="power_w", aggregation="avg")],
                time_field="observed_at",
                goal="power threshold excursion",
            ),
            "line",
        ),
        (
            semantic_request(
                "cnc_sensor_observation",
                intent="relationship",
                dimensions=["product_type"],
                measures=[
                    SemanticMeasure(field_id="tool_wear_min", aggregation="none"),
                    SemanticMeasure(field_id="overstrain_load", aggregation="none"),
                ],
                goal="tool wear와 torque overstrain 관계",
            ),
            "scatter",
        ),
        (
            semantic_request(
                "result_artifact",
                intent="relationship",
                dimensions=["site_id", "status_grade"],
                measures=[SemanticMeasure(field_id="asset_id", aggregation="count")],
                goal="site status grade 집중도",
            ),
            "heatmap",
        ),
        (
            semantic_request(
                "result_artifact",
                intent="composition",
                dimensions=["site_id", "recommended_action.priority"],
                measures=[SemanticMeasure(field_id="asset_id", aggregation="count")],
                goal="recommended action priority composition",
            ),
            "stacked_bar",
        ),
        (
            semantic_request(
                "cnc_sensor_observation",
                intent="detail",
                dimensions=["asset_id", "product_type"],
                measures=[SemanticMeasure(field_id="torque_nm", aggregation="none")],
                goal="세부 원본 확인",
            ),
            "table",
        ),
    ],
)
def test_required_semantic_scenarios_choose_expected_chart(
    plan_request: SemanticVisualizationPlanRequest,
    expected_kind: str,
) -> None:
    catalog, plan, candidates = build(plan_request)
    assert plan.chart_kind == expected_kind
    assert candidates[0].kind == expected_kind
    compiled = compile_postgresql_query(plan, catalog)
    assert compiled.sql.startswith("SELECT ")
    assert "q.organization_id=%s" in compiled.sql
    assert plan_request.source.organization_id not in compiled.sql
    assert plan_request.source.organization_id in compiled.params
    assert compiled.selected_fields

    if plan_request.goal == "설비별 현재 status와 probability 비교":
        assert plan.channel_mapping.series == "status_grade"
        assert plan.order[0].field_id == "failure_probability"
        assert plan.order[0].direction == "desc"

    if any(item.field_id == "power_w" for item in plan_request.measures):
        assert any(item.field_id == "power_w" for item in plan.annotations)
        assert "q.torque_nm * q.rotational_speed_rpm" in compiled.sql
    if any(item.field_id == "temperature_gap_k" for item in plan_request.measures):
        assert any(item.values == [8.6] for item in plan.annotations)


def test_parameterized_compiler_keeps_filters_scope_and_derived_sql_out_of_llm_control() -> None:
    request = semantic_request(
        "cnc_sensor_observation",
        intent="trend",
        dimensions=["asset_id"],
        measures=[SemanticMeasure(field_id="power_w", aggregation="avg")],
        time_field="observed_at",
    ).model_copy(
        update={
            "filters": [
                SemanticQueryFilter(
                    field_id="site_id",
                    operator="eq",
                    value="SITE-SECRET",
                ),
                SemanticQueryFilter(field_id="power_w", operator="gte", value=3500.0),
            ],
            "order": [SemanticOrder(field_id="observed_at", direction="asc")],
        }
    )
    catalog, plan, _ = build(request)
    compiled = compile_postgresql_query(plan, catalog)

    assert "SITE-SECRET" not in compiled.sql
    assert "SITE-SECRET" in compiled.params
    assert compiled.sql.count("%s") == len(compiled.params)
    assert compiled.params[:4] == [
        "org-a",
        "project-a",
        "workspace-a",
        "dsv-v3-1",
    ]
    assert DERIVED_EXPRESSION_REGISTRY["power_w"] in compiled.sql


@pytest.mark.parametrize(
    ("field_id", "source_role"),
    [
        ("does_not_exist", "cnc_sensor_observation"),
        ("event_condition_details", "cnc_sensor_observation"),
        ("condition_variant", "cnc_sensor_observation"),
        ("hidden_truth", "result_artifact"),
        ("failure_mode", "result_artifact"),
        ("maintenance_evidence_match_count", "result_artifact"),
        ("prediction_accuracy", "result_artifact"),
    ],
)
def test_unknown_evaluation_hidden_and_accuracy_fields_are_rejected(
    field_id: str,
    source_role: str,
) -> None:
    request = semantic_request(
        source_role,
        intent="distribution",
        measures=[SemanticMeasure(field_id=field_id, aggregation="none")],
    )
    with pytest.raises(ValueError, match="unknown or runtime-forbidden semantic field"):
        build(request)


def test_disallowed_aggregation_and_non_allowlisted_derived_expression_are_rejected() -> None:
    sum_request = semantic_request(
        "cnc_sensor_observation",
        intent="summary",
        measures=[SemanticMeasure(field_id="torque_nm", aggregation="sum")],
    )
    with pytest.raises(ValueError, match="aggregation sum is not allowed"):
        build(sum_request)

    arbitrary_derived = semantic_request(
        "cnc_sensor_observation",
        intent="distribution",
        measures=[SemanticMeasure(field_id="torque_nm * rotational_speed_rpm", aggregation="none")],
    )
    with pytest.raises(ValueError, match="unknown or runtime-forbidden semantic field"):
        build(arbitrary_derived)


def test_registry_outside_chart_and_channel_incompatibility_are_rejected() -> None:
    with pytest.raises(ValidationError):
        SemanticVisualizationPlanRequest.model_validate(
            {
                **semantic_request(
                    "result_artifact",
                    intent="distribution",
                    measures=[SemanticMeasure(field_id="failure_probability", aggregation="none")],
                ).model_dump(mode="json"),
                "chart_kind": "sankey",
            }
        )

    no_time_line = semantic_request(
        "result_artifact",
        intent="comparison",
        dimensions=["asset_id"],
        measures=[SemanticMeasure(field_id="failure_probability", aggregation="max")],
        chart_kind="line",
    )
    with pytest.raises(ValueError, match="outside deterministic semantic candidates"):
        build(no_time_line)


def test_incompatible_units_cannot_share_one_chart_value_axis() -> None:
    request = semantic_request(
        "cnc_sensor_observation",
        intent="trend",
        dimensions=["asset_id"],
        measures=[
            SemanticMeasure(field_id="torque_nm", aggregation="avg"),
            SemanticMeasure(field_id="rotational_speed_rpm", aggregation="avg"),
        ],
        time_field="observed_at",
    )
    with pytest.raises(ValueError, match="incompatible units"):
        build(request)


def test_catalog_cardinality_constraints_reject_unsafe_heatmap_dimensions() -> None:
    request = semantic_request(
        "result_artifact",
        intent="relationship",
        dimensions=["site_id", "status_grade"],
        measures=[SemanticMeasure(field_id="asset_id", aggregation="count")],
    ).model_copy(
        update={"field_cardinalities": {"site_id": 51, "status_grade": 4}}
    )
    with pytest.raises(ValueError, match="site_id=51>50"):
        build(request)


def test_query_result_profile_must_match_chart_channels_and_physical_types() -> None:
    valid_profile = [
        FieldProfile(
            id="torque_nm",
            semantic_type="quantitative",
            physical_type="number",
            null_ratio=0,
            distinct_count=100,
            cardinality_ratio=1,
            sample_values=[10.0],
        ),
        FieldProfile(
            id="rotational_speed_rpm",
            semantic_type="quantitative",
            physical_type="number",
            null_ratio=0,
            distinct_count=100,
            cardinality_ratio=1,
            sample_values=[1500.0],
        ),
        FieldProfile(
            id="product_type",
            semantic_type="categorical",
            physical_type="string",
            null_ratio=0,
            distinct_count=3,
            cardinality_ratio=0.03,
            sample_values=["L", "M", "H"],
        ),
    ]
    request = semantic_request(
        "cnc_sensor_observation",
        intent="relationship",
        dimensions=["product_type"],
        measures=[
            SemanticMeasure(field_id="torque_nm", aggregation="none"),
            SemanticMeasure(field_id="rotational_speed_rpm", aggregation="none"),
        ],
    ).model_copy(update={"result_profile": valid_profile})
    _, plan, _ = build(request)
    assert plan.profile_hash.startswith("semantic-profile-")

    invalid_profile = [
        valid_profile[0].model_copy(update={"physical_type": "string"}),
        *valid_profile[1:],
    ]
    with pytest.raises(ValueError, match="requires numeric query result field: torque_nm"):
        build(request.model_copy(update={"result_profile": invalid_profile}))

    with pytest.raises(ValueError, match="missing chart channel fields: product_type"):
        build(request.model_copy(update={"result_profile": valid_profile[:2]}))


def test_time_range_and_row_limit_are_safely_clamped_or_rejected() -> None:
    request = semantic_request(
        "prediction_timeline",
        intent="trend",
        dimensions=["asset_id"],
        measures=[SemanticMeasure(field_id="failure_probability", aggregation="avg")],
        time_field="observed_at",
        start=START,
        end=START + timedelta(days=45),
        limit=10000,
    )
    catalog, plan, _ = build(request)
    compiled = compile_postgresql_query(plan, catalog, clamp_limits=True)
    assert compiled.clamped is True
    assert set(compiled.warnings) == {
        "time_range_clamped_to_31_days",
        "row_limit_clamped_to_5000",
    }
    assert compiled.params[-1] == 5000

    with pytest.raises(ValueError, match="time range exceeds 31 days"):
        compile_postgresql_query(plan, catalog, clamp_limits=False)


def test_other_dataset_version_project_and_wrong_source_field_are_rejected() -> None:
    wrong_version = semantic_request(
        "cnc_sensor_observation",
        intent="distribution",
        measures=[SemanticMeasure(field_id="torque_nm", aggregation="none")],
    ).model_copy(
        update={
            "source": governed_source(
                "cnc_sensor_observation",
                dataset_version="canonical-independent-v1.0",
                source_version="canonical-independent-v1.0",
            )
        }
    )
    with pytest.raises(ValueError, match="requires canonical-ai4i-physics-v3.1"):
        build(wrong_version)

    wrong_source_field = semantic_request(
        "result_artifact",
        intent="distribution",
        measures=[SemanticMeasure(field_id="torque_nm", aggregation="none")],
    )
    with pytest.raises(ValueError, match="unavailable for source result_artifact"):
        build(wrong_source_field)


def test_binary_predicted_type_never_expands_to_ai4i_failure_modes() -> None:
    request = semantic_request(
        "result_artifact",
        intent="comparison",
        dimensions=["predicted_failure_type"],
        measures=[SemanticMeasure(field_id="asset_id", aggregation="count")],
        goal="site × PWF HDF OSF TWF failure type heatmap",
    )
    catalog, plan, candidates = build(request)
    assert plan.chart_kind == "bar"
    assert candidates[0].field_mapping.x == "predicted_failure_type"
    assert catalog["predicted_failure_type"].ordered_values == [
        "no_significant_risk",
        "failure_risk",
    ]
    serialized = " ".join(
        [plan.selection_reason, *catalog["predicted_failure_type"].ordered_values]
    )
    assert all(mode not in serialized for mode in ("PWF", "HDF", "OSF", "TWF"))


def test_tool_wear_alignment_and_maintenance_evidence_are_not_prediction_accuracy_measures() -> None:
    request = semantic_request(
        "result_artifact",
        intent="summary",
        measures=[SemanticMeasure(field_id="failure_probability", aggregation="avg")],
        goal="tool-wear 731/731 정렬과 maintenance evidence를 prediction accuracy로 보여줘",
    )
    catalog, plan, _ = build(request)
    assert plan.chart_kind == "metric"
    assert plan.measures == [SemanticMeasure(field_id="failure_probability", aggregation="avg")]
    assert not {
        "tool_wear_731_731",
        "maintenance_evidence",
        "maintenance_evidence_match_count",
        "prediction_accuracy",
        "event_condition_details",
        "condition_variant",
    }.intersection(catalog)


def test_graph_degraded_keeps_relational_candidates_and_records_fallback() -> None:
    request = semantic_request(
        "prediction_timeline",
        intent="trend",
        dimensions=["asset_id"],
        measures=[SemanticMeasure(field_id="failure_probability", aggregation="avg")],
        time_field="observed_at",
        graph_readiness="degraded",
    )
    catalog, plan, candidates = build(request)
    assert candidates[0].kind == "line"
    assert any(item.kind == "table" for item in candidates)
    assert plan.fallback_reason == "graph_degraded_using_relational_source"
    assert compile_postgresql_query(plan, catalog).sql

    unavailable = request.model_copy(
        update={
            "source": governed_source(
                "prediction_timeline",
                graph_readiness="degraded",
                relational_fallback_capability=False,
            )
        }
    )
    with pytest.raises(ValueError, match="relational fallback is unavailable"):
        build(unavailable)


def test_visualization_override_requires_migration_across_catalog_or_dataset_versions() -> None:
    request = semantic_request(
        "result_artifact",
        intent="comparison",
        dimensions=["asset_id"],
        measures=[SemanticMeasure(field_id="failure_probability", aggregation="max")],
    )
    catalog, plan, _ = build(request)
    compatible = VisualizationOverride(
        catalog_version=CATALOG_VERSION,
        dataset_version="canonical-ai4i-physics-v3.1",
        source_version="canonical-ai4i-physics-v3.1",
        chart_kind="bar",
        dimensions=["asset_id"],
        measures=[SemanticMeasure(field_id="failure_probability", aggregation="max")],
        channel_mapping={"x": "asset_id", "y": "failure_probability"},
    )
    assert validate_override(compatible, plan, catalog).status == "compatible"

    v2_override = compatible.model_copy(
        update={
            "catalog_version": "pm-semantic-catalog-v2.0.0",
            "dataset_version": "canonical-independent-v1.0",
            "source_version": "canonical-independent-v1.0",
        }
    )
    result = validate_override(v2_override, plan, catalog)
    assert result.status == "migration_required"
    assert set(result.reasons) == {
        "catalog_version_changed",
        "dataset_version_changed",
        "source_version_changed",
    }

    missing_field = compatible.model_copy(update={"dimensions": ["removed_v2_field"]})
    result = validate_override(missing_field, plan, catalog)
    assert result.status == "incompatible"
    assert result.reasons == ["fields_missing:removed_v2_field"]


def test_semantic_visualization_override_saves_and_restores_through_dashboard_preferences(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "semantic-override.db"
    identity = IdentityService(database_path, app_env="test", seed_demo=True)
    user, _, _, _ = identity.login(
        LoginRequest(email="manager@ontology.local", password="Manager!2026")
    )
    dashboards = DashboardService(str(database_path))
    resolved = dashboards.resolve(principal=user, workspace_id="manufacturing-demo")
    target = resolved.tabs[0].boards[0]
    override = VisualizationOverride(
        catalog_version=CATALOG_VERSION,
        dataset_version="canonical-ai4i-physics-v3.1",
        source_version="canonical-ai4i-physics-v3.1",
        chart_kind="bar",
        dimensions=["asset_id"],
        measures=[SemanticMeasure(field_id="failure_probability", aggregation="max")],
        channel_mapping={"x": "asset_id", "y": "failure_probability"},
    )
    target.settings["semantic_visualization_override"] = override.model_dump(mode="json")

    saved = dashboards.save_preferences(
        principal=user,
        request=DashboardPreferenceSaveRequest(
            workspace_id="manufacturing-demo",
            base_revision=resolved.preference_revision,
            active_tab_id=resolved.active_tab_id,
            tabs=resolved.tabs,
            parameter_state=resolved.parameter_state,
        ),
    )
    assert saved.preference_revision == 1
    saved_board = next(
        board
        for tab in saved.tabs
        for board in tab.boards
        if board.id == target.id
    )
    assert VisualizationOverride.model_validate(
        saved_board.settings["semantic_visualization_override"]
    ) == override

    reloaded = DashboardService(str(database_path)).resolve(
        principal=user,
        workspace_id="manufacturing-demo",
    )
    reloaded_board = next(
        board
        for tab in reloaded.tabs
        for board in tab.boards
        if board.id == target.id
    )
    assert VisualizationOverride.model_validate(
        reloaded_board.settings["semantic_visualization_override"]
    ) == override


class FakeProvider:
    name = "fake-provider"

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.last_payload: dict[str, Any] | None = None

    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_payload = payload
        return self.response


class FakeRuntimeService:
    def context(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str | None,
    ) -> DatasetVersionRuntimeContext:
        if dataset_version_id is None:
            raise KeyError("dataset_version_id")
        source = governed_source(
            "prediction_timeline",
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        ).model_copy(
            update={
                "dataset_id": "dataset-pm",
                "dataset_version_id": dataset_version_id,
            }
        )
        return authoritative_runtime_context(source, graph_status="failed")


def principal() -> Principal:
    return Principal(
        user_id="user-a",
        organization_id="org-a",
        email="user@example.com",
        display_name="User A",
        status="active",
        roles=["process_engineer"],
        permissions=["planner.board_recommend"],
        workspace_scopes=["workspace-a"],
        project_scopes=["project-a"],
        project_roles={"project-a": ["process_engineer"]},
        active_project_id="project-a",
        active_project_roles=["process_engineer"],
        is_admin=False,
        default_path="/app",
        landing_key="workspace",
    )


def test_llm_outside_candidate_falls_back_and_project_scope_is_enforced(tmp_path: Path) -> None:
    IdentityService(tmp_path / "semantic-planner.db", app_env="test", seed_demo=True)
    service = ManufacturingPredictiveMaintenanceService(
        ROOT,
        database_path=tmp_path / "semantic-planner.db",
    )
    provider = FakeProvider({"kind": "sankey", "rationale": "invented chart"})
    planner = OntologyDashboardPlannerService(
        service,
        provider=provider,
    )
    request = semantic_request(
        "cnc_sensor_observation",
        intent="relationship",
        dimensions=["product_type"],
        measures=[
            SemanticMeasure(field_id="torque_nm", aggregation="none"),
            SemanticMeasure(field_id="rotational_speed_rpm", aggregation="none"),
        ],
        use_llm=True,
    )
    response = planner.semantic_visualization_plan(
        principal=principal(),
        request=request,
        runtime_context=authoritative_runtime_context(request.source),
    )
    assert response.mode == "deterministic_fallback"
    assert response.fallback_reason == "ValueError"
    assert response.plan.chart_kind == "scatter"
    assert response.validation["llm_sql_generation"] is False
    assert response.validation["derived_expression_allowlist_only"] is True
    assert provider.last_payload is not None
    assert all(
        "source_expressions" not in field
        for field in provider.last_payload["semantic_fields"]
    )

    cross_project = request.model_copy(
        update={"source": governed_source("cnc_sensor_observation", project_id="project-b")}
    )
    with pytest.raises(AuthError) as error:
        planner.semantic_visualization_plan(
            principal=principal(),
            request=cross_project,
            runtime_context=authoritative_runtime_context(cross_project.source),
        )
    assert error.value.status_code == 403

    cross_organization = request.model_copy(
        update={
            "source": governed_source(
                "cnc_sensor_observation",
                organization_id="org-b",
            )
        }
    )
    with pytest.raises(AuthError) as error:
        planner.semantic_visualization_plan(
            principal=principal(),
            request=cross_organization,
            runtime_context=authoritative_runtime_context(cross_organization.source),
        )
    assert error.value.status_code == 403

    cross_workspace = request.model_copy(
        update={
            "source": governed_source(
                "cnc_sensor_observation",
                workspace_id="workspace-b",
            )
        }
    )
    with pytest.raises(AuthError) as error:
        planner.semantic_visualization_plan(
            principal=principal(),
            request=cross_workspace,
            runtime_context=authoritative_runtime_context(cross_workspace.source),
        )
    assert error.value.status_code == 403


def test_compatible_saved_override_applies_mapping_and_invalid_override_falls_back(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "semantic-override-planner.db"
    IdentityService(database_path, app_env="test", seed_demo=True)
    service = ManufacturingPredictiveMaintenanceService(ROOT, database_path=database_path)
    planner = OntologyDashboardPlannerService(service)
    compatible = VisualizationOverride(
        catalog_version=CATALOG_VERSION,
        dataset_version="canonical-ai4i-physics-v3.1",
        source_version="canonical-ai4i-physics-v3.1",
        chart_kind="bar",
        dimensions=["status_grade"],
        measures=[SemanticMeasure(field_id="asset_id", aggregation="count")],
        channel_mapping={"x": "status_grade", "y": "asset_id"},
    )
    base = semantic_request(
        "result_artifact",
        intent="comparison",
        dimensions=["asset_id"],
        measures=[SemanticMeasure(field_id="failure_probability", aggregation="max")],
        use_llm=True,
    ).model_copy(update={"saved_override": compatible})

    response = planner.semantic_visualization_plan(
        principal=principal(),
        request=base,
        runtime_context=authoritative_runtime_context(base.source),
    )
    assert response.mode == "deterministic"
    assert response.override_compatibility.status == "compatible"
    assert response.validation["override_applied"] is True
    assert response.plan.dimensions == ["status_grade"]
    assert response.plan.measures == [
        SemanticMeasure(field_id="asset_id", aggregation="count")
    ]
    assert response.plan.channel_mapping.x == "status_grade"
    assert response.plan.channel_mapping.y == "asset_id"
    assert response.plan.selection_reason == "Saved semantic visualization override applied."

    invalid_mapping = VisualizationOverride.model_validate(
        {
            **compatible.model_dump(mode="json"),
            "channel_mapping": {
                "x": "status_grade",
                "y": "failure_probability",
            },
        }
    )
    fallback = planner.semantic_visualization_plan(
        principal=principal(),
        request=base.model_copy(
            update={"saved_override": invalid_mapping, "use_llm": False}
        ),
        runtime_context=authoritative_runtime_context(base.source),
    )
    assert fallback.override_compatibility.status == "incompatible"
    assert fallback.validation["override_applied"] is False
    assert fallback.plan.dimensions == ["asset_id"]
    assert fallback.plan.measures == [
        SemanticMeasure(field_id="failure_probability", aggregation="max")
    ]


def test_server_dataset_context_rejects_spoofed_provenance_and_replaces_runtime_status(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "semantic-authority.db"
    IdentityService(database_path, app_env="test", seed_demo=True)
    service = ManufacturingPredictiveMaintenanceService(ROOT, database_path=database_path)
    planner = OntologyDashboardPlannerService(service)
    request = semantic_request(
        "prediction_timeline",
        intent="trend",
        dimensions=["asset_id"],
        measures=[SemanticMeasure(field_id="failure_probability", aggregation="avg")],
        time_field="observed_at",
        graph_readiness="ready",
    )
    context = authoritative_runtime_context(request.source, graph_status="failed")
    response = planner.semantic_visualization_plan(
        principal=principal(),
        request=request,
        runtime_context=context,
    )
    assert response.validation["server_authoritative_dataset_context"] is True
    assert response.plan.source.graph_readiness == "failed"
    assert response.plan.fallback_reason == "graph_failed_using_relational_source"
    assert response.plan.source.release_gates["tool_wear_continuity"]["pass"] is True
    assert response.plan.source.model_version == "independent-logreg-v3.1"
    assert response.plan.source.result_artifact_schema_version == "result-artifact-v1.0"

    spoofed = request.model_copy(
        update={
            "source": request.source.model_copy(
                update={"bundle_checksum_sha256": "b" * 64}
            )
        }
    )
    with pytest.raises(ValueError, match="checksum does not match"):
        planner.semantic_visualization_plan(
            principal=principal(),
            request=spoofed,
            runtime_context=context,
        )


def test_semantic_visualization_plan_api_contract_is_project_scoped_and_serializable(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "semantic-plan-api.db"
    identity = IdentityService(database_path, app_env="test", seed_demo=True)
    service = ManufacturingPredictiveMaintenanceService(ROOT, database_path=database_path)
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: service
    app.dependency_overrides[get_ontology_planner_service] = lambda: OntologyDashboardPlannerService(
        service
    )
    app.dependency_overrides[get_predictive_maintenance_runtime_service] = (
        lambda: FakeRuntimeService()
    )
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/auth/login",
                json={"email": "manager@ontology.local", "password": "Manager!2026"},
            )
            assert login.status_code == 200, login.text
            user = login.json()["user"]
            response = client.post(
                "/api/planner/visualizations/semantic-plan",
                headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
                json={
                    "source": {
                        "organization_id": user["organization_id"],
                        "project_id": user["active_project_id"],
                        "workspace_id": "manufacturing-demo",
                        "dataset_id": "dataset-pm",
                        "dataset_version_id": "dsv-v3-1",
                        "source_role": "prediction_timeline",
                        "dataset_version": "canonical-ai4i-physics-v3.1",
                        "source_version": "canonical-ai4i-physics-v3.1",
                        "bundle_checksum_sha256": CHECKSUM,
                        "model_version": "independent-logreg-v3.1",
                        "release_gates": {
                            "tool_wear_continuity": {"pass": True},
                        },
                        "graph_readiness": "degraded",
                        "relational_fallback_capability": True,
                    },
                    "goal": "risk timeline 시간 추세",
                    "intent": "trend",
                    "dimensions": ["asset_id"],
                    "measures": [
                        {"field_id": "failure_probability", "aggregation": "avg"}
                    ],
                    "time": {
                        "field_id": "observed_at",
                        "grain": "1h",
                        "window": {
                            "start": "2026-08-01T00:00:00+09:00",
                            "end": "2026-08-02T00:00:00+09:00",
                        },
                    },
                    "filters": [],
                    "order": [],
                    "limit": 500,
                    "field_cardinalities": {"asset_id": 100},
                    "result_profile": [],
                    "clamp_limits": True,
                    "use_llm": False,
                },
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["plan"]["chart_kind"] == "line"
            assert payload["plan"]["source"]["project_id"] == user["active_project_id"]
            assert payload["plan"]["fallback_reason"] == (
                "graph_failed_using_relational_source"
            )
            assert payload["compiled_query"]["sql"].startswith("SELECT ")
            assert payload["compiled_query"]["params"][0] == user["organization_id"]
            assert payload["validation"]["parameterized_postgresql"] is True
            assert payload["validation"]["release_gates_governance_only"] is True
            assert payload["validation"]["server_authoritative_dataset_context"] is True
            assert all(
                "source_expressions" not in field for field in payload["semantic_fields"]
            )
            assert payload["plan"]["source"]["release_gates"]["tool_wear_continuity"][
                "pass"
            ] is True
    finally:
        app.dependency_overrides.clear()

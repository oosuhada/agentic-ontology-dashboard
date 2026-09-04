"""Contract regression tests for the AssetDetailViewModel candidate contract.

Context: docs/operations/pdm-evidence-report-ui-integration-plan.md §3.1/§3.2 and
docs/operations/schema-definition.md §5.3 define AssetDetailViewModel as a V2
change proposal for `GET /objects/{asset_id}/detail-view`. It does not
replace the current Event Report API. Per §3.2 step 1, the documented
contract and test fixtures are added before any implementation. These tests
only fix the candidate shape and its scenario fixtures; they do not assert
that a Product API endpoint exists yet.

See docs/operations/asset-detail-report-viewmodel-frontend-field-audit.md for the
field audit this fixture set is derived from.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "schemas" / "asset-detail-view-model.schema.json"
PROCEDURE_GROUNDING_SCHEMA_PATH = ROOT / "contracts" / "schemas" / "procedure-grounding.schema.json"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "asset_detail_view_model"
INSPECTION_SOP_FIXTURE_ROOT = ROOT / "data" / "fixtures" / "inspection_sop"

SCENARIO_FILES = {
    "current_evidence_only": "current-evidence-only.json",
    "observation_series_present": "observation-series-present.json",
    "risk_timeline_present": "risk-timeline-present.json",
    "baseline_partially_missing": "baseline-partially-missing.json",
}

# risk.status_grade must only ever carry these 4 grades when available.
# data_quality_hold is represented separately at data_status.is_data_quality_hold,
# not as a 5th status_grade value (unlike the raw Product Result Artifact's
# status_grade, which still includes data_quality_hold at the producer level).
ALLOWED_STATUS_GRADES = {"normal", "attention", "warning", "critical"}

# runtime_inference/compatibility_fallback is only meaningful as a source
# discriminator for evidence and risk_series entries, never for
# data_status.source (canonical/fallback) or feature series quality_status
# (good/bad/unknown).
SOURCE_KIND_VALUES = {"runtime_inference", "compatibility_fallback"}
def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def schema() -> dict:
    return load_json(SCHEMA_PATH)


def procedure_grounding_schema() -> dict:
    return load_json(PROCEDURE_GROUNDING_SCHEMA_PATH)


def fixture(name: str) -> dict:
    return load_json(FIXTURE_ROOT / SCENARIO_FILES[name])


def schema_errors(payload: dict) -> list:
    return list(Draft202012Validator(schema()).iter_errors(payload))


@pytest.mark.parametrize("scenario", sorted(SCENARIO_FILES))
def test_fixture_matches_asset_detail_view_model_schema(scenario: str) -> None:
    assert schema_errors(fixture(scenario)) == []


def test_inspection_sop_fixtures_match_procedure_grounding_schema() -> None:
    fixtures = sorted(INSPECTION_SOP_FIXTURE_ROOT.glob("*.json"))

    assert fixtures
    validator = Draft202012Validator(procedure_grounding_schema())
    for path in fixtures:
        payload = load_json(path)
        assert list(validator.iter_errors(payload)) == []
        assert payload["source_kind"] == "demo_sop_fixture"
        assert payload["maturity"] == "fixture"
        assert "정비 판단 전 확인사항" in payload["guidance"]["allowed_ui_claims"]
        assert "교체 필요 확정" in payload["guidance"]["forbidden_ui_claims"]
        assert "비용상 최적 대안" in payload["guidance"]["forbidden_ui_claims"]
        assert "자동 승인 완료" in payload["guidance"]["forbidden_ui_claims"]
        assert payload["sensor_judgment"]["inspection_result_mapping"] == {
            "records_operational_fact": True,
            "does_not_create_maintenance_event": True,
            "manual_recommendation_requires_manager_acceptance": True,
        }
        assert "실제 고장 예방 입증" in payload["sensor_judgment"]["claim_boundaries"]["forbidden_claims"]


@pytest.mark.parametrize("scenario", sorted(SCENARIO_FILES))
def test_fixture_status_grade_is_one_of_four_grades(scenario: str) -> None:
    payload = fixture(scenario)

    assert payload["risk"]["status_grade"] in ALLOWED_STATUS_GRADES | {None}
    assert "data_quality_hold" not in ALLOWED_STATUS_GRADES


def test_schema_keeps_data_quality_hold_out_of_status_grade_enum() -> None:
    properties = schema()["properties"]

    assert "data_quality_hold" not in properties["risk"]["properties"]["status_grade"]["enum"]
    assert properties["risk"]["properties"]["status_grade"]["enum"] == [
        "normal",
        "attention",
        "warning",
        "critical",
        None,
    ]


def test_schema_separates_data_quality_hold_into_data_status() -> None:
    properties = schema()["properties"]

    assert "is_data_quality_hold" in properties["data_status"]["required"]
    assert properties["data_status"]["properties"]["is_data_quality_hold"]["type"] == "boolean"


def test_schema_allows_unknown_freshness_without_synthesizing_false() -> None:
    properties = schema()["properties"]

    assert properties["data_status"]["properties"]["is_stale"]["type"] == ["boolean", "null"]


def test_schema_requires_shared_evidence_snapshot_basis() -> None:
    payload = fixture("current_evidence_only")
    properties = schema()["properties"]

    assert "snapshot_basis" in schema()["required"]
    assert payload["snapshot_basis"] == {
        "artifact_id": payload["evidence"]["artifact_id"],
        "evidence_payload_reference": payload["evidence"]["evidence_payload_reference"],
        "asset_id": payload["asset"]["asset_id"],
        "event_id": None,
        "observed_at": payload["asset"]["observed_at"],
        "model_version": payload["evidence"]["model_version"],
        "dataset_version": payload["evidence"]["dataset_version"],
        "source_sha256": None,
    }
    assert properties["snapshot_basis"]["$ref"] == "#/$defs/evidenceSnapshotBasis"


def test_schema_keeps_feature_history_provenance_at_envelope_only() -> None:
    """Feature points carry time/value/quality only; shared provenance is not repeated."""
    properties = schema()["properties"]

    assert set(properties["evidence"]["properties"]["source_kind"]["enum"]) == SOURCE_KIND_VALUES
    assert set(properties["risk_series"]["items"]["properties"]["source_kind"]["enum"]) == SOURCE_KIND_VALUES
    assert set(properties["data_status"]["properties"]["source"]["enum"]) == {"canonical", "fallback"}

    feature_properties = properties["features"]["items"]["properties"]
    history_properties = feature_properties["history"]["properties"]
    point_properties = history_properties["points"]["items"]["properties"]
    assert "source_ref" in history_properties
    assert "source_ref" not in point_properties
    assert "source_kind" not in point_properties
    assert set(point_properties["quality_status"]["enum"]) == {"good", "bad", "unknown"}
    assert set(feature_properties["current"]["properties"]["quality_status"]["enum"]) == {
        "good",
        "bad",
        "unknown",
    }


def test_schema_accepts_nullable_criticality_and_extended_owner_domains() -> None:
    properties = schema()["properties"]

    assert properties["asset"]["properties"]["criticality"]["enum"] == ["low", "medium", "high", None]
    assert properties["asset"]["properties"]["criticality_source"]["enum"] == [
        "manual_initial_assessment",
        "equipment_master",
        "project_context",
        "unknown",
    ]
    gap_owner_domain = (
        properties["evidence"]["properties"]["gaps"]["items"]["properties"]["owner_domain"]["enum"]
    )
    assert set(gap_owner_domain) == {
        "diagnosis",
        "generator",
        "dataset",
        "equipment",
        "project",
        "operations",
        "maintenance",
        "report",
        "frontend",
        "unresolved",
    }


def test_missing_criticality_fixture_records_explicit_equipment_gap() -> None:
    payload = fixture("baseline_partially_missing")

    assert payload["asset"]["criticality"] is None
    assert payload["asset"]["criticality_basis"] == []
    assert {
        "field": "asset.criticality",
        "reason": "criticality_missing_or_unresolved",
        "owner_domain": "equipment",
    } in payload["evidence"]["gaps"]
    assert payload["review_priority"] is None


def test_review_priority_is_backend_view_model_data_not_frontend_fallback() -> None:
    payload = fixture("observation_series_present")

    assert payload["review_priority"] == {
        "level": "immediate",
        "reasons": [
            "risk.status_grade=critical",
            "asset.criticality=high",
            "operation_context.production_impact=high",
        ],
        "source_fields": [
            "risk.status_grade",
            "asset.criticality",
            "operation_context.production_impact",
        ],
    }


def test_schema_rejects_operations_prefixed_additional_property() -> None:
    payload = fixture("current_evidence_only")
    payload["operationsLegacyField"] = True

    errors = schema_errors(payload)

    assert any("Additional properties are not allowed" in error.message for error in errors)


def test_current_evidence_only_records_gaps_for_history_timeline_and_equipment() -> None:
    payload = fixture("current_evidence_only")
    gap_fields = {gap["field"] for gap in payload["evidence"]["gaps"]}

    assert payload["risk_series"] == []
    assert payload["equipment_history"] == []
    assert all(feature["history"]["points"] == [] for feature in payload["features"])
    assert {"features[].history.points", "risk_series", "equipment_history"} <= gap_fields


def test_observation_history_present_fills_feature_history_but_not_risk_series() -> None:
    payload = fixture("observation_series_present")
    gap_fields = {gap["field"] for gap in payload["evidence"]["gaps"]}

    assert any(feature["history"]["points"] for feature in payload["features"])
    assert payload["risk_series"] == []
    assert "risk_series" in gap_fields
    assert "features[].history.points" not in gap_fields


@pytest.mark.parametrize("scenario", sorted(SCENARIO_FILES))
def test_feature_history_is_pre_current_and_keeps_provenance_at_envelope(scenario: str) -> None:
    payload = fixture(scenario)
    current_observed_at = payload["asset"]["observed_at"]

    for feature in payload["features"]:
        assert feature["current"]["observed_at"] == current_observed_at
        points = feature["history"]["points"]
        observed_times = [point["observed_at"] for point in points]
        assert observed_times == sorted(observed_times)
        assert current_observed_at not in observed_times
        assert all(set(point) == {"observed_at", "value", "quality_status"} for point in points)
        if points:
            assert feature["history"]["source_ref"].startswith("observation://")


def test_risk_timeline_present_fills_risk_series_and_feature_history() -> None:
    payload = fixture("risk_timeline_present")
    gap_fields = {gap["field"] for gap in payload["evidence"]["gaps"]}

    assert payload["risk_series"]
    assert all(point["source_kind"] in SOURCE_KIND_VALUES for point in payload["risk_series"])
    assert any(feature["history"]["points"] for feature in payload["features"])
    assert "risk_series" not in gap_fields
    assert "features[].history.points" not in gap_fields
    # equipment_history still requires a dedicated Activity/Maintenance source.
    assert "equipment_history" in gap_fields


def test_risk_series_source_ref_does_not_point_at_legacy_precomputed_timeline() -> None:
    for scenario in SCENARIO_FILES:
        payload = fixture(scenario)
        for point in payload["risk_series"]:
            source_ref = point.get("source_ref", "")
            assert "precomputed_prediction_timeline" not in source_ref
            assert "/timeline" not in source_ref
            assert "gen_data/canonical/model_outputs" not in source_ref


def test_risk_series_source_ref_uses_runtime_history_contract() -> None:
    for scenario in SCENARIO_FILES:
        payload = fixture(scenario)
        for point in payload["risk_series"]:
            assert point["source_ref"].startswith("diagnosis-runtime-history://")


def test_baseline_partially_missing_keeps_current_value_and_history_but_gaps_baseline() -> None:
    payload = fixture("baseline_partially_missing")
    missing_baseline_features = [feature for feature in payload["features"] if feature["baseline"] is None]

    assert missing_baseline_features
    for feature in missing_baseline_features:
        assert feature["current"]["value"] is not None
        assert feature["history"]["points"], "current value/history must not be withheld just because baseline is missing"

    gap_fields = {gap["field"] for gap in payload["evidence"]["gaps"]}
    assert any(field.startswith("features[") and field.endswith("].baseline") for field in gap_fields)


@pytest.mark.parametrize("scenario", sorted(SCENARIO_FILES))
def test_fixture_never_synthesizes_values_for_gapped_fields(scenario: str) -> None:
    """Fields listed in evidence.gaps must stay null/empty, never a synthesized
    fallback value (0, an averaged number, a hardcoded 'normal')."""
    payload = fixture(scenario)
    gap_fields = {gap["field"] for gap in payload["evidence"]["gaps"]}

    if "risk_series" in gap_fields:
        assert payload["risk_series"] == []
    if "equipment_history" in gap_fields:
        assert payload["equipment_history"] == []
    if "features[].history.points" in gap_fields:
        assert all(feature["history"]["points"] == [] for feature in payload["features"])

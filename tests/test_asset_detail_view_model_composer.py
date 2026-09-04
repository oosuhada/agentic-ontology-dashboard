from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from systems.backend.app.operations.asset_detail_view_model import (
    AssetDetailRequest,
    AssetDetailViewModelService,
    compose_asset_detail_view_model,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads(
    (ROOT / "contracts" / "schemas" / "asset-detail-view-model.schema.json").read_text()
)
ARTIFACT = json.loads(
    (
        ROOT
        / "tests"
        / "fixtures"
        / "product_result_evidence_projection"
        / "producer-enriched-critical-artifact.json"
    ).read_text(encoding="utf-8")
)


class FakeAssetDetailReadPort:
    def __init__(
        self,
        *,
        artifact: dict[str, Any] | None = ARTIFACT,
        risk_source_ref: str = "diagnosis-runtime-history://CMP-S03-L03-01/2026-08-01T00:00:00+09:00",
    ) -> None:
        self.artifact = artifact
        self.risk_source_ref = risk_source_ref
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def asset_summary(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("asset_summary", kwargs))
        return {
            "asset_id": kwargs["asset_id"],
            "asset_type": "compressor",
            "display_name": "압축기 S03-L03-01",
            "site_id": "S03",
            "cell_id": "L03",
            "observed_at": "2026-08-01T00:00:00+09:00",
        }

    def latest_result_artifact(self, **kwargs: Any) -> dict[str, Any] | None:
        self.calls.append(("latest_result_artifact", kwargs))
        return self.artifact

    def feature_series(self, **kwargs: Any) -> dict[str, dict[str, Any]]:
        self.calls.append(("feature_series", kwargs))
        return {
            "rotation_raw": {
                "source_ref": "observation://CMP-S03-L03-01.rotation_raw",
                "points": [
                    {
                        "observed_at": "2026-07-31T21:00:00+09:00",
                        "value": 1810.0,
                        "quality_status": "good",
                    }
                ],
            }
        }

    def runtime_prediction_history(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("runtime_prediction_history", kwargs))
        return [
            {
                "observed_at": "2026-08-01T00:00:00+09:00",
                "failure_probability": 0.92,
                "status_grade": "critical",
                "prediction_id": "CMP-S03-L03-01#2026-08-01T00:00:00+09:00",
                "source_kind": "runtime_inference",
                "source_ref": self.risk_source_ref,
            }
        ]

    def equipment_history(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("equipment_history", kwargs))
        return []

    def data_status(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("data_status", kwargs))
        return {
            "source": "canonical",
            "is_stale": False,
            "last_updated_at": "2026-08-01T00:00:00+09:00",
            "warnings": [],
        }


def _request() -> AssetDetailRequest:
    return AssetDetailRequest(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        asset_id="CMP-S03-L03-01",
        start=datetime(2026, 7, 31, 18, tzinfo=timezone.utc),
        end=datetime(2026, 8, 1, 0, tzinfo=timezone.utc),
        dataset_version_id="canonical-ai4i-physics-v3.1",
        event_id="RESULT#CMP-S03-L03-01#2026-08-01T00:00:00+09:00",
        grain="1h",
    )


def test_service_reads_only_contracted_sources_and_returns_schema_valid_view_model() -> None:
    port = FakeAssetDetailReadPort()
    service = AssetDetailViewModelService(port)

    payload = service.detail_view(_request())

    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []
    assert [name for name, _ in port.calls] == [
        "latest_result_artifact",
        "asset_summary",
        "feature_series",
        "runtime_prediction_history",
        "equipment_history",
        "data_status",
    ]
    feature_call = dict(port.calls)["feature_series"]
    risk_call = dict(port.calls)["runtime_prediction_history"]
    artifact_call = dict(port.calls)["latest_result_artifact"]
    asset_call = dict(port.calls)["asset_summary"]
    status_call = dict(port.calls)["data_status"]
    assert artifact_call["event_id"] == _request().event_id
    assert asset_call["event_id"] == _request().event_id
    assert status_call["event_id"] == _request().event_id
    assert feature_call["dataset_version_id"] == "canonical-ai4i-physics-v3.1"
    assert feature_call["grain"] == "1h"
    assert risk_call["start"] == _request().start
    assert risk_call["end"] == _request().end


def test_latest_detail_view_anchors_history_and_snapshot_to_selected_event() -> None:
    port = FakeAssetDetailReadPort()
    service = AssetDetailViewModelService(port)

    payload = service.latest_detail_view(
        organization_id="org-1",
        project_id="project-1",
        workspace_id="workspace-1",
        asset_id="CMP-S03-L03-01",
        dataset_version_id="canonical-ai4i-physics-v3.1",
        event_id="RESULT#CMP-S03-L03-01#2026-08-01T00:00:00+09:00",
        history_window="24h",
    )

    feature_call = dict(port.calls)["feature_series"]
    assert feature_call["end"] == datetime(2026, 7, 31, 15, tzinfo=timezone.utc)
    assert feature_call["start"] == datetime(2026, 7, 30, 15, tzinfo=timezone.utc)
    assert payload["snapshot_basis"]["event_id"] == (
        "RESULT#CMP-S03-L03-01#2026-08-01T00:00:00+09:00"
    )


def test_service_rejects_mismatched_result_artifact_asset() -> None:
    artifact = json.loads(json.dumps(ARTIFACT))
    artifact["asset_id"] = "CMP-OTHER"
    service = AssetDetailViewModelService(
        FakeAssetDetailReadPort(artifact=artifact)
    )

    with pytest.raises(ValueError, match="asset_id"):
        service.detail_view(_request())


def test_service_does_not_accept_legacy_risk_history_sources_from_port() -> None:
    service = AssetDetailViewModelService(
        FakeAssetDetailReadPort(risk_source_ref="pm_prediction_timeline://CMP-S03-L03-01")
    )

    with pytest.raises(ValueError, match="prediction_results|unsupported"):
        service.detail_view(_request())


def test_service_requires_product_result_artifact() -> None:
    service = AssetDetailViewModelService(
        FakeAssetDetailReadPort(artifact=None)
    )

    with pytest.raises(KeyError, match="result artifact"):
        service.detail_view(_request())


def test_composer_builds_view_model_without_generator_raw_file_dependency() -> None:
    operation_context = {
        "context_id": "production-planning-context-v1",
        "source_type": "capacity_model",
        "temporal_scope": {
            "snapshot_id": "OPS-SNAPSHOT-2026-08-01-A-B",
            "timezone": "Asia/Seoul",
            "valid_from": "2026-08-01T00:00:00+09:00",
            "valid_to": "2026-08-02T00:00:00+09:00",
            "generated_at": "2026-08-01T00:00:00+09:00",
        },
        "production_plan": {
            "plan_id": "PLAN-2026-08-01-GS-DEMO",
            "plan_date": "2026-08-01",
            "planned_units": 16200,
            "product_mix": [{"variant": "M", "share": 0.3, "planned_units": 4860}],
        },
        "capacity_model": {
            "active_asset_count": 80,
            "planned_operating_hours": 16,
            "oee": 0.846,
            "standard_cycle_minutes_per_unit": 4.0,
            "asset_units_per_hour": 12.69,
            "daily_capacity_units": 16200,
            "basis": "80 assets, 16h/day, OEE 0.846, cycle 4.0min 기준",
        },
        "event_impact": {
            "event_id": "EVT-GS-002",
            "equipment_id": "CNC-S04-L04-01",
            "line": "S04-L04",
            "product_variant": "M",
            "screen_priority": "shift_inspection",
            "impact_status": "estimated",
            "estimated_lost_units": 25,
            "basis": {
                "estimated_downtime_minutes": 120,
                "asset_units_per_hour": 12.69,
                "formula": "120 / 60 * 12.69",
            },
        },
        "limitations": [
            "The calculated plan must not change failure_probability, status_grade, top_factors, or recommended_action."
        ],
    }
    payload = compose_asset_detail_view_model(
        asset={
            "asset_id": "CMP-S03-L03-01",
            "asset_type": "compressor",
            "display_name": "압축기 S03-L03-01",
            "site_id": "S03",
            "cell_id": "L03",
            "observed_at": "2026-08-01T00:00:00+09:00",
        },
        result_artifact=ARTIFACT,
        feature_series={
            "rotation_raw": {
                "source_ref": "observation://CMP-S03-L03-01.rotation_raw",
                "points": [
                    {
                        "observed_at": "2026-07-31T21:00:00+09:00",
                        "value": 1810.0,
                        "quality_status": "good",
                    }
                ],
            }
        },
        runtime_prediction_history=[
            {
                "observed_at": "2026-08-01T00:00:00+09:00",
                "failure_probability": 0.92,
                "status_grade": "critical",
                "prediction_id": "CMP-S03-L03-01#2026-08-01T00:00:00+09:00",
                "source_kind": "runtime_inference",
                "source_ref": "diagnosis-runtime-history://CMP-S03-L03-01/2026-08-01T00:00:00+09:00",
            }
        ],
        operation_context=operation_context,
        inspection_guidance={
            "rotating_assembly": {
                "source_type": "demo_sop_fixture",
                "sop_id": "SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
                "title": "CNC 회전/구동 계통 점검 참고 절차",
                "version": "demo-2026-08-28",
                "reference_location_label": "SOP 기준 참고 위치",
                "suggested_check_method": "회전/구동 계통의 체결, 마모, 이상 소음 여부를 확인합니다.",
                "checklist_draft": ["점검 전 설비 상태를 확인합니다."],
                "maintenance_review_prerequisites": {
                    "label": "정비 판단 전 확인사항",
                    "review_conditions": ["동일 부품 후보가 반복적으로 상위 위험 요인과 연결됩니다."],
                    "required_measurements": ["현재 센서 관측값과 최근 이력 비교"],
                    "human_review_questions": ["교체 전 생산 정지 가능 시간이 확인됐습니까?"],
                    "decision_boundary": "이 정보는 정비 판단 전 확인사항이며 정비 방법·시점 결정, 비용상 선호 대안, WorkOrder 생성 또는 정비 승인을 수행하지 않습니다.",
                },
                "safety_level": "caution",
                "requires_human_approval": True,
                "source_ref": "data/fixtures/inspection_sop/demo-cnc-inspection-guidance-v1-1.json#SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
                "disclaimer": "데모 SOP fixture 기반 참고 안내이며 Product Evidence가 확정한 점검 위치 또는 수리 지시가 아닙니다.",
            }
        },
        data_status={
            "source": "canonical",
            "is_stale": False,
            "last_updated_at": "2026-08-01T00:00:00+09:00",
            "warnings": [],
        },
    )

    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []
    assert payload["inspection_targets"][0]["component_id"] == "rotating_assembly"
    assert payload["inspection_targets"][0]["component_label"] == "회전/진동 계통"
    assert payload["inspection_targets"][0]["location_label"] is None
    assert payload["inspection_targets"][0]["inspection_method"] is None
    assert payload["inspection_targets"][0]["location_contract_id"] is None
    assert payload["inspection_targets"][0]["location_source_ref"] is None
    assert payload["inspection_targets"][0]["location_maturity"] is None
    assert payload["inspection_targets"][0]["inspection_guidance"] == {
        "source_type": "demo_sop_fixture",
        "sop_id": "SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
        "title": "CNC 회전/구동 계통 점검 참고 절차",
        "version": "demo-2026-08-28",
        "reference_location_label": "SOP 기준 참고 위치",
        "suggested_check_method": "회전/구동 계통의 체결, 마모, 이상 소음 여부를 확인합니다.",
        "checklist_draft": ["점검 전 설비 상태를 확인합니다."],
        "maintenance_review_prerequisites": {
            "label": "정비 판단 전 확인사항",
            "review_conditions": ["동일 부품 후보가 반복적으로 상위 위험 요인과 연결됩니다."],
            "required_measurements": ["현재 센서 관측값과 최근 이력 비교"],
            "human_review_questions": ["교체 전 생산 정지 가능 시간이 확인됐습니까?"],
            "decision_boundary": "이 정보는 정비 판단 전 확인사항이며 정비 방법·시점 결정, 비용상 선호 대안, WorkOrder 생성 또는 정비 승인을 수행하지 않습니다.",
        },
        "safety_level": "caution",
        "requires_human_approval": True,
        "source_ref": "data/fixtures/inspection_sop/demo-cnc-inspection-guidance-v1-1.json#SOP-DEMO-CNC-ROTATING-ASSEMBLY-001",
        "disclaimer": "데모 SOP fixture 기반 참고 안내이며 Product Evidence가 확정한 점검 위치 또는 수리 지시가 아닙니다.",
    }
    assert payload["inspection_targets"][0]["basis_refs"] == [
        "factor.1.rotation_raw",
        "sensor_evidence.sensors.rotation_raw",
    ]
    assert payload["inspection_targets"][0]["source_ref"].endswith("#component_hypotheses[0]")
    assert (
        payload["inspection_targets"][0]["unavailable_reason"]
        == "field_inspection_location_reference_unavailable"
    )
    assert payload["operation_context"]["source_type"] == "capacity_model"
    assert payload["operation_context"]["event_impact"]["estimated_lost_units"] == 25
    assert payload["risk_series"][0]["source_ref"].startswith("diagnosis-runtime-history://")
    assert "features[].history.points" not in {gap["field"] for gap in payload["evidence"]["gaps"]}
    assert "risk_series" not in {gap["field"] for gap in payload["evidence"]["gaps"]}


def test_composer_attaches_field_inspection_location_reference() -> None:
    payload = compose_asset_detail_view_model(
        asset={
            "asset_id": "CMP-S03-L03-01",
            "asset_type": "compressor",
            "display_name": "압축기 S03-L03-01",
            "observed_at": "2026-08-01T00:00:00+09:00",
        },
        result_artifact=ARTIFACT,
        feature_series={
            "rotation_raw": {
                "source_ref": "observation://CMP-S03-L03-01.rotation_raw",
                "points": [
                    {
                        "observed_at": "2026-07-31T21:00:00+09:00",
                        "value": 1810.0,
                        "quality_status": "good",
                    }
                ],
            }
        },
        runtime_prediction_history=[],
        equipment_history=[],
        inspection_locations={
            "rotating_assembly": {
                "contract_id": "ILR-DEMO-COMPRESSOR-001",
                "maturity": "fixture",
                "location_label": "모터 구동부 및 베어링 하우징",
                "inspection_method": "회전부 진동과 이상 소음을 확인합니다.",
                "source_ref": "data/fixtures/inspection_location/demo-compressor.json#rotating_assembly",
            }
        },
        data_status={
            "source": "canonical",
            "is_stale": False,
            "last_updated_at": "2026-08-01T00:00:00+09:00",
            "warnings": [],
        },
    )

    target = payload["inspection_targets"][0]
    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []
    assert target["location_label"] == "모터 구동부 및 베어링 하우징"
    assert target["inspection_method"] == "회전부 진동과 이상 소음을 확인합니다."
    assert target["location_contract_id"] == "ILR-DEMO-COMPRESSOR-001"
    assert target["location_source_ref"].endswith("#rotating_assembly")
    assert target["location_maturity"] == "fixture"
    assert target["unavailable_reason"] is None


def test_composer_excludes_current_instant_across_timezone_offsets() -> None:
    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=ARTIFACT,
        feature_series={
            "rotation_raw": {
                "source_ref": "observation://CMP-S03-L03-01.rotation_raw",
                "points": [
                    {
                        "observed_at": "2026-07-31T15:00:00Z",
                        "value": 1820.0,
                        "quality_status": "good",
                    },
                    {
                        "observed_at": "2026-07-31T14:00:00Z",
                        "value": 1800.0,
                        "quality_status": "good",
                    },
                ],
            }
        },
    )

    history = next(
        feature["history"] for feature in payload["features"] if feature["key"] == "rotation_raw"
    )
    assert [point["observed_at"] for point in history["points"]] == ["2026-07-31T14:00:00Z"]
    assert history["window"] == {
        "requested": "24h",
        "anchor_observed_at": "2026-07-31T15:00:00Z",
        "requested_start": "2026-07-30T15:00:00Z",
        "requested_end": "2026-07-31T15:00:00Z",
        "actual_start": "2026-07-31T14:00:00Z",
        "actual_end": "2026-07-31T14:00:00Z",
        "point_count": 1,
        "coverage_status": "partial",
    }


def test_composer_filters_feature_history_to_requested_window() -> None:
    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=ARTIFACT,
        feature_series={
            "rotation_raw": {
                "source_ref": "observation://CMP-S03-L03-01.rotation_raw",
                "points": [
                    {
                        "observed_at": "2026-07-30T14:59:59Z",
                        "value": 1700.0,
                        "quality_status": "good",
                    },
                    {
                        "observed_at": "2026-07-31T14:00:00Z",
                        "value": 1800.0,
                        "quality_status": "good",
                    },
                ],
            }
        },
        history_window="24h",
    )

    history = next(
        feature["history"] for feature in payload["features"] if feature["key"] == "rotation_raw"
    )
    assert [point["observed_at"] for point in history["points"]] == ["2026-07-31T14:00:00Z"]
    assert history["window"]["requested"] == "24h"
    assert history["window"]["actual_start"] == "2026-07-31T14:00:00Z"
    assert history["window"]["point_count"] == 1
    assert history["window"]["coverage_status"] == "partial"


def test_composer_rejects_conflicting_points_for_same_instant() -> None:
    with pytest.raises(ValueError, match="conflicting feature history"):
        compose_asset_detail_view_model(
            asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
            result_artifact=ARTIFACT,
            feature_series={
                "rotation_raw": {
                    "source_ref": "observation://CMP-S03-L03-01.rotation_raw",
                    "points": [
                        {
                            "observed_at": "2026-07-31T14:00:00Z",
                            "value": 1800.0,
                            "quality_status": "good",
                        },
                        {
                            "observed_at": "2026-07-31T23:00:00+09:00",
                            "value": 1810.0,
                            "quality_status": "good",
                        },
                    ],
                }
            },
        )


@pytest.mark.parametrize(
    "source_ref",
    [
        "gen_data/canonical/model_outputs/prediction_timeline.jsonl",
        "pm_prediction_timeline://CMP-S03-L03-01",
        "legacy://precomputed_prediction_timeline/CMP-S03-L03-01",
        "/timeline/CMP-S03-L03-01",
    ],
)
def test_composer_rejects_non_prediction_results_risk_series_sources(source_ref: str) -> None:
    with pytest.raises(ValueError, match="unsupported"):
        compose_asset_detail_view_model(
            asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
            result_artifact=ARTIFACT,
            runtime_prediction_history=[
                {
                    "observed_at": "2026-08-01T00:00:00+09:00",
                    "failure_probability": 0.92,
                    "status_grade": "critical",
                    "prediction_id": "prediction-1",
                    "source_ref": source_ref,
                }
            ],
        )


def test_composer_keeps_data_quality_hold_out_of_risk_status_grade() -> None:
    artifact = json.loads(json.dumps(ARTIFACT))
    artifact["status_grade"] = "data_quality_hold"
    artifact["data_quality_warnings"] = ["sensor packet failed identity validation"]

    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=artifact,
        runtime_prediction_history=[
            {
                "observed_at": "2026-08-01T00:00:00+09:00",
                "failure_probability": 0.92,
                "status_grade": "data_quality_hold",
                "prediction_id": "prediction-hold",
                "source_kind": "runtime_inference",
                "source_ref": "diagnosis-runtime-history://CMP-S03-L03-01/2026-08-01T00:00:00+09:00",
            }
        ],
        data_status={"source": "canonical", "is_stale": False, "warnings": []},
    )

    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []
    assert payload["risk"]["status_grade"] is None
    assert payload["risk_series"][0]["status_grade"] is None
    assert payload["data_status"]["is_data_quality_hold"] is True


def test_composer_uses_legacy_status_fallback_for_data_quality_hold() -> None:
    artifact = json.loads(json.dumps(ARTIFACT))
    artifact.pop("status_grade", None)
    artifact["status"] = "data_quality_hold"

    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=artifact,
    )

    assert payload["risk"]["status_grade"] is None
    assert payload["data_status"]["is_data_quality_hold"] is True


def test_composer_omits_missing_top_factor_evidence_field_id() -> None:
    artifact = json.loads(json.dumps(ARTIFACT))
    artifact["ranked_factor_evidence"] = []

    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=artifact,
    )

    top_factor = next(feature["top_factor"] for feature in payload["features"] if feature["top_factor"])
    assert "evidence_field_id" not in top_factor
    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []


def test_composer_preserves_unknown_freshness_as_null_with_warning() -> None:
    artifact = json.loads(json.dumps(ARTIFACT))
    artifact.pop("is_stale", None)

    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=artifact,
        data_status={"source": "canonical", "warnings": []},
    )

    assert payload["data_status"]["is_stale"] is None
    assert "data_status freshness fact unavailable" in payload["data_status"]["warnings"]
    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []


def test_composer_projects_canonical_evidence_gaps_to_view_model_schema() -> None:
    artifact = json.loads(json.dumps(ARTIFACT))
    artifact["evidence_payload"]["evidence_gaps"] = [
        {
            "gap_id": "gap.recommended_actions.unavailable",
            "field": "evidence_payload.recommended_actions",
            "reason": "missing_source",
            "required_source": "recommendation_policy_input",
            "owner_domain": "diagnosis",
            "display_policy": "show_limitation",
        },
        {
            "gap_id": "gap.operations.unavailable",
            "field": "equipment_history",
            "reason": "not_in_week2_scope",
            "required_source": "operations_activity_api",
            "owner_domain": "operations",
            "display_policy": "show_as_unavailable",
        },
    ]

    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=artifact,
        data_status={"source": "canonical", "is_stale": False, "warnings": []},
    )

    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []
    gap = next(
        gap
        for gap in payload["evidence"]["gaps"]
        if gap["field"] == "evidence_payload.recommended_actions"
    )
    assert set(gap) == {"field", "reason", "owner_domain"}
    assert "required_source=recommendation_policy_input" in gap["reason"]
    operations_gap = next(
        gap for gap in payload["evidence"]["gaps"] if gap["field"] == "equipment_history"
    )
    assert operations_gap["owner_domain"] == "operations"


def test_composer_preserves_asset_criticality_context_and_review_priority() -> None:
    payload = compose_asset_detail_view_model(
        asset={
            "asset_id": "CMP-S03-L03-01",
            "asset_type": "compressor",
            "criticality": "high",
            "criticality_basis": ["equipment master tier"],
            "criticality_source": "equipment_master",
            "maintenance_context": {
                "last_maintenance_days_ago": 12,
                "similar_events_30d": None,
                "open_work_order_exists": False,
            },
            "operation_context": {
                "load_level": None,
                "runtime_hours_7d": None,
                "production_impact": "high",
            },
        },
        result_artifact=ARTIFACT,
        data_status={"source": "canonical", "is_stale": False, "warnings": []},
    )

    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []
    assert payload["asset"]["criticality"] == "high"
    assert payload["asset"]["criticality_basis"] == ["equipment master tier"]
    assert payload["maintenance_context"]["open_work_order_exists"] is False
    assert payload["operation_context"]["production_impact"] == "high"
    assert payload["review_priority"] == {
        "level": "immediate",
        "reasons": [
            "risk.status_grade=critical",
            "asset.criticality=high",
            "maintenance_context.open_work_order_exists=False",
            "operation_context.production_impact=high",
        ],
        "source_fields": [
            "risk.status_grade",
            "asset.criticality",
            "maintenance_context.open_work_order_exists",
            "operation_context.production_impact",
        ],
    }


def test_composer_does_not_default_missing_criticality_or_context() -> None:
    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=ARTIFACT,
        data_status={"source": "canonical", "is_stale": False, "warnings": []},
    )

    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []
    assert payload["asset"]["criticality"] is None
    assert payload["asset"]["criticality_basis"] == []
    assert payload["asset"]["criticality_source"] == "unknown"
    assert payload["maintenance_context"] == {
        "last_maintenance_days_ago": None,
        "similar_events_30d": None,
        "open_work_order_exists": None,
    }
    assert payload["operation_context"] == {
        "load_level": None,
        "runtime_hours_7d": None,
        "production_impact": None,
    }
    assert payload["review_priority"] is None
    gaps = {(gap["field"], gap["reason"], gap["owner_domain"]) for gap in payload["evidence"]["gaps"]}
    assert ("asset.criticality", "criticality_missing_or_unresolved", "equipment") in gaps
    assert ("review_priority", "review_priority_inputs_missing_or_unresolved", "report") in gaps


def test_composer_does_not_synthesize_missing_criticality_basis() -> None:
    payload = compose_asset_detail_view_model(
        asset={
            "asset_id": "CMP-S03-L03-01",
            "asset_type": "compressor",
            "criticality": "medium",
            "criticality_source": "equipment_master",
            "operation_context": {"production_impact": "medium"},
        },
        result_artifact=ARTIFACT,
        data_status={"source": "canonical", "is_stale": False, "warnings": []},
    )

    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []
    assert payload["asset"]["criticality"] == "medium"
    assert payload["asset"]["criticality_basis"] == []
    gaps = {(gap["field"], gap["reason"], gap["owner_domain"]) for gap in payload["evidence"]["gaps"]}
    assert ("asset.criticality_basis", "criticality_basis_missing_or_unresolved", "equipment") in gaps


def test_composer_requires_production_impact_for_review_priority() -> None:
    payload = compose_asset_detail_view_model(
        asset={
            "asset_id": "CMP-S03-L03-01",
            "asset_type": "compressor",
            "criticality": "high",
            "criticality_basis": ["equipment master tier"],
            "criticality_source": "equipment_master",
            "maintenance_context": {"last_maintenance_days_ago": 12},
        },
        result_artifact=ARTIFACT,
        data_status={"source": "canonical", "is_stale": False, "warnings": []},
    )

    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []
    assert payload["review_priority"] is None
    gaps = {(gap["field"], gap["reason"], gap["owner_domain"]) for gap in payload["evidence"]["gaps"]}
    assert ("review_priority", "review_priority_inputs_missing_or_unresolved", "report") in gaps


def test_composer_preserves_nullable_baseline_as_gap_without_type_error() -> None:
    artifact = json.loads(json.dumps(ARTIFACT))
    sensor = artifact["evidence_payload"]["sensor_evidence"]["sensors"]["rotation_raw"]
    sensor["basis"]["baseline_mean"] = None
    sensor["basis"]["baseline_std"] = None

    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=artifact,
        feature_series={
            "rotation_raw": {
                "source_ref": "observation://CMP-S03-L03-01.rotation_raw",
                "points": [
                    {
                        "observed_at": "2026-07-31T21:00:00+09:00",
                        "value": 1810.0,
                        "quality_status": "good",
                    }
                ],
            }
        },
        data_status={"source": "canonical", "is_stale": False, "warnings": []},
    )

    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []
    rotation = next(feature for feature in payload["features"] if feature["key"] == "rotation_raw")
    assert rotation["baseline"] is None
    assert any(gap["field"] == "features[0].baseline" for gap in payload["evidence"]["gaps"])


def test_composer_rejects_raw_generator_feature_series_sources() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        compose_asset_detail_view_model(
            asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
            result_artifact=ARTIFACT,
            feature_series={
                "rotation_raw": {
                    "source_ref": "gen_data/output/sensor/CMP-S03-L03-01/_log.jsonl",
                    "points": [
                        {
                            "observed_at": "2026-07-31T21:00:00+09:00",
                            "value": 1810.0,
                            "quality_status": "good",
                        }
                    ],
                }
            },
        )


def test_composer_marks_missing_series_as_gaps_without_synthesizing_values() -> None:
    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=ARTIFACT,
    )

    gap_fields = {gap["field"] for gap in payload["evidence"]["gaps"]}
    assert {"features[].history.points", "risk_series", "equipment_history"} <= gap_fields
    assert payload["risk_series"] == []
    assert all(feature["history"]["points"] == [] for feature in payload["features"])


def test_composer_projects_closed_loop_lifecycle_action_and_timeline() -> None:
    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=ARTIFACT,
        closed_loop={
            "work_orders": [
                {
                    "work_order_id": "WO-INS-001",
                    "work_type": "inspection",
                    "status": "requested",
                    "assigned_to": None,
                    "actor_display_name": "윤하린",
                    "created_at": "2026-08-06T03:10:00Z",
                    "updated_at": "2026-08-06T03:10:00Z",
                }
            ],
            "activities": [
                {
                    "activity_id": "ACT-001",
                    "activity_type": "work_order.requested",
                    "work_type": "inspection",
                    "actor_display_name": "윤하린",
                    "before_status": None,
                    "after_status": "requested",
                    "created_at": "2026-08-06T03:10:00Z",
                    "work_order_id": "WO-INS-001",
                }
            ],
            "available_actions": [
                {
                    "action_id": "approve_inspection_work_order",
                    "target_type": "work_order",
                    "target_id": "WO-INS-001",
                    "label": "점검 승인",
                    "disabled_reason": None,
                }
            ],
            "runtime_status": None,
        },
    )

    assert list(Draft202012Validator(SCHEMA).iter_errors(payload)) == []
    closed_loop = payload["closed_loop"]
    assert closed_loop["lifecycle_summary"] == {
        "current_step": "inspection_requested",
        "current_step_label": "점검 승인 대기",
        "completed_steps": ["prediction", "evidence", "decision"],
        "next_step": "inspection_approved",
        "source": "backend_closed_loop_policy",
    }
    assert closed_loop["primary_action"] == {
        "action_id": "approve_inspection_work_order",
        "target_type": "work_order",
        "target_id": "WO-INS-001",
        "label": "점검 승인",
        "owner_role": "process_manager",
        "owner_label": "생산 운영 의사결정자",
        "disabled_reason": None,
        "requires_input": False,
    }
    assert closed_loop["timeline"][0] == {
        "timeline_id": "ACT-001",
        "event_type": "work_order.requested",
        "label": "작업요청 생성",
        "status": "completed",
        "actor_display_name": "윤하린",
        "occurred_at": "2026-08-06T03:10:00Z",
        "target_type": "work_order",
        "target_id": "WO-INS-001",
    }


def test_composer_preserves_empty_recommendation_as_gap_without_synthesizing_action() -> None:
    artifact = json.loads(json.dumps(ARTIFACT))
    artifact["evidence_payload"]["recommended_actions"] = []

    payload = compose_asset_detail_view_model(
        asset={"asset_id": "CMP-S03-L03-01", "asset_type": "compressor"},
        result_artifact=artifact,
    )

    gap_fields = {gap["field"] for gap in payload["evidence"]["gaps"]}
    assert "evidence_payload.recommended_actions" in gap_fields
    assert "recommended_actions" not in payload
    assert "available_actions" not in payload

from __future__ import annotations

import copy
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator, FormatChecker

from app.dependencies import current_principal, get_identity_service, require_csrf
from app.diagnosis.runtime_router import internal_router, router
from app.diagnosis.runtime_service import PredictiveMaintenanceRuntimeService
from app.diagnosis.materialization import (
    ProductResultMaterializationCommand,
    ProductResultMaterializationService,
)
from app.diagnosis.runtime_schema import PredictionResultBatch
from app.identity import AuthError, Principal
from app.identity.identity_router import identity_http_status


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "contracts" / "examples" / "prediction-result-batch" / "prediction-result-batch-v1.json"
SCHEMA = ROOT / "contracts" / "schemas" / "prediction-result-batch.schema.json"


class FakeIdentity:
    def require_permission(self, principal: Principal, permission: str) -> None:
        assert permission in principal.permissions

    def require_project(self, principal: Principal, project_id: str) -> None:
        assert project_id in principal.project_scopes

    def require_workspace(self, principal: Principal, workspace_id: str) -> None:
        assert workspace_id in principal.workspace_scopes


class FakeInboxRepository:
    def __init__(
        self,
        *,
        assets: set[str] | None = None,
        asset_metadata: dict[str, dict[str, Any]] | None = None,
        fail_promotions_once: bool = False,
    ) -> None:
        self.assets = assets or {"CNC-001"}
        self.asset_metadata = asset_metadata or {}
        self.fail_promotions_once = fail_promotions_once
        self.batches: dict[str, str] = {}
        self.items: dict[str, str] = {}
        self.saved: list[dict[str, Any]] = []
        self.promotions: list[dict[str, Any]] = []

    @staticmethod
    def clock_now() -> datetime:
        return datetime(2026, 8, 27, tzinfo=timezone.utc)

    def assets_exist_in_workspace(self, **kwargs: Any) -> set[str]:
        return set(kwargs["asset_ids"]) & self.assets

    def save_prediction_batch_inbox(self, **kwargs: Any) -> dict[str, Any]:
        batch_id = kwargs["batch_id"]
        payload_sha256 = kwargs["payload_sha256"]
        status = kwargs["validation_status"]
        reason = kwargs["rejection_reason"]
        if batch_id in self.batches:
            if self.batches[batch_id] == payload_sha256:
                status = "duplicate"
                reason = None
            else:
                status = "conflict"
                reason = "batch_payload_conflict"

        persisted = []
        for receipt in kwargs["item_receipts"]:
            event_id = receipt["event_id"]
            item_sha = receipt["payload_sha256"]
            item_status = receipt["validation_status"]
            item_reason = receipt["rejection_reason"]
            if event_id in self.items:
                if self.items[event_id] == item_sha:
                    item_status = "duplicate"
                    item_reason = None
                else:
                    item_status = "conflict"
                    item_reason = "event_payload_conflict"
            else:
                self.items[event_id] = item_sha
            persisted.append(
                {
                    "event_id": event_id,
                    "payload_sha256": item_sha,
                    "validation_status": item_status,
                    "rejection_reason": item_reason,
                }
            )

        if any(item["validation_status"] == "conflict" for item in persisted):
            status = "conflict"
            reason = reason or "one or more items conflicted"
        elif any(item["validation_status"] == "rejected" for item in persisted):
            status = "rejected"
            reason = reason or "one or more items were rejected"
        elif persisted and all(item["validation_status"] == "duplicate" for item in persisted):
            status = "duplicate"
            reason = None
        self.batches.setdefault(batch_id, payload_sha256)
        row = {
            "batch_id": batch_id,
            "payload_sha256": payload_sha256,
            "validation_status": status,
            "rejection_reason": reason,
            "raw_payload": kwargs["raw_payload"],
            "item_receipts": persisted,
        }
        self.saved.append(row)
        return row

    def prediction_batch_promotion_context(self, **kwargs: Any) -> dict[str, Any] | None:
        batch_id = kwargs["batch_id"]
        row = next(
            (
                item
                for item in reversed(self.saved)
                if item["batch_id"] == batch_id and item["validation_status"] == "accepted"
            ),
            None,
        )
        if row is None:
            return None
        payload = row["raw_payload"]
        asset_rows = {
            asset_id: {
                "asset_id": asset_id,
                "asset_type": "cnc",
                "site_id": "site-1",
                "cell_id": "cell-1",
                **self.asset_metadata.get(asset_id, {}),
            }
            for asset_id in self.assets
        }
        return {
            "dataset_version_id": "dataset-version-test",
            "dataset_name": "Dataset Test",
            "bundle_checksum_sha256": "f" * 64,
            "record_count": 1,
            "dataset_status": "ready",
            "raw_payload": payload,
            "assets": asset_rows,
        }

    def save_prediction_batch_promotions(self, **kwargs: Any) -> dict[str, Any]:
        if self.fail_promotions_once:
            self.fail_promotions_once = False
            raise RuntimeError("simulated promotion outage")
        receipts = []
        for promotion in kwargs["promotions"]:
            existing = next(
                (
                    item
                    for item in self.promotions
                    if item["artifact"]["artifact_id"] == promotion["artifact"]["artifact_id"]
                ),
                None,
            )
            if existing is None:
                self.promotions.append(promotion)
                receipts.append(
                    {
                        "event_id": promotion["event_id"],
                        "promotion_status": "promoted",
                        "product_result_id": promotion["prediction_result_id"],
                        "artifact_id": promotion["artifact"]["artifact_id"],
                        "reason": None,
                    }
                )
            else:
                receipts.append(
                    {
                        "event_id": promotion["event_id"],
                        "promotion_status": "already_promoted",
                        "product_result_id": existing["prediction_result_id"],
                        "artifact_id": existing["artifact"]["artifact_id"],
                        "reason": None,
                    }
                )
        return {"item_receipts": receipts}


def principal() -> Principal:
    return Principal(
        user_id="user-1",
        organization_id="org-ontology-demo",
        email="ml@example.com",
        display_name="ML Validator",
        status="active",
        roles=["ml_validator"],
        permissions=["predictions.ingest"],
        workspace_scopes=["manufacturing-demo"],
        project_scopes=["manufacturing-demo-project"],
        active_project_id="manufacturing-demo-project",
        active_project_roles=["ml_validator"],
        is_admin=False,
        default_path="/app/projects/manufacturing-demo-project/operations",
        landing_key="operations",
    )


def load_payload() -> dict[str, Any]:
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload["results"][0]["payload_sha256"] = (
        PredictiveMaintenanceRuntimeService._prediction_item_sha256(payload["results"][0])
    )
    return payload


def make_service(repository: FakeInboxRepository | None = None) -> PredictiveMaintenanceRuntimeService:
    return PredictiveMaintenanceRuntimeService(repository or FakeInboxRepository())


def add_auth_error_handler(app: FastAPI) -> None:
    @app.exception_handler(AuthError)
    async def auth_error_handler(_, exc: AuthError):
        return JSONResponse(
            status_code=identity_http_status(exc),
            content={"detail": exc.message},
        )


def receive(
    service: PredictiveMaintenanceRuntimeService,
    payload: dict[str, Any],
):
    return service.receive_prediction_result_batch(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        payload=payload,
    )


def test_prediction_inbox_accepts_valid_batch_without_product_result() -> None:
    receipt = receive(make_service(), load_payload())

    assert receipt.validation_status == "accepted"
    assert receipt.accepted_results == 1
    assert receipt.promotion_status == "not_promoted"
    assert receipt.product_result_created is False


def test_prediction_batch_promotion_creates_product_result_artifact() -> None:
    repository = FakeInboxRepository()
    service = make_service(repository)
    payload = load_payload()
    assert receive(service, payload).validation_status == "accepted"

    receipt = service.promote_prediction_result_batch(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        batch_id=payload["batch_id"],
    )

    assert receipt.promotion_status == "promoted"
    assert receipt.product_result_created is True
    assert receipt.promoted_results == 1
    assert receipt.product_result_ids == [repository.promotions[0]["prediction_result_id"]]
    artifact = repository.promotions[0]["artifact"]
    assert artifact["schema_version"] == "result-artifact-v1.0"
    assert artifact["provenance"]["source_type"] == "product_runtime_inference"
    assert artifact["provenance"]["canonical_source_mutated"] is False
    assert artifact["evidence_payload"]["recommended_actions"][0]["action_id"] == (
        "review_shutdown"
    )
    assert artifact["evidence_payload"]["evidence_gaps"]
    summary = service._product_result_evidence_summary(artifact)
    assert summary is not None
    assert summary.available is True
    assert summary.evidence_payload_reference == {
        "source": "product_result_artifact",
        "reference": artifact["artifact_id"],
        "generated_by": "systems.backend.diagnosis.generator_batch_promotion",
    }
    assert summary.batch_lineage is not None
    assert summary.batch_lineage.batch_id == payload["batch_id"]
    assert summary.batch_lineage.event_id == payload["results"][0]["event_id"]
    assert summary.batch_lineage.source_kind == payload["source_context"]["source_kind"]
    assert summary.batch_lineage.source_reference.startswith(
        f"prediction-result-batch:{payload['batch_id']}:event:"
    )
    assert [field.field_id for field in summary.source_fields] == [
        "prediction_batch.score",
        "prediction_batch.payload_sha256",
        "prediction_batch.model_artifact_manifest_sha256",
        "model_artifact.selected_threshold",
        "asset.criticality",
        "backend_policy.severity_rules",
    ]
    assert summary.recommended_actions[0].requires_human_approval is True
    assert summary.evidence_gaps[0].display_policy == "show_limitation"

    overlay_artifact = copy.deepcopy(artifact)
    overlay_artifact["lineage"]["source_context"]["source_kind"] = (
        "maintenance_replay_overlay"
    )
    overlay_artifact["lineage"]["source_context"]["lineage"] = {
        "simulation_session_id": "simulation-session-1",
        "overlay_branch_id": "overlay-branch-1",
        "history_segment_id": "history-segment-1",
        "maintenance_event_id": "maintenance-event-1",
        "maintenance_action_id": "maintenance-action-1",
        "state_version": 3,
    }
    overlay_summary = service._product_result_evidence_summary(overlay_artifact)
    assert overlay_summary is not None
    assert overlay_summary.batch_lineage is not None
    assert overlay_summary.batch_lineage.maintenance_event_id == "maintenance-event-1"
    assert overlay_summary.batch_lineage.overlay_branch_id == "overlay-branch-1"
    assert overlay_summary.batch_lineage.state_version == 3


def test_prediction_batch_promotion_absorbs_optional_generator_explanation() -> None:
    repository = FakeInboxRepository()
    service = make_service(repository)
    payload = load_payload()
    payload["results"][0]["explanation"] = {
        "top_factors": [
            {
                "feature": "torque_nm_6h_mean",
                "display_name": "구동 토크 6시간 평균",
                "feature_value": 74.2,
                "signed_contribution": 0.42,
                "direction": "risk_up",
                "explanation_method": "linear_logit_contribution",
                "source_ref": {
                    "uri": "s3://generator/features/evt-001.json",
                    "sha256": "e" * 64,
                },
            },
            {
                "feature": "motor_power_6h_change",
                "display_name": "모터 출력 6시간 변화",
                "feature_value": 1.8,
                "signed_contribution": 0.25,
                "direction": "risk_up",
                "explanation_method": "linear_logit_contribution",
            },
        ],
        "confidence_label": "medium",
        "explanation_method": "linear_logit_contribution",
        "feature_snapshot_ref": {
            "uri": "s3://generator/features/evt-001.json",
            "sha256": "f" * 64,
        },
        "sensor_window_ref": {
            "uri": "s3://generator/windows/evt-001.json",
            "sha256": "e" * 64,
        },
        "display_labels": {"torque_nm_6h_mean": "구동 토크 6시간 평균"},
    }
    payload["results"][0]["payload_sha256"] = (
        PredictiveMaintenanceRuntimeService._prediction_item_sha256(payload["results"][0])
    )

    assert receive(service, payload).validation_status == "accepted"
    receipt = service.promote_prediction_result_batch(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        batch_id=payload["batch_id"],
    )

    assert receipt.promotion_status == "promoted"
    artifact = repository.promotions[0]["artifact"]
    assert [factor["feature"] for factor in artifact["top_factors"][:2]] == [
        "torque_nm_6h_mean",
        "motor_power_6h_change",
    ]
    assert artifact["ranked_factor_evidence"][0]["display_name"] == (
        "구동 토크 6시간 평균"
    )
    source_field_ids = {
        field["field_id"]
        for field in artifact["evidence_payload"]["source_fields"]
    }
    assert "generator_explanation.1.torque_nm_6h_mean" in source_field_ids
    assert artifact["recommended_action"]["action"] == "review_shutdown"


def test_product_result_materialization_exposes_shared_evidence_projection() -> None:
    repository = FakeInboxRepository()
    service = make_service(repository)
    payload = load_payload()
    assert receive(service, payload).validation_status == "accepted"
    context = repository.prediction_batch_promotion_context(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        batch_id=payload["batch_id"],
    )
    assert context is not None
    batch = PredictionResultBatch.model_validate(context["raw_payload"])
    item = batch.results[0]

    materialized = ProductResultMaterializationService().materialize(
        ProductResultMaterializationCommand(
            organization_id="org-ontology-demo",
            project_id="manufacturing-demo-project",
            workspace_id="manufacturing-demo",
            dataset_version_id=str(context["dataset_version_id"]),
            asset=context["assets"][item.asset_id],
            batch=batch,
            item=item,
        )
    )

    assert materialized.materialized is True
    assert materialized.replayed is False
    assert materialized.artifact_id == materialized.artifact["artifact_id"]
    assert materialized.prediction_result_id == materialized.prediction_result.prediction_id
    assert materialized.evidence_projection["artifact_reference"]["artifact_id"] == (
        materialized.artifact_id
    )
    assert materialized.evidence_projection["artifact_reference"][
        "evidence_payload_reference"
    ] == materialized.artifact["provenance"]["evidence_payload_reference"]


def test_prediction_batch_promotion_uses_model_selected_threshold_for_positive_score() -> None:
    repository = FakeInboxRepository()
    service = make_service(repository)
    payload = load_payload()
    payload["results"][0]["score"] = 0.22
    payload["model_set"]["models"][0]["selected_threshold"] = 0.2
    payload["results"][0]["payload_sha256"] = (
        PredictiveMaintenanceRuntimeService._prediction_item_sha256(payload["results"][0])
    )
    assert receive(service, payload).validation_status == "accepted"

    receipt = service.promote_prediction_result_batch(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        batch_id=payload["batch_id"],
    )

    assert receipt.promotion_status == "promoted"
    artifact = repository.promotions[0]["artifact"]
    assert artifact["threshold"] == 0.2
    assert artifact["status_grade"] == "attention"
    assert artifact["predicted_failure_type"] == "failure_risk"
    assert artifact["recommended_action"]["action"] == "request_inspection"
    assert artifact["provenance"]["model_artifact"]["selected_threshold"] == 0.2


def test_prediction_batch_promotion_applies_high_criticality_warning_adjustment() -> None:
    repository = FakeInboxRepository(
        asset_metadata={"CNC-001": {"criticality": "high"}},
    )
    service = make_service(repository)
    payload = load_payload()
    payload["results"][0]["score"] = 0.53
    payload["model_set"]["models"][0]["selected_threshold"] = 0.8
    payload["results"][0]["payload_sha256"] = (
        PredictiveMaintenanceRuntimeService._prediction_item_sha256(payload["results"][0])
    )
    assert receive(service, payload).validation_status == "accepted"

    receipt = service.promote_prediction_result_batch(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        batch_id=payload["batch_id"],
    )

    assert receipt.promotion_status == "promoted"
    artifact = repository.promotions[0]["artifact"]
    assert artifact["status_grade"] == "warning"
    assert artifact["predicted_failure_type"] == "no_significant_risk"
    assert artifact["recommended_action"]["action"] == "request_inspection"
    assert artifact["evidence_payload"]["recommended_actions"][0]["kind"] == (
        "request_inspection"
    )
    gap_ids = {gap["gap_id"] for gap in artifact["evidence_payload"]["evidence_gaps"]}
    assert "generator-batch-asset-criticality-unavailable" not in gap_ids


def test_prediction_batch_promotion_is_idempotent() -> None:
    repository = FakeInboxRepository()
    service = make_service(repository)
    payload = load_payload()
    assert receive(service, payload).validation_status == "accepted"

    first = service.promote_prediction_result_batch(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        batch_id=payload["batch_id"],
    )
    second = service.promote_prediction_result_batch(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
        workspace_id="manufacturing-demo",
        batch_id=payload["batch_id"],
    )

    assert first.promotion_status == "promoted"
    assert second.promotion_status == "already_promoted"
    assert second.already_promoted_results == 1


def test_prediction_inbox_duplicate_reuses_existing_event() -> None:
    service = make_service()
    payload = load_payload()

    assert receive(service, payload).validation_status == "accepted"
    duplicate = receive(service, payload)

    assert duplicate.validation_status == "duplicate"
    assert duplicate.duplicate_results == 1


def test_prediction_inbox_conflicts_same_event_different_payload() -> None:
    service = make_service()
    payload = load_payload()
    assert receive(service, payload).validation_status == "accepted"

    changed = copy.deepcopy(payload)
    changed["batch_id"] = "batch-conflicting"
    changed["results"][0]["score"] = 0.7
    changed["results"][0]["payload_sha256"] = (
        PredictiveMaintenanceRuntimeService._prediction_item_sha256(changed["results"][0])
    )
    conflict = receive(service, changed)

    assert conflict.validation_status == "conflict"
    assert conflict.conflict_results == 1
    assert "Product" not in (conflict.rejection_reason or "")


def test_prediction_inbox_rejects_payload_sha256_mismatch() -> None:
    payload = load_payload()
    payload["results"][0]["score"] = 0.7

    receipt = receive(make_service(), payload)

    assert receipt.validation_status == "rejected"
    assert receipt.rejected_results == 1
    assert "payload_sha256_mismatch" in (receipt.rejection_reason or "")


def test_prediction_inbox_rejects_model_artifact_manifest_checksum_mismatch() -> None:
    payload = load_payload()
    payload["results"][0]["model_artifact_manifest_sha256"] = "e" * 64
    payload["results"][0]["payload_sha256"] = (
        PredictiveMaintenanceRuntimeService._prediction_item_sha256(payload["results"][0])
    )

    receipt = receive(make_service(), payload)

    assert receipt.validation_status == "rejected"
    assert receipt.rejected_results == 1
    assert "model_artifact_manifest_sha256_mismatch" in (
        receipt.rejection_reason or ""
    )


def test_prediction_inbox_rejects_duplicate_model_set_identity() -> None:
    payload = load_payload()
    payload["model_set"]["models"].append(copy.deepcopy(payload["model_set"]["models"][0]))

    receipt = receive(make_service(), payload)

    assert receipt.validation_status == "rejected"
    assert receipt.rejected_results == 1
    assert "model_set_duplicate_identity" in (receipt.rejection_reason or "")


def test_prediction_inbox_rejects_official_schema_violation_before_pydantic() -> None:
    payload = load_payload()
    payload["results"][0]["source_ref"]["sha256"] = "0" * 64
    payload["results"][0]["payload_sha256"] = (
        PredictiveMaintenanceRuntimeService._prediction_item_sha256(payload["results"][0])
    )

    receipt = receive(make_service(), payload)

    assert receipt.validation_status == "rejected"
    assert receipt.received_results == 0
    assert "schema_invalid" in (receipt.rejection_reason or "")
    assert "source_ref" in (receipt.rejection_reason or "")


def test_prediction_inbox_rejects_missing_predicted_provenance_checksum() -> None:
    payload = load_payload()
    payload["results"][0]["label_schema_sha256"] = None

    receipt = receive(make_service(), payload)

    assert receipt.validation_status == "rejected"
    assert receipt.received_results == 0
    assert "schema_invalid" in (receipt.rejection_reason or "")
    assert "label_schema_sha256" in (receipt.rejection_reason or "")


def test_prediction_inbox_rejects_incomplete_source_context_lineage() -> None:
    payload = load_payload()
    payload["source_context"]["source_kind"] = "maintenance_replay_overlay"
    payload["source_context"]["lineage"] = {
        "simulation_session_id": "simulation-session-1",
        "overlay_branch_id": "overlay-branch-1",
        "history_segment_id": "history-segment-1",
        "maintenance_event_id": "maintenance-event-1",
        "maintenance_action_id": "maintenance-action-1",
        "state_version": 1,
    }
    payload["source_context"]["lineage"]["maintenance_event_id"] = None

    receipt = receive(make_service(), payload)

    assert receipt.validation_status == "rejected"
    assert receipt.received_results == 0
    assert "schema_invalid" in (receipt.rejection_reason or "")
    assert "maintenance_event_id" in (receipt.rejection_reason or "")


def test_prediction_inbox_example_passes_schema_pydantic_receipt_roundtrip() -> None:
    payload = load_payload()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    assert list(validator.iter_errors(payload)) == []
    receipt = receive(make_service(), payload)

    assert receipt.validation_status == "accepted"
    assert receipt.received_results == len(payload["results"])


def test_prediction_inbox_preserves_generator_source_context_and_model_set() -> None:
    repository = FakeInboxRepository()
    payload = load_payload()

    receipt = receive(make_service(repository), payload)

    assert receipt.validation_status == "accepted"
    stored_payload = repository.saved[0]["raw_payload"]
    assert stored_payload["source_context"] == payload["source_context"]
    assert stored_payload["model_set"] == payload["model_set"]
    assert stored_payload["results"][0]["label_schema_sha256"] == (
        payload["results"][0]["label_schema_sha256"]
    )


def test_prediction_inbox_records_schema_invalid_payload() -> None:
    payload = load_payload()
    payload.pop("results")

    receipt = receive(make_service(), payload)

    assert receipt.validation_status == "rejected"
    assert receipt.received_results == 0
    assert "schema_invalid" in (receipt.rejection_reason or "")


def test_prediction_inbox_rejects_asset_outside_workspace() -> None:
    payload = load_payload()
    payload["results"][0]["asset_id"] = "CNC-404"
    payload["results"][0]["payload_sha256"] = (
        PredictiveMaintenanceRuntimeService._prediction_item_sha256(payload["results"][0])
    )

    receipt = receive(make_service(), payload)

    assert receipt.validation_status == "rejected"
    assert "scope_invalid" in (receipt.rejection_reason or "")


def test_prediction_inbox_routes_return_receipt(monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_RESULT_INGEST_TOKEN", "receiver-secret")
    repository = FakeInboxRepository()
    service = make_service(repository)
    app = FastAPI()
    app.include_router(router)
    app.include_router(internal_router)
    app.dependency_overrides[current_principal] = principal
    app.dependency_overrides[get_identity_service] = lambda: FakeIdentity()
    app.dependency_overrides[require_csrf] = lambda: None
    from app.diagnosis.runtime_router import get_predictive_maintenance_runtime_service

    app.dependency_overrides[get_predictive_maintenance_runtime_service] = lambda: service

    with TestClient(app) as client:
        public = client.post(
            "/api/projects/manufacturing-demo-project/workspaces/manufacturing-demo/"
            "predictive-maintenance/prediction-result-batches",
            json=load_payload(),
            headers={"X-CSRF-Token": "test"},
        )
        promotion = client.post(
            "/api/projects/manufacturing-demo-project/workspaces/manufacturing-demo/"
            "predictive-maintenance/prediction-result-batches/"
            "batch-20260827-cnc-001/promote",
            headers={"X-CSRF-Token": "test"},
        )
        internal = client.post(
            "/internal/prediction-results?project_id=manufacturing-demo-project"
            "&workspace_id=manufacturing-demo",
            json=load_payload(),
            headers={"Authorization": "Bearer receiver-secret"},
        )

    assert public.status_code == 202, public.text
    assert public.json()["product_result_created"] is False
    assert promotion.status_code == 200, promotion.text
    assert promotion.json()["product_result_created"] is True
    assert promotion.json()["promoted_results"] == 1
    assert internal.status_code == 200, internal.text
    assert internal.json()["validation_status"] == "duplicate"


def test_internal_prediction_inbox_promotes_accepted_batch(monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_RESULT_INGEST_TOKEN", "receiver-secret")
    service = make_service(FakeInboxRepository())
    app = FastAPI()
    app.include_router(internal_router)
    app.dependency_overrides[get_identity_service] = lambda: FakeIdentity()
    from app.diagnosis.runtime_router import get_predictive_maintenance_runtime_service

    app.dependency_overrides[get_predictive_maintenance_runtime_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/internal/prediction-results?project_id=manufacturing-demo-project"
            "&workspace_id=manufacturing-demo",
            json=load_payload(),
            headers={"Authorization": "Bearer receiver-secret"},
        )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["validation_status"] == "accepted"
    assert body["promotion_status"] == "promoted"
    assert body["product_result_created"] is True
    assert body["promoted_results"] == 1
    assert body["artifact_ids"]


def test_internal_prediction_inbox_duplicate_retries_unfinished_promotion(monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_RESULT_INGEST_TOKEN", "receiver-secret")
    repository = FakeInboxRepository(fail_promotions_once=True)
    service = make_service(repository)
    app = FastAPI()
    app.include_router(internal_router)
    app.dependency_overrides[get_identity_service] = lambda: FakeIdentity()
    from app.diagnosis.runtime_router import get_predictive_maintenance_runtime_service

    app.dependency_overrides[get_predictive_maintenance_runtime_service] = lambda: service
    payload = load_payload()

    with TestClient(app, raise_server_exceptions=False) as client:
        failed = client.post(
            "/internal/prediction-results?project_id=manufacturing-demo-project"
            "&workspace_id=manufacturing-demo",
            json=payload,
            headers={"Authorization": "Bearer receiver-secret"},
        )
        retried = client.post(
            "/internal/prediction-results?project_id=manufacturing-demo-project"
            "&workspace_id=manufacturing-demo",
            json=payload,
            headers={"Authorization": "Bearer receiver-secret"},
        )

    assert failed.status_code == 500
    assert retried.status_code == 200, retried.text
    body = retried.json()
    assert body["validation_status"] == "duplicate"
    assert body["promotion_status"] == "promoted"
    assert body["product_result_created"] is True
    assert body["promoted_results"] == 1
    assert repository.promotions


def test_prediction_inbox_internal_route_requires_configured_service_token(monkeypatch) -> None:
    monkeypatch.setenv("PREDICTION_RESULT_INGEST_TOKEN", "receiver-secret")
    service = make_service()
    app = FastAPI()
    add_auth_error_handler(app)
    app.include_router(internal_router)
    app.dependency_overrides[get_identity_service] = lambda: FakeIdentity()
    from app.diagnosis.runtime_router import get_predictive_maintenance_runtime_service

    app.dependency_overrides[get_predictive_maintenance_runtime_service] = lambda: service

    with TestClient(app) as client:
        response = client.post(
            "/internal/prediction-results?project_id=manufacturing-demo-project"
            "&workspace_id=manufacturing-demo",
            json=load_payload(),
            headers={"Authorization": "Bearer wrong-secret"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Prediction Result service token is invalid."


def test_generator_delivery_service_reaches_backend_internal_route(monkeypatch) -> None:
    from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
        PredictionDeliveryService,
    )

    class PayloadAdapter:
        batch_id = "batch-delivery-integration"

        def __init__(self) -> None:
            self.payload = load_payload()
            self.payload["batch_id"] = self.batch_id

        def model_dump_json(self) -> str:
            return json.dumps(self.payload)

        def model_dump(self, mode: str = "json") -> dict[str, Any]:
            return copy.deepcopy(self.payload)

    monkeypatch.setenv("PREDICTION_RESULT_INGEST_TOKEN", "receiver-secret")
    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_TOKEN", "receiver-secret")
    repository = FakeInboxRepository()
    service = make_service(repository)
    app = FastAPI()
    app.include_router(internal_router)
    app.dependency_overrides[get_identity_service] = lambda: FakeIdentity()
    from app.diagnosis.runtime_router import get_predictive_maintenance_runtime_service

    app.dependency_overrides[get_predictive_maintenance_runtime_service] = lambda: service

    class MockResponse:
        def __init__(self, response) -> None:
            self.response = response

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def getcode(self) -> int:
            return self.response.status_code

        def read(self) -> bytes:
            return self.response.content

    with TestClient(app) as client:
        def mock_urlopen(req, timeout=10.0):
            parsed = urllib.parse.urlsplit(req.full_url)
            path = urllib.parse.urlunsplit(("", "", parsed.path, parsed.query, ""))
            response = client.post(
                path,
                content=req.data,
                headers=dict(req.headers),
            )
            return MockResponse(response)

        monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
        delivery = PredictionDeliveryService(
            endpoint_url="http://testserver/internal/prediction-results"
        )
        result = delivery.send_once(PayloadAdapter())

    assert result["delivered"] is True
    assert result["status_code"] == 202
    assert repository.saved[0]["validation_status"] == "accepted"

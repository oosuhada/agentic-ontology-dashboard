from __future__ import annotations

import hashlib
import json
import uuid
from functools import lru_cache
from typing import Any

from app.common.runtime_settings import project_root

from .diagnosis_schema import (
    DataQuality,
    EvidenceSource,
    PredictionEvidence,
    PredictionModel,
    PredictionResult,
    PredictionSubject,
    PredictionValue,
    RecommendedAction,
)
from .evidence import validate_product_result_artifact
from .evidence_projection import product_result_artifact_to_event_evidence_projection
from .recommendation_policy import resolve_status_criticality_action
from .runtime_schema import PredictionResultBatch, PredictionResultBatchItem, StrictModel


V3_1_RESULT_SCHEMA = "result-artifact-v1.0"
PREDICTION_TASK = "binary_failure_within_horizon"
GENERATED_BY = "systems.backend.diagnosis.generator_batch_promotion"


def _top_factors_from_generator_explanation(
    item: PredictionResultBatchItem,
) -> list[dict[str, Any]] | None:
    explanation = item.explanation
    if explanation is None or not explanation.top_factors:
        return None
    factors = []
    for rank, factor in enumerate(explanation.top_factors[:5], start=1):
        field_id = (
            factor.evidence_field_id
            or f"generator_explanation.{rank}.{factor.feature}"
        )
        source_ref = None
        if factor.source_ref is not None:
            source_ref = factor.source_ref.model_dump(mode="json")
        factors.append(
            {
                "rank": rank,
                "feature": factor.feature,
                "feature_value": factor.feature_value,
                "signed_contribution": factor.signed_contribution,
                "direction": factor.direction,
                "explanation_method": factor.explanation_method,
                "display_name": factor.display_name or factor.feature,
                "evidence_field_id": field_id,
                **({"source_ref": source_ref} if source_ref is not None else {}),
            }
        )
    return factors


def _ranked_factor_evidence_from_top_factors(
    top_factors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    total = (
        sum(abs(float(factor.get("signed_contribution") or 0.0)) for factor in top_factors)
        or 1.0
    )
    rows = []
    for rank, factor in enumerate(top_factors[:5], start=1):
        field_id = str(
            factor.get("evidence_field_id")
            or f"generator_explanation.{rank}.{factor.get('feature') or 'unknown'}"
        )
        signed = float(factor.get("signed_contribution") or 0.0)
        rows.append(
            {
                "evidence_field_id": field_id,
                "feature": str(factor.get("feature") or ""),
                "display_name": str(
                    factor.get("display_name") or factor.get("feature") or ""
                ),
                "value": factor.get("feature_value"),
                "unit": "",
                "normal_range": "model explanation value",
                "direction": str(factor.get("direction") or "risk_up"),
                "contribution": round(abs(signed) / total, 6),
                "source_type": "generator_prediction_explanation",
            }
        )
    return rows


class ProductResultMaterializationCommand(StrictModel):
    """Inputs required to materialize one accepted Generator prediction item."""

    organization_id: str
    project_id: str
    workspace_id: str
    dataset_version_id: str
    asset: dict[str, Any]
    batch: PredictionResultBatch
    item: PredictionResultBatchItem


class ProductResultMaterializationResult(StrictModel):
    """One validated Product Result plus sibling read projections."""

    event_id: str
    artifact: dict[str, Any]
    prediction_result: PredictionResult
    prediction_result_id: str
    artifact_id: str
    source_sha256: str
    evidence_projection: dict[str, Any]
    materialized: bool = True
    replayed: bool = False


class ProductResultMaterializationService:
    """Materialize read-side Product Result artifacts from validated inbox data."""

    def materialize(
        self,
        command: ProductResultMaterializationCommand,
    ) -> ProductResultMaterializationResult:
        artifact = self._product_artifact_from_prediction_item(
            organization_id=command.organization_id,
            project_id=command.project_id,
            workspace_id=command.workspace_id,
            dataset_version_id=command.dataset_version_id,
            asset=command.asset,
            batch=command.batch,
            item=command.item,
        )
        prediction_result = self._prediction_result_from_artifact(
            organization_id=command.organization_id,
            project_id=command.project_id,
            workspace_id=command.workspace_id,
            batch=command.batch,
            item=command.item,
            artifact=artifact,
        )
        evidence_projection = product_result_artifact_to_event_evidence_projection(artifact)
        return ProductResultMaterializationResult(
            event_id=command.item.event_id,
            artifact=artifact,
            prediction_result=prediction_result,
            prediction_result_id=str(artifact["provenance"]["prediction_id"]),
            artifact_id=str(artifact["artifact_id"]),
            source_sha256=self._record_sha256(artifact),
            evidence_projection=evidence_projection,
        )

    @staticmethod
    @lru_cache(maxsize=1)
    def _threshold_policy() -> dict[str, Any]:
        path = project_root() / "systems" / "backend" / "app" / "diagnosis" / "threshold_policy.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @classmethod
    def _generator_model_snapshot(
        cls,
        batch: PredictionResultBatch,
        item: PredictionResultBatchItem,
    ) -> Any | None:
        for model in batch.model_set.models:
            if model.model_id == item.model_id and model.model_version == item.model_version:
                return model
        return None

    @classmethod
    def _generator_policy_decision(
        cls,
        *,
        score: float,
        selected_threshold: float | None,
        criticality: str | None,
    ) -> dict[str, float | str | None]:
        policy = cls._threshold_policy()
        fallback_threshold = float(policy["decision_threshold"])
        threshold = float(selected_threshold if selected_threshold is not None else fallback_threshold)
        adjustments = policy.get("criticality_adjustments", {})
        adjustment = float(adjustments.get(str(criticality), 0.0)) if criticality else 0.0
        rules = policy["severity_rules"]
        attention = min(float(rules["attention"]) + adjustment, threshold)
        warning = float(rules["warning"]) + adjustment
        critical = float(rules["critical"])
        if score >= critical:
            status = "critical"
        elif score >= warning:
            status = "warning"
        elif score >= attention:
            status = "attention"
        else:
            status = "normal"
        return {
            "status": status,
            "selected_threshold": threshold,
            "attention_threshold": attention,
            "warning_threshold": warning,
            "critical_threshold": critical,
            "criticality_adjustment": adjustment,
        }

    @classmethod
    def _promotion_action(cls, status: str, criticality: str | None) -> dict[str, str]:
        resolved = resolve_status_criticality_action(status, criticality)
        if resolved is not None:
            action_key, label, kind = resolved
        else:
            action_key = str(cls._threshold_policy()["decision_mapping"][status])
            label = action_key
            kind = "backend_threshold_policy"
        priority = {
            "critical": "urgent",
            "warning": "high",
            "attention": "medium",
            "normal": "normal",
        }[status]
        return {"action": action_key, "label": label, "kind": kind, "priority": priority}

    @staticmethod
    def _confidence_for_generator_score(score: float, threshold: float) -> float:
        return round(max(0.01, min(0.99, abs(score - threshold) * 2.0)), 6)

    @staticmethod
    def _record_sha256(record: dict[str, Any]) -> str:
        rendered = json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(rendered).hexdigest()

    @classmethod
    def _product_artifact_from_prediction_item(
        cls,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_version_id: str,
        asset: dict[str, Any],
        batch: PredictionResultBatch,
        item: PredictionResultBatchItem,
    ) -> dict[str, Any]:
        _ = (organization_id, project_id, workspace_id, dataset_version_id)
        score = float(item.score)
        model_snapshot = cls._generator_model_snapshot(batch, item)
        selected_threshold = (
            float(model_snapshot.selected_threshold)
            if model_snapshot is not None and model_snapshot.selected_threshold is not None
            else None
        )
        criticality = (
            str(asset.get("criticality"))
            if asset.get("criticality") in {"low", "medium", "high"}
            else None
        )
        policy_decision = cls._generator_policy_decision(
            score=score,
            selected_threshold=selected_threshold,
            criticality=criticality,
        )
        threshold = float(policy_decision["selected_threshold"])
        status = str(policy_decision["status"])
        predicted_type = (
            "failure_risk" if score >= threshold else "no_significant_risk"
        )
        prediction_id = f"GEN-{uuid.uuid5(uuid.NAMESPACE_URL, f'{batch.batch_id}:{item.event_id}')}"
        artifact_id = f"RESULT#{prediction_id}"
        action = cls._promotion_action(status, criticality)
        confidence = cls._confidence_for_generator_score(score, threshold)
        source_reference = (
            f"prediction-result-batch:{batch.batch_id}:event:{item.event_id}:"
            f"sha256:{item.payload_sha256}"
        )
        top_factors = _top_factors_from_generator_explanation(item)
        if top_factors is None:
            top_factors = [
                {
                    "rank": 1,
                    "feature": "generator_failure_score",
                    "feature_value": score,
                    "signed_contribution": round(score - threshold, 6),
                    "direction": "risk_up" if score >= threshold else "risk_down",
                    "explanation_method": "generator_prediction_score",
                },
                {
                    "rank": 2,
                    "feature": "model_selected_threshold",
                    "feature_value": threshold,
                    "signed_contribution": 0.0,
                    "direction": "risk_down",
                    "explanation_method": "model_artifact_training_config",
                },
                {
                    "rank": 3,
                    "feature": "asset_criticality_adjustment",
                    "feature_value": policy_decision["criticality_adjustment"],
                    "signed_contribution": policy_decision["criticality_adjustment"],
                    "direction": "risk_up" if float(policy_decision["criticality_adjustment"]) < 0 else "risk_down",
                    "explanation_method": "backend_threshold_policy",
                },
                {
                    "rank": 4,
                    "feature": "generator_model_artifact_manifest",
                    "feature_value": 1.0,
                    "signed_contribution": 0.0,
                    "direction": "risk_up",
                    "explanation_method": "lineage_presence_check",
                },
            ]
        ranked_factor_evidence = _ranked_factor_evidence_from_top_factors(top_factors)
        if not ranked_factor_evidence:
            ranked_factor_evidence = [
                {
                    "evidence_field_id": f"prediction_batch.{name}",
                    "feature": name,
                    "display_name": label,
                    "value": value,
                    "unit": unit,
                    "normal_range": normal_range,
                    "direction": direction,
                    "contribution": contribution,
                    "source_type": "generator_prediction_result_batch",
                }
                for name, label, value, unit, normal_range, direction, contribution in (
                    (
                        "generator_failure_score",
                        "Generator failure score",
                        score,
                        "probability",
                        f"< {threshold}",
                        "risk_up" if score >= threshold else "risk_down",
                        abs(score - threshold),
                    ),
                    (
                        "model_selected_threshold",
                        "Model selected threshold",
                        threshold,
                        "probability",
                        "model artifact value",
                        "risk_down",
                        0.0,
                    ),
                    (
                        "asset_criticality_adjustment",
                        "Asset criticality adjustment",
                        policy_decision["criticality_adjustment"],
                        "probability",
                        "policy value",
                        "risk_up" if float(policy_decision["criticality_adjustment"]) < 0 else "risk_down",
                        abs(float(policy_decision["criticality_adjustment"])),
                    ),
                    (
                        "generator_model_artifact_manifest",
                        "Generator model artifact manifest",
                        1.0,
                        "present",
                        "required",
                        "risk_up",
                        0.0,
                    ),
                )
            ]
        source_fields = [
            {
                "field_id": "prediction_batch.score",
                "source_path": f"results[event_id={item.event_id}].score",
                "label": "Generator failure score",
                "description": "Raw prediction score emitted by Generator and consumed by Backend policy.",
            },
            {
                "field_id": "prediction_batch.payload_sha256",
                "source_path": f"results[event_id={item.event_id}].payload_sha256",
                "label": "Prediction payload checksum",
                "description": "Canonical checksum of the raw Generator prediction item.",
            },
            {
                "field_id": "prediction_batch.model_artifact_manifest_sha256",
                "source_path": f"results[event_id={item.event_id}].model_artifact_manifest_sha256",
                "label": "Model artifact manifest checksum",
                "description": "Generator model artifact lineage checksum used for this prediction.",
            },
            {
                "field_id": "model_artifact.selected_threshold",
                "source_path": f"model_set.models[model_id={item.model_id},model_version={item.model_version}].selected_threshold",
                "label": "Model selected threshold",
                "description": "Model Artifact training_config.selected_threshold captured in the Generator batch snapshot.",
            },
            {
                "field_id": "asset.criticality",
                "source_path": f"pm_assets[asset_id={item.asset_id}].criticality",
                "label": "Asset criticality",
                "description": "Asset criticality used for Backend severity-boundary adjustment when available.",
            }
        ]
        if item.explanation is not None and item.explanation.top_factors:
            source_fields.extend(
                [
                    {
                        "field_id": str(
                            factor.get("evidence_field_id")
                            or f"generator_explanation.{factor['rank']}.{factor['feature']}"
                        ),
                        "source_path": f"results[event_id={item.event_id}].explanation.top_factors[{factor['rank'] - 1}]",
                        "label": str(factor.get("display_name") or factor["feature"]),
                        "description": "Generator model explanation absorbed into Backend Product Result after batch validation.",
                    }
                    for factor in top_factors
                ]
            )
        source_fields.append(
            {
                "field_id": "backend_policy.severity_rules",
                "source_path": "systems/backend/app/diagnosis/threshold_policy.json",
                "label": "Backend severity policy",
                "description": "Backend-owned severity and criticality adjustment policy applied during Product Result promotion.",
            }
        )
        evidence_gaps = [
            {
                "gap_id": "generator-batch-sensor-window-unavailable",
                "field": "evidence_payload.sensor_evidence",
                "reason": "missing_source",
                "required_source": "observation window and feature attribution payload",
                "owner_domain": "diagnosis",
                "display_policy": "show_limitation",
            },
            {
                "gap_id": "generator-batch-component-hypotheses-unavailable",
                "field": "evidence_payload.component_hypotheses",
                "reason": "insufficient_context",
                "required_source": "component attribution or inspection-target mapping",
                "owner_domain": "diagnosis",
                "display_policy": "show_limitation",
            },
            {
                "gap_id": "generator-batch-maintenance-context-unavailable",
                "field": "evidence_payload.maintenance_context",
                "reason": "missing_source",
                "required_source": "maintenance context provider",
                "owner_domain": "maintenance",
                "display_policy": "show_limitation",
            },
        ]
        if selected_threshold is None:
            evidence_gaps.append(
                {
                    "gap_id": "generator-batch-selected-threshold-unavailable",
                    "field": "model_artifact.selected_threshold",
                    "reason": "missing_source",
                    "required_source": "Model Artifact training_config.selected_threshold in model_set snapshot",
                    "owner_domain": "generator",
                    "display_policy": "show_limitation",
                }
            )
        if criticality is None:
            evidence_gaps.append(
                {
                    "gap_id": "generator-batch-asset-criticality-unavailable",
                    "field": "asset.criticality",
                    "reason": "missing_source",
                    "required_source": "asset criticality from Backend asset context",
                    "owner_domain": "operations",
                    "display_policy": "show_limitation",
                }
            )
        evidence_payload = {
            "sensor_evidence": {"window_rows": 0, "sensors": {}},
            "component_hypotheses": [],
            "status_flags": {
                "multiple_risk_factors": False,
                "insufficient_data": False,
            },
            "recommended_actions": [
                {
                    "action_id": action["action"],
                    "label": action["label"],
                    "kind": action["kind"],
                    "requires_human_approval": True,
                    "basis": [
                        "prediction_batch.score",
                        "model_artifact.selected_threshold",
                        "asset.criticality",
                        "backend_policy.severity_rules",
                    ],
                }
            ],
            "source_fields": source_fields,
            "evidence_gaps": evidence_gaps,
        }
        artifact = {
            "artifact_id": artifact_id,
            "artifact_type": "predictive_maintenance_result",
            "schema_version": V3_1_RESULT_SCHEMA,
            "asset_id": item.asset_id,
            "asset_type": str(asset["asset_type"]),
            "observed_at": item.observed_at.isoformat(),
            "generated_at": batch.emitted_at.isoformat(),
            "threshold": threshold,
            "prediction_horizon_hours": 24,
            "prediction_task": PREDICTION_TASK,
            "failure_probability": score,
            "predicted_failure_type": predicted_type,
            "status_grade": status,
            "confidence": confidence,
            "confidence_label": (
                "high" if confidence >= 0.7 else "medium" if confidence >= 0.4 else "low"
            ),
            "top_factors": top_factors,
            "ranked_factor_evidence": ranked_factor_evidence,
            "recommended_action": action,
            "data_quality_warnings": [],
            "observation": {},
            "history": [],
            "detected_interval": {
                "start": item.observed_at.isoformat(),
                "end": item.observed_at.isoformat(),
            },
            "policy_version": str(cls._threshold_policy()["policy_version"]),
            "model_mode": "generator_prediction_batch",
            "lineage": {
                "batch_id": batch.batch_id,
                "event_id": item.event_id,
                "source_context": batch.source_context.model_dump(mode="json"),
                "item_lineage": item.lineage.model_dump(mode="json"),
            },
            "evidence_payload": evidence_payload,
            "provenance": {
                "dataset_version": batch.source_context.dataset_version,
                "model_version": item.model_version,
                "prediction_id": prediction_id,
                "source_type": "product_runtime_inference",
                "canonical_source_mutated": False,
                "model_artifact": {
                    "model_id": item.model_id,
                    "model_version": item.model_version,
                    "model_artifact_manifest_sha256": item.model_artifact_manifest_sha256,
                    "selected_threshold": selected_threshold,
                    "feature_schema_version": item.feature_schema_version,
                    "history_requirement_version": item.history_requirement_version,
                    "label_schema_version": item.label_schema_version,
                    "feature_schema_sha256": item.feature_schema_sha256,
                    "history_requirement_sha256": item.history_requirement_sha256,
                    "label_schema_sha256": item.label_schema_sha256,
                },
                "evidence_payload_reference": {
                    "source": "product_result_artifact",
                    "reference": artifact_id,
                    "generated_by": GENERATED_BY,
                },
                "source_reference": source_reference,
            },
        }
        validate_product_result_artifact(artifact)
        return artifact

    @staticmethod
    def _prediction_result_from_artifact(
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        batch: PredictionResultBatch,
        item: PredictionResultBatchItem,
        artifact: dict[str, Any],
    ) -> PredictionResult:
        return PredictionResult(
            prediction_id=artifact["provenance"]["prediction_id"],
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            source_run_id=artifact["artifact_id"],
            subject=PredictionSubject(
                object_type="equipment",
                object_id=item.asset_id,
                observed_at=item.observed_at,
            ),
            prediction=PredictionValue(
                task="classification",
                status=artifact["status_grade"],
                label=artifact["predicted_failure_type"],
                score=artifact["failure_probability"],
                confidence=artifact["confidence"],
                horizon="24h",
                value=artifact["predicted_failure_type"],
            ),
            evidence=[
                PredictionEvidence(
                    evidence_id=f"artifact:{artifact['artifact_id']}",
                    kind="artifact",
                    label="Generator Prediction Result Batch",
                    value={
                        "source_contract": "prediction-result-batch-v1",
                        "batch_id": batch.batch_id,
                        "event_id": item.event_id,
                        "backend_policy_version": artifact["policy_version"],
                    },
                    source=EvidenceSource(
                        system="systems.generator",
                        reference=artifact["provenance"]["source_reference"],
                        checksum=item.payload_sha256,
                    ),
                )
            ],
            recommended_actions=[
                RecommendedAction(
                    action_type=artifact["recommended_action"]["action"],
                    label=artifact["recommended_action"]["action"],
                    reason="Backend threshold policy applied to Generator prediction score; approval and execution have not occurred.",
                    requires_approval=True,
                    parameters={
                        "priority": artifact["recommended_action"]["priority"],
                        "semantic_type": "policy_recommendation",
                        "execution_state": "not_executed",
                        "creates_work_order_automatically": False,
                    },
                )
            ],
            model=PredictionModel(
                provider="systems.generator",
                model_name=item.model_id,
                model_version=item.model_version,
                dataset_version=batch.source_context.dataset_version,
                policy_version=artifact["policy_version"],
            ),
            data_quality=DataQuality(status="pass", issues=[]),
            created_at=batch.emitted_at,
        )

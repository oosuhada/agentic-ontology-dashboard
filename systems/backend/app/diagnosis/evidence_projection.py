"""Artifact-derived Event Evidence projection helpers.

This module belongs to the dashboard projection layer. It consumes Product
Result Artifacts produced by ``systems/backend/app/diagnosis`` and derives
dashboard/report-facing evidence without becoming the runtime producer.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

HIDDEN_KEYS = {"evaluation_truth", "hidden_truth"}
EVENT_EVIDENCE_SCHEMA_VERSION = "event-evidence-projection-v1"
EVENT_EVIDENCE_CONTRACT_TYPE = "event_evidence_projection"
OPERATIONAL_DECISION_KINDS = {
    "continue_monitoring",
    "request_inspection",
    "review_shutdown",
    "hold_for_data_check",
}

DECISION_BY_ACTION = {
    "continue_monitoring": "continue_monitoring",
    "request_inspection": "request_inspection",
    "inspect_within_current_shift": "request_inspection",
    "immediate_inspection_and_stop_review": "review_shutdown",
    "hold_for_data_check": "hold_for_data_check",
}


def evidence_snapshot_basis_from_artifact(
    artifact: dict[str, Any],
    *,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Return the shared basis that sibling read projections can compare."""

    provenance = artifact.get("provenance") or {}
    lineage = artifact.get("lineage") or {}
    evidence_reference = provenance.get("evidence_payload_reference")
    if isinstance(evidence_reference, dict):
        evidence_reference = evidence_reference.get("reference")
    return {
        "artifact_id": artifact.get("artifact_id"),
        "evidence_payload_reference": str(evidence_reference or ""),
        "asset_id": artifact.get("asset_id"),
        "event_id": event_id or artifact.get("event_id"),
        "observed_at": artifact.get("observed_at"),
        "model_version": provenance.get("model_version"),
        "dataset_version": provenance.get("dataset_version"),
        "source_sha256": (
            artifact.get("source_sha256")
            or provenance.get("source_sha256")
            or lineage.get("source_sha256")
        ),
    }


def product_result_artifact_to_event_evidence_projection(artifact: dict[str, Any]) -> dict[str, Any]:
    """Derive canonical Event Evidence projection from a producer-enriched artifact."""

    clean_artifact = _strip_hidden(artifact)
    _ensure_unmutated_source(clean_artifact)
    payload = clean_artifact.get("evidence_payload")
    if not isinstance(payload, dict):
        raise ValueError("Product Result Artifact evidence_payload is required for Event Evidence projection")
    provenance = clean_artifact.get("provenance", {})
    event_id = f"EVT-{clean_artifact['artifact_id']}"
    threshold = clean_artifact.get("threshold")
    recommended_decision = _recommended_decision(clean_artifact)
    operational_decision_kind = _operational_decision_kind(payload)
    projection = {
        "schema_version": EVENT_EVIDENCE_SCHEMA_VERSION,
        "contract_type": EVENT_EVIDENCE_CONTRACT_TYPE,
        "event_id": event_id,
        "evidence_id": f"EVD-{event_id}",
        "scenario_id": None,
        "subject": _subject(clean_artifact),
        "artifact_reference": {
            "event_id": event_id,
            "artifact_id": clean_artifact.get("artifact_id"),
            "artifact_type": clean_artifact.get("artifact_type"),
            "artifact_schema_version": clean_artifact.get("schema_version"),
            "asset_id": clean_artifact.get("asset_id"),
            "asset_type": clean_artifact.get("asset_type"),
            "observed_at": clean_artifact.get("observed_at"),
            "prediction_id": provenance.get("prediction_id"),
            "top_factor_count": len(clean_artifact.get("top_factors", [])),
            "evidence_payload_reference": provenance.get("evidence_payload_reference"),
        },
        "assessment": {
            "status": clean_artifact.get("status_grade"),
            "recommended_decision": recommended_decision,
            "operational_decision_kind": operational_decision_kind,
            "confidence": _confidence_label(clean_artifact.get("confidence_label") or clean_artifact.get("confidence")),
            "confidence_value": clean_artifact.get("confidence"),
            "failure_probability": clean_artifact.get("failure_probability"),
            "threshold": threshold,
            "predicted_failure_type": clean_artifact.get("predicted_failure_type"),
            "top_factors": clean_artifact.get("top_factors", []),
            "data_quality_warnings": clean_artifact.get("data_quality_warnings", []),
        },
        "report_projection": {
            "display_labels": {
                "status_label": _status_label(clean_artifact.get("status_grade")),
                "confidence_label": _confidence_label(clean_artifact.get("confidence_label") or clean_artifact.get("confidence")),
                "probability_label": _probability_label(clean_artifact.get("failure_probability")),
            },
            "sensor_cards": _sensor_cards(payload.get("sensor_evidence", {})),
            "inspection_targets": payload.get("component_hypotheses", []),
            "recommended_actions": payload.get("recommended_actions", []),
            "evidence_trace": payload.get("source_fields", []),
            "maintenance_context": payload.get("maintenance_context", {}),
            "status_flags": payload.get("status_flags", {}),
        },
        "provenance": {
            "dataset_version": provenance.get("dataset_version"),
            "model_version": provenance.get("model_version"),
            "prediction_id": provenance.get("prediction_id"),
            "source_type": provenance.get("source_type"),
            "model_artifact": provenance.get("model_artifact"),
            "lineage": {
                **(clean_artifact.get("lineage", {}) or {}),
                "observation": clean_artifact.get("observation", {}),
                "history": clean_artifact.get("history", []),
                "detected_interval": clean_artifact.get("detected_interval"),
                "policy_version": clean_artifact.get("policy_version"),
                "model_mode": clean_artifact.get("model_mode"),
            },
        },
        "limitations": _limitations(clean_artifact, payload),
        "generated_at": clean_artifact.get("generated_at") or clean_artifact.get("observed_at"),
    }
    return _strip_hidden(projection)


def event_evidence_projection_to_legacy_evidence(
    evidence: dict[str, Any],
    *,
    ranked_factor_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build legacy evidence-package-compatible shape from canonical projection."""

    projection = _strip_hidden(evidence)
    assessment = projection["assessment"]
    report_projection = projection["report_projection"]
    artifact_reference = projection["artifact_reference"]
    provenance = projection["provenance"]
    lineage = dict(provenance.get("lineage") or {})
    threshold = assessment.get("threshold")
    if threshold is None:
        raise ValueError("legacy evidence projection requires an explicit threshold")

    maintenance_context = report_projection.get("maintenance_context") or {}
    legacy_factor_source = ranked_factor_evidence or assessment.get("top_factors", [])
    top_factors = [_legacy_top_factor(factor) for factor in legacy_factor_source]
    if any(not isinstance(factor, dict) or "evidence_field_id" not in factor for factor in top_factors):
        raise ValueError("legacy evidence projection requires producer-normalized top_factors")

    legacy = {
        "schema_version": "1.0",
        "evidence_id": projection["evidence_id"],
        "event_id": projection["event_id"],
        "scenario_id": projection.get("scenario_id") or lineage.get("fixture_id") or "unknown",
        "equipment": projection.get("subject", {}),
        "model": {
            "model_version": provenance.get("model_version") or "unknown",
            "policy_version": lineage.get("policy_version") or "unknown",
            "mode": lineage.get("model_mode") or "deterministic_fallback",
            "artifact": provenance.get("model_artifact"),
        },
        "status": assessment.get("status"),
        "recommended_decision": assessment.get("recommended_decision"),
        "confidence": assessment.get("confidence"),
        "failure_probability": assessment.get("failure_probability"),
        "threshold": float(threshold),
        "predicted_failure_type": assessment.get("predicted_failure_type") or "uncertain",
        "observation": lineage.get("observation", {}),
        "history": lineage.get("history", []),
        "detected_interval": lineage.get("detected_interval")
        or {"start": artifact_reference.get("observed_at"), "end": artifact_reference.get("observed_at")},
        "top_factors": top_factors,
        "maintenance_context": maintenance_context,
        "data_quality_warnings": assessment.get("data_quality_warnings", []),
        "lineage": {
            "fixture_id": lineage.get("fixture_id") or projection.get("scenario_id") or "unknown",
            "fixture_schema_version": lineage.get("fixture_schema_version") or "derived",
            "sensor_source": lineage.get("sensor_source") or "artifact-derived projection",
            "context_source": lineage.get("context_source")
            or (
                f"{maintenance_context.get('provider')}:{maintenance_context.get('version')}"
                if maintenance_context.get("provider") and maintenance_context.get("version")
                else "unavailable"
            ),
            "product_result_artifact": artifact_reference,
        },
        "generated_at": projection.get("generated_at") or artifact_reference.get("observed_at"),
    }
    return _strip_hidden(legacy)


def _strip_hidden(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_hidden(item) for key, item in deepcopy(value).items() if key not in HIDDEN_KEYS}
    if isinstance(value, list):
        return [_strip_hidden(item) for item in value]
    return deepcopy(value)


def _legacy_top_factor(factor: Any) -> dict[str, Any]:
    if not isinstance(factor, dict) or "evidence_field_id" not in factor:
        return {}
    return {
        "evidence_field_id": factor.get("evidence_field_id"),
        "feature": factor.get("feature"),
        "display_name": factor.get("display_name") or factor.get("feature"),
        "value": factor.get("value") if factor.get("value") is not None else factor.get("feature_value"),
        "unit": factor.get("unit", ""),
        "normal_range": factor.get("normal_range", "근거 부족"),
        "direction": factor.get("direction"),
        "contribution": factor.get("contribution"),
        "source_type": factor.get("source_type", "observed"),
    }


def _ensure_unmutated_source(artifact: dict[str, Any]) -> None:
    provenance = artifact.get("provenance") or {}
    if provenance.get("canonical_source_mutated") is not False:
        raise ValueError("Product Result Artifact provenance.canonical_source_mutated must be false")


def _sensor_cards(sensor_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    cards = []
    for sensor_key, sensor in (sensor_evidence.get("sensors") or {}).items():
        cards.append(
            {
                "sensor_id": sensor_key,
                "label": sensor.get("display_name") or sensor_key,
                "current": sensor.get("current"),
                "window_mean": sensor.get("window_mean"),
                "unit": sensor.get("unit", ""),
                "z_score": sensor.get("z_score"),
                "basis": sensor.get("basis", {}),
                "source_field_id": f"sensor_evidence.sensors.{sensor_key}",
            }
        )
    return cards


def _recommended_decision(artifact: dict[str, Any]) -> str:
    action = (artifact.get("recommended_action") or {}).get("action")
    if action in DECISION_BY_ACTION:
        return DECISION_BY_ACTION[action]
    status = artifact.get("status_grade")
    if status == "critical":
        return "review_shutdown"
    if status in {"warning", "attention"}:
        return "request_inspection"
    if status == "data_quality_hold":
        return "hold_for_data_check"
    return "continue_monitoring"


def _operational_decision_kind(payload: dict[str, Any]) -> str | None:
    """Return only the Diagnosis-owned machine decision projection.

    The legacy ``recommended_decision`` remains a display compatibility field.
    Maintenance must never derive authorization from that field, the root
    ``recommended_action``, status grade, or a producer recommendation kind.
    """

    actions = payload.get("recommended_actions") or []
    if not actions:
        return None
    if len(actions) != 1:
        raise ValueError(
            "Event Evidence Projection requires exactly one operational recommendation"
        )
    action = actions[0]
    if not isinstance(action, dict):
        raise ValueError("Event Evidence Projection recommendation must be an object")
    # ``action_id`` is the Diagnosis policy key. ``kind`` remains producer-owned
    # display/domain metadata and is deliberately not interpreted here.
    decision = action.get("action_id")
    if decision not in OPERATIONAL_DECISION_KINDS:
        # Historical/producer-owned action identifiers may still be useful as
        # report evidence, but they must never be promoted into an executable
        # operational decision. Treating them as unavailable is both safer and
        # keeps read projections usable for mixed-version runtime data.
        return None
    return str(decision)


def _confidence_label(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, str):
        return value if value in {"high", "medium", "low", "unavailable"} else "unavailable"
    numeric = float(value)
    if numeric >= 0.7:
        return "high"
    if numeric >= 0.4:
        return "medium"
    return "low"


def _status_label(value: Any) -> str:
    return {
        "normal": "정상",
        "attention": "주의",
        "warning": "경고",
        "critical": "긴급",
        "data_quality_hold": "데이터 확인 필요",
    }.get(str(value), str(value))


def _probability_label(value: Any) -> str:
    if value is None:
        return "근거 부족"
    return f"{float(value) * 100:.1f}%"


def _subject(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "equipment_id": artifact.get("asset_id"),
        "display_name": artifact.get("asset_id"),
        "asset_type": artifact.get("asset_type"),
    }


def _limitations(artifact: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    limitations = [
        "예측 결과는 고장 확정이 아니라 점검 우선순위 근거다.",
        "권장 조치는 자동 제어가 아니라 사람의 검토를 요구한다.",
    ]
    if artifact.get("data_quality_warnings"):
        limitations.append("데이터 품질 경고가 있어 해석에 제한이 있다.")
    if artifact.get("status_grade") == "data_quality_hold":
        limitations.append("센서 데이터 확인 전까지 위험 판단을 보류한다.")
    if payload.get("evidence_gaps"):
        limitations.append("일부 근거 필드는 evidence_gaps에 따라 산출 불가능 또는 보류 상태다.")
    return limitations

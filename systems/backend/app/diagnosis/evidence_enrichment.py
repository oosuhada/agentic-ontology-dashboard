from __future__ import annotations

import math
from typing import Any

from .contracts import DISPLAY_NAMES, UNITS
from .evidence_baseline import build_history_baseline_window, numeric_observation
from .predictor import FactorScore, Prediction
from .recommendation_policy import resolve_status_criticality_action

GENERATED_BY = "systems.backend.app.diagnosis.evidence_enrichment"

NORMAL_RANGES = {
    "air_temperature_k": "295.0–305.0",
    "process_temperature_k": "304.0–315.0",
    "rotational_speed_rpm": "1,400–2,200",
    "tool_wear_min": "0–180",
    "temperature_difference_k": "8.6–12.0",
    "mechanical_power_w": "3,500–9,000",
    "overstrain_index": "0–11,000",
    "torque_nm": "10–60",
}
_COMPONENT_BY_FEATURE = {
    "tool_wear_min": ("tooling", "공구/마모 계통"),
    "temperature_difference_k": ("thermal_path", "열 방산 계통"),
    "mechanical_power_w": ("drive_power", "동력 전달 계통"),
    "overstrain_index": ("drive_power", "동력 전달 계통"),
    "torque_nm": ("drive_power", "동력 전달 계통"),
    "rotational_speed_rpm": ("rotating_assembly", "회전 계통"),
    "rotation_raw": ("rotating_assembly", "회전/진동 계통"),
    "relative_vibration_z": ("vibration_path", "진동 계통"),
    "vibration_raw": ("vibration_path", "진동 계통"),
    "pressure_raw": ("air_supply", "압력/공압 계통"),
    "voltage_raw": ("electrical_supply", "전원 계통"),
}
# Status-only fallback used when equipment criticality is unavailable. When
# criticality IS available, _recommended_actions defers to
# recommendation_policy.resolve_status_criticality_action instead, so this
# table never becomes a second, diverging copy of the status x criticality
# rules owned by recommendation-policy-v1 (see recommendation_policy.json).
_ACTION_BY_STATUS = {
    "critical": ("review_shutdown", "정지 검토", "review_shutdown"),
    "warning": ("request_inspection", "점검 요청", "request_inspection"),
    "attention": ("request_inspection", "점검 요청", "request_inspection"),
    "normal": ("continue_monitoring", "모니터링 지속", "continue_monitoring"),
    "data_quality_hold": ("hold_for_data_check", "데이터 확인 후 판단", "hold_for_data_check"),
}
_UNIT_FALLBACKS = {
    "voltage_raw": "raw",
    "rotation_raw": "raw",
    "pressure_raw": "raw",
    "vibration_raw": "raw",
    "relative_vibration_z": "z",
}
_DISPLAY_FALLBACKS = {
    "voltage_raw": "전압 신호",
    "rotation_raw": "회전 신호",
    "pressure_raw": "압력 신호",
    "vibration_raw": "진동 신호",
    "relative_vibration_z": "상대 진동",
}


def build_product_result_evidence_payload(
    artifact: dict[str, Any],
    fixture: dict[str, Any],
    prediction: Prediction,
    *,
    maintenance_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build producer-owned evidence facts for Product Result Artifact enrichment."""

    enrich_product_result_top_factors(artifact, fixture)
    sensor_evidence = _sensor_evidence(fixture)
    source_fields = _factor_source_fields(artifact)
    source_fields.extend(_sensor_source_fields(sensor_evidence))
    component_hypotheses = _component_hypotheses(artifact, sensor_evidence)
    criticality = (fixture or {}).get("equipment", {}).get("criticality")
    recommended_actions, recommendation_gap = _recommended_actions(
        artifact,
        component_hypotheses,
        criticality=criticality,
        source_fields=source_fields,
    )
    evidence_gaps = _evidence_gaps(artifact, maintenance_context, prediction)
    if recommendation_gap is not None:
        evidence_gaps.append(recommendation_gap)

    payload: dict[str, Any] = {
        "sensor_evidence": sensor_evidence,
        "component_hypotheses": component_hypotheses,
        "status_flags": {
            "multiple_risk_factors": _has_multiple_risk_factors(artifact),
            "insufficient_data": bool(prediction.quality_issues),
        },
        "recommended_actions": recommended_actions,
        "source_fields": _dedupe_source_fields(source_fields),
        "evidence_gaps": evidence_gaps,
    }
    if maintenance_context is not None:
        payload["maintenance_context"] = maintenance_context
    return payload


def evidence_payload_reference(artifact: dict[str, Any]) -> dict[str, str]:
    return {
        "source": "product_result_artifact",
        "reference": str(artifact["artifact_id"]),
        "generated_by": GENERATED_BY,
    }


def validate_evidence_payload_invariants(payload: dict[str, Any]) -> None:
    recommended_actions = payload.get("recommended_actions", [])
    if len(recommended_actions) > 1:
        raise ValueError(
            "evidence_payload supports at most one operational recommendation"
        )
    source_field_ids = {field["field_id"] for field in payload.get("source_fields", [])}
    basis_refs: set[str] = set()
    for hypothesis in payload.get("component_hypotheses", []):
        basis_refs.update(hypothesis.get("basis", []))
    for action in recommended_actions:
        basis_refs.update(action.get("basis", []))
    unresolved = sorted(basis_refs - source_field_ids)
    if unresolved:
        raise ValueError(f"evidence_payload basis refs are not in source_fields: {unresolved}")

    if payload.get("maintenance_context") is None and not any(
        gap.get("field") == "evidence_payload.maintenance_context"
        and gap.get("owner_domain") == "maintenance"
        for gap in payload.get("evidence_gaps", [])
    ):
        raise ValueError("evidence_payload missing maintenance_context gap")

    has_factor_evidence = any(field_id.startswith("factor.") for field_id in source_field_ids)
    if not has_factor_evidence and not any(
        gap.get("field") == "top_factors"
        and gap.get("owner_domain") == "diagnosis"
        for gap in payload.get("evidence_gaps", [])
    ):
        raise ValueError("evidence_payload missing top_factors gap")


def build_ranked_factor_evidence(prediction: Prediction) -> list[dict[str, Any]]:
    scored = prediction.factors[:5]
    total_score = sum(item.score for item in scored) or 1.0
    return [_ranked_factor_evidence_row(index, item, total_score) for index, item in enumerate(scored, start=1)]


def enrich_product_result_top_factors(artifact: dict[str, Any], fixture: dict[str, Any] | None = None) -> None:
    factors = artifact.get("top_factors") or []
    total = sum(abs(float(factor.get("signed_contribution") or 0.0)) for factor in factors) or 1.0
    observed_features = set(numeric_observation((fixture or {}).get("observation") or {}))
    for index, factor in enumerate(factors, start=1):
        feature = str(factor.get("feature") or "unknown")
        signed = float(factor.get("signed_contribution") or 0.0)
        factor.setdefault("evidence_field_id", f"factor.{index}.{feature}")
        factor.setdefault("display_name", _display_name(feature))
        factor.setdefault("value", factor.get("feature_value"))
        factor.setdefault("unit", _unit(feature))
        factor.setdefault("normal_range", "근거 부족")
        factor.setdefault("direction", "risk_up" if signed >= 0 else "risk_down")
        factor.setdefault("contribution", round(abs(signed) / total, 6))
        factor.setdefault("source_type", "observed" if feature in observed_features else "derived")


def _ranked_factor_evidence_row(index: int, item: FactorScore, total_score: float) -> dict[str, Any]:
    feature = item.feature
    value = None
    if item.raw_value is not None:
        try:
            number = float(item.raw_value)
        except (TypeError, ValueError):
            value = None
        else:
            value = round(number, 4) if math.isfinite(number) else None
    return {
        "evidence_field_id": f"factor.{index}.{feature}",
        "feature": feature,
        "display_name": _display_name(feature),
        "value": value,
        "unit": _unit(feature),
        "normal_range": NORMAL_RANGES.get(feature, "근거 부족"),
        "direction": item.direction,
        "contribution": round(item.score / total_score, 6),
        "source_type": _source_type(feature),
    }


def _sensor_evidence(fixture: dict[str, Any]) -> dict[str, Any]:
    raw_observation = fixture.get("observation") or {}
    observation = numeric_observation(raw_observation)
    baseline_window = build_history_baseline_window(fixture)
    window_rows = [row for _, row in baseline_window.rows if row]
    sensors: dict[str, Any] = {}

    for feature, current in observation.items():
        stat = baseline_window.stat(feature, current)
        sensors[feature] = {
            "display_name": _display_name(feature),
            "unit": _unit(feature),
            "current": current,
            "window_mean": stat.mean,
            "z_score": stat.z_score,
            "basis": {
                "baseline_mean": stat.mean,
                "baseline_std": stat.std,
                "baseline_n": stat.n,
                "baseline_reference": "fixture.history",
            },
        }

    timestamps = baseline_window.display_timestamps
    return {
        "window": {"start": timestamps[0], "end": timestamps[-1]} if timestamps else {},
        "window_rows": len(window_rows),
        "sensors": sensors,
    }


def _component_hypotheses(artifact: dict[str, Any], sensor_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    hypotheses: dict[str, dict[str, Any]] = {}
    sensors = sensor_evidence.get("sensors") or {}
    for factor in artifact.get("top_factors", [])[:3]:
        feature = str(factor.get("feature") or "")
        component_id, component_label = _COMPONENT_BY_FEATURE.get(feature, ("diagnosis_factor", "진단 요인"))
        basis = [str(factor["evidence_field_id"])]
        sensor_ref = f"sensor_evidence.sensors.{feature}"
        if feature in sensors:
            basis.append(sensor_ref)
        if component_id not in hypotheses:
            hypotheses[component_id] = {
                "component_id": component_id,
                "component_label": component_label,
                "association": "inspection_candidate",
                "basis": [],
            }
        hypotheses[component_id]["basis"] = list(dict.fromkeys([*hypotheses[component_id]["basis"], *basis]))
    return list(hypotheses.values())


def _recommended_actions(
    artifact: dict[str, Any],
    hypotheses: list[dict[str, Any]],
    *,
    source_fields: list[dict[str, str]],
    criticality: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str] | None]:
    status = str(artifact.get("status_grade") or "attention")
    source_field_ids = {field["field_id"] for field in source_fields}
    if status == "data_quality_hold":
        action_id, label, kind = _ACTION_BY_STATUS["data_quality_hold"]
        return (
            [
                {
                    "action_id": action_id,
                    "label": label,
                    "kind": kind,
                    "requires_human_approval": True,
                    "basis": [],
                }
            ],
            None,
        )
    resolved = resolve_status_criticality_action(status, criticality)
    if resolved is not None:
        action_id, label, kind = resolved
    else:
        return [], _recommendation_gap("criticality_missing_or_unresolved")
    basis: list[str] = []
    for hypothesis in hypotheses[:2]:
        basis.extend(hypothesis.get("basis", []))
    if not basis:
        basis = [field["evidence_field_id"] for field in artifact.get("top_factors", [])[:1] if field.get("evidence_field_id")]
    unresolved_basis = sorted(set(basis) - source_field_ids)
    if not basis or unresolved_basis:
        return [], _recommendation_gap("basis_missing_or_unresolved")
    return [
        {
            "action_id": action_id,
            "label": label,
            "kind": kind,
            "requires_human_approval": True,
            "basis": list(dict.fromkeys(basis)),
        }
    ], None


def _recommendation_gap(reason: str) -> dict[str, str]:
    return {
        "gap_id": "gap.recommended_actions.unavailable",
        "field": "evidence_payload.recommended_actions",
        "reason": reason,
        "required_source": "recommendation_policy_input",
        "owner_domain": "diagnosis",
        "display_policy": "show_limitation",
    }


def _factor_source_fields(artifact: dict[str, Any]) -> list[dict[str, str]]:
    fields = []
    for index, factor in enumerate(artifact.get("top_factors", [])):
        field_id = str(factor["evidence_field_id"])
        fields.append(
            {
                "field_id": field_id,
                "source_path": f"top_factors[{index}]",
                "label": str(factor.get("display_name") or _display_name(str(factor.get("feature") or ""))),
                "description": "위험 판단에 사용된 상위 요인",
            }
        )
    return fields


def _sensor_source_fields(sensor_evidence: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "field_id": f"sensor_evidence.sensors.{feature}",
            "source_path": f"evidence_payload.sensor_evidence.sensors.{feature}",
            "label": str(sensor.get("display_name") or _display_name(feature)),
            "description": "센서 관측 및 baseline 근거",
        }
        for feature, sensor in (sensor_evidence.get("sensors") or {}).items()
    ]


def _evidence_gaps(
    artifact: dict[str, Any],
    maintenance_context: dict[str, Any] | None,
    prediction: Prediction,
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    if not artifact.get("top_factors"):
        gaps.append(
            {
                "gap_id": "gap.top_factors.unavailable",
                "field": "top_factors",
                "reason": "insufficient_context",
                "required_source": "observation_history",
                "owner_domain": "diagnosis",
                "display_policy": "show_limitation",
            }
        )
    if maintenance_context is None:
        gaps.append(
            {
                "gap_id": "gap.maintenance_context.unavailable",
                "field": "evidence_payload.maintenance_context",
                "reason": "missing_source",
                "required_source": "maintenance_context_provider",
                "owner_domain": "maintenance",
                "display_policy": "show_as_unavailable",
            }
        )
    for index, issue in enumerate(prediction.quality_issues, start=1):
        gaps.append(
            {
                "gap_id": f"gap.data_quality.{index}",
                "field": str(issue.get("field") or "observation"),
                "reason": "insufficient_context",
                "required_source": "valid_runtime_observation",
                "owner_domain": "diagnosis",
                "display_policy": "show_limitation",
            }
        )
    return gaps


def _has_multiple_risk_factors(artifact: dict[str, Any]) -> bool:
    factors = artifact.get("top_factors") or []
    if len(factors) < 2:
        return False
    first = abs(float(factors[0].get("signed_contribution") or 0.0))
    second = abs(float(factors[1].get("signed_contribution") or 0.0))
    return second > 0 and first - second < 0.25


def _dedupe_source_fields(fields: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: dict[str, dict[str, str]] = {}
    for field in fields:
        deduped.setdefault(field["field_id"], field)
    return list(deduped.values())


def _display_name(feature: str) -> str:
    return DISPLAY_NAMES.get(feature) or _DISPLAY_FALLBACKS.get(feature) or feature


def _unit(feature: str) -> str:
    return UNITS.get(feature) or _UNIT_FALLBACKS.get(feature) or ""


def _source_type(feature: str) -> str:
    return "derived" if feature in {"temperature_difference_k", "mechanical_power_w", "overstrain_index"} else "observed"

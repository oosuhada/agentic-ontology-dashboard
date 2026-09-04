"""Deterministic user-language projection for predictive-maintenance artifacts.

Canonical artifacts stay immutable.  This module classifies their fields before
they are shown to a person or sent to an LLM, so policy/provenance fields cannot
be narrated as physical failure causes.
"""

from __future__ import annotations

import re
from typing import Any, Literal


PRESENTATION_DICTIONARY_VERSION = "predictive-maintenance-presentation-v1.0"

PresentationKind = Literal[
    "sensor", "derived", "model_output", "policy", "provenance", "internal"
]

_FIELD_CATALOG: dict[str, dict[str, Any]] = {
    "air_temperature_k": {"kind": "sensor", "ko": "흡입 공기 온도", "en": "Air temperature"},
    "process_temperature_k": {"kind": "sensor", "ko": "가공 온도", "en": "Process temperature"},
    "rotational_speed_rpm": {"kind": "sensor", "ko": "주축 회전수", "en": "Rotational speed"},
    "torque_nm": {"kind": "sensor", "ko": "구동 토크", "en": "Torque"},
    "tool_wear_min": {"kind": "sensor", "ko": "공구 사용 시간", "en": "Tool wear"},
    "power_w": {"kind": "derived", "ko": "모터 출력", "en": "Mechanical power"},
    "mechanical_power_w": {"kind": "derived", "ko": "모터 출력", "en": "Mechanical power"},
    "temperature_gap_k": {"kind": "derived", "ko": "공정·공기 온도차", "en": "Process-to-air temperature gap"},
    "temperature_difference_k": {"kind": "derived", "ko": "공정·공기 온도차", "en": "Process-to-air temperature gap"},
    "overstrain_load": {"kind": "derived", "ko": "과부하 누적 지표", "en": "Overstrain load"},
    "overstrain_index": {"kind": "derived", "ko": "과부하 누적 지표", "en": "Overstrain index"},
    "rotation_raw": {"kind": "sensor", "ko": "회전 평균", "en": "Rotation signal"},
    "vibration_raw": {"kind": "sensor", "ko": "진동 평균", "en": "Vibration signal"},
    "pressure_raw": {"kind": "sensor", "ko": "압력 평균", "en": "Pressure signal"},
    "voltage_raw": {"kind": "sensor", "ko": "전압", "en": "Voltage signal"},
    "relative_vibration_z": {"kind": "derived", "ko": "진동 이상도", "en": "Relative vibration score"},
    "generator_failure_score": {"kind": "model_output", "ko": "모델 산출 위험 점수", "en": "Model risk score"},
    "model_selected_threshold": {"kind": "policy", "ko": "고위험 판정 기준값", "en": "Risk decision threshold"},
    "asset_criticality_adjustment": {"kind": "policy", "ko": "설비 중요도 보정", "en": "Asset criticality adjustment"},
    "generator_model_artifact_manifest": {"kind": "provenance", "ko": "모델 릴리스 정보", "en": "Model release metadata"},
}

_WINDOW_SUFFIX = re.compile(r"_(?:1h|3h|6h|12h|24h|7d|30d)_(?:max_abs|abs_max|abs_mean|change|max|min|mean|std|last)$")


def normalized_field_key(value: str) -> str:
    return _WINDOW_SUFFIX.sub("", value)


def presentation_field(value: str, locale: str = "ko-KR") -> dict[str, str]:
    normalized = normalized_field_key(value)
    item = _FIELD_CATALOG.get(value) or _FIELD_CATALOG.get(normalized)
    if item:
        return {
            "key": value,
            "kind": str(item["kind"]),
            "label": str(item["en"] if locale == "en-US" else item["ko"]),
        }
    return {
        "key": value,
        "kind": "internal",
        "label": "Additional technical evidence" if locale == "en-US" else "추가 기술 근거",
    }


def partition_factors(
    factors: list[dict[str, Any]], locale: str = "ko-KR"
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
        "physical": [], "decision_basis": [], "technical_metadata": []
    }
    for factor in factors:
        projected = presentation_field(str(factor.get("feature") or ""), locale)
        item = {**factor, "display_name": projected["label"], "presentation_kind": projected["kind"]}
        if projected["kind"] in {"sensor", "derived"}:
            result["physical"].append(item)
        elif projected["kind"] in {"model_output", "policy"}:
            result["decision_basis"].append(item)
        else:
            result["technical_metadata"].append(item)
    return result


def asset_display_name(asset_id: str, locale: str = "ko-KR") -> str:
    match = re.match(r"^(CNC|CMP)-S(\d+)-L(\d+)-(\d+)$", asset_id, re.IGNORECASE)
    if not match:
        return asset_id
    kind, site, cell, slot = match.groups()
    if locale == "en-US":
        equipment = "Air compressor" if kind.upper() == "CMP" else "CNC machine"
        return f"Zone {int(site)} · Cell {int(cell)} · {equipment} {int(slot)}"
    equipment = "공기압축기" if kind.upper() == "CMP" else "CNC 가공기"
    return f"{int(site)}구역 · {int(cell)}셀 · {equipment} {int(slot)}"


def source_display_name(value: str, locale: str = "ko-KR") -> str:
    if value.startswith("gen-data-wall-clock-live"):
        return "Live equipment observations" if locale == "en-US" else "실시간 설비 관측 데이터"
    if "random-forest" in value:
        return "CNC failure-risk model" if locale == "en-US" else "CNC 고장 위험 예측 모델"
    if value.startswith("result-artifact"):
        return "Prediction evidence schema" if locale == "en-US" else "예측 결과 근거 형식"
    return "Technical source" if locale == "en-US" else "기술 출처"

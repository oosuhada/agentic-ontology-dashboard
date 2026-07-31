from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from .contracts import DISPLAY_NAMES, UNITS, derive_features, project_root
from .predictor import HeuristicPredictor, Prediction

NORMAL_RANGES = {
    "tool_wear_min": "0–180",
    "temperature_difference_k": "8.6–12.0",
    "mechanical_power_w": "3,500–9,000",
    "overstrain_index": "0–11,000",
    "torque_nm": "10–60",
}


class ContextProvider(Protocol):
    provider_name: str

    def get_context(self, equipment_id: str, failure_type: str) -> dict[str, Any]: ...


class FixtureContextProvider:
    provider_name = "fixture"

    def __init__(self, path: str | Path | None = None) -> None:
        source = Path(path) if path else project_root() / "data" / "fixtures" / "maintenance_context.json"
        self.payload = json.loads(source.read_text(encoding="utf-8"))

    def get_context(self, equipment_id: str, failure_type: str) -> dict[str, Any]:
        context = self.payload["contexts"].get(failure_type) or self.payload["contexts"]["uncertain"]
        return {
            "provider": self.provider_name,
            "version": self.payload["version"],
            "source_type": self.payload["source_type"],
            "source_refs": list(context["source_refs"]),
            "checklist": list(context["checklist"]),
            "recommended_actions": list(context["recommended_actions"]),
        }


def _factor_value(feature: str, observation: dict[str, Any], derived: dict[str, float]) -> float:
    if feature in derived:
        return float(derived[feature])
    return float(observation[feature])


def _source_type(feature: str) -> str:
    return "derived" if feature in {"temperature_difference_k", "mechanical_power_w", "overstrain_index"} else "observed"


def build_evidence_package(
    fixture: dict[str, Any],
    *,
    predictor: HeuristicPredictor | None = None,
    context_provider: ContextProvider | None = None,
) -> dict[str, Any]:
    model = predictor or HeuristicPredictor()
    prediction: Prediction = model.predict(fixture)
    provider = context_provider or FixtureContextProvider()
    observation = fixture["observation"]
    derived = {} if prediction.quality_issues else derive_features(observation)

    scored = prediction.factors[:5]
    total_score = sum(item.score for item in scored) or 1.0
    factors = [
        {
            "evidence_field_id": f"factor.{index + 1}.{item.feature}",
            "feature": item.feature,
            "display_name": DISPLAY_NAMES[item.feature],
            "value": round(_factor_value(item.feature, observation, derived), 4),
            "unit": UNITS[item.feature],
            "normal_range": NORMAL_RANGES[item.feature],
            "direction": item.direction,
            "contribution": round(item.score / total_score, 6),
            "source_type": _source_type(item.feature),
        }
        for index, item in enumerate(scored)
    ]

    history = fixture["history"]
    start = history[0]["timestamp"] if history else observation["timestamp"]
    context = provider.get_context(fixture["equipment"]["equipment_id"], prediction.predicted_failure_type)
    package = {
        "schema_version": "1.0",
        "evidence_id": f"EVD-{fixture['event_id']}",
        "event_id": fixture["event_id"],
        "scenario_id": fixture["scenario_id"],
        "equipment": fixture["equipment"],
        "model": {
            "model_version": prediction.model_version,
            "policy_version": model.policy["policy_version"],
            "mode": "deterministic_fallback",
        },
        "status": prediction.risk_band,
        "recommended_decision": prediction.recommended_decision,
        "confidence": prediction.confidence,
        "failure_probability": prediction.probability,
        "threshold": float(model.policy["decision_threshold"]),
        "predicted_failure_type": prediction.predicted_failure_type,
        "observation": {**observation, **derived},
        "history": history,
        "detected_interval": {"start": start, "end": observation["timestamp"]},
        "top_factors": factors,
        "maintenance_context": context,
        "data_quality_warnings": prediction.quality_issues,
        "lineage": {
            "fixture_id": fixture["scenario_id"],
            "fixture_schema_version": fixture["schema_version"],
            "sensor_source": "observed-compatible fixture",
            "context_source": f"{context['provider']}:{context['version']}",
        },
        "generated_at": observation["timestamp"],
    }
    validate_evidence_package(package)
    return package


def validate_evidence_package(package: dict[str, Any]) -> None:
    schema = json.loads((project_root() / "schemas" / "evidence-package.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(package), key=lambda item: list(item.absolute_path))
    if errors:
        rendered = "; ".join(
            f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}" for error in errors
        )
        raise ValueError(f"evidence schema validation failed: {rendered}")

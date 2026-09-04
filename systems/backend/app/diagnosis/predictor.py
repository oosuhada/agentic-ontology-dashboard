from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from .artifact_provider import LocalModelArtifactProvider
from .cnc_runtime_features import SUPPORTED_KIND as CNC_TEMPORAL_KIND
from .cnc_runtime_features import derive_cnc_temporal_features
from .compressor_runtime_features import SUPPORTED_KIND as COMPRESSOR_TEMPORAL_KIND
from .compressor_runtime_features import derive_compressor_temporal_features
from .feature_executor import execute_feature_contract
from .contracts import audit_fixture, derive_features
from .evidence_baseline import build_history_baseline_window


DEFAULT_POLICY_PATH = Path(__file__).with_name("threshold_policy.json")
FIXTURE_POLICY_PATH = Path(__file__).with_name("fixture_threshold_policy.json")
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
_HEURISTIC_DEFAULT_ENVIRONMENTS = {"local", "demo", "test"}
_RISK_UP_FEATURES = {
    "tool_wear_min",
    "torque_nm",
    "mechanical_power_w",
    "overstrain_index",
}
_RISK_DOWN_FEATURES = {
    "rotational_speed_rpm",
    "temperature_difference_k",
}


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


@dataclass(frozen=True)
class FactorScore:
    feature: str
    raw_value: float
    score: float
    direction: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "raw_value": self.raw_value,
            "score": self.score,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class Prediction:
    model_version: str
    probability: float | None
    risk_band: str
    recommended_decision: str
    confidence: str
    predicted_failure_type: str
    factors: list[FactorScore]
    quality_issues: list[dict[str, str]]
    model_artifact: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "probability": self.probability,
            "risk_band": self.risk_band,
            "recommended_decision": self.recommended_decision,
            "confidence": self.confidence,
            "predicted_failure_type": self.predicted_failure_type,
            "factors": [factor.to_dict() for factor in self.factors],
            "quality_issues": self.quality_issues,
            "model_artifact": self.model_artifact,
        }


class Predictor(Protocol):
    model_version: str
    policy: dict[str, Any]

    def predict(self, fixture: dict[str, Any]) -> Prediction: ...


class HeuristicPredictor:
    """Deterministic fixture predictor and offline fallback.

    It is intentionally separate from the trained benchmark model. The trained model
    demonstrates reproducible model development; this predictor guarantees that Gold
    product scenarios remain available without a binary artifact or external service.
    """

    model_version = "fixture-heuristic-v1"

    def __init__(self, policy_path: str | Path | None = None) -> None:
        path = Path(policy_path) if policy_path else FIXTURE_POLICY_PATH
        self.policy = json.loads(path.read_text(encoding="utf-8"))

    def predict(self, fixture: dict[str, Any]) -> Prediction:
        quality_issues = [issue.to_dict() for issue in audit_fixture(fixture)]
        if quality_issues:
            return Prediction(
                model_version=self.model_version,
                probability=None,
                risk_band="data_quality_hold",
                recommended_decision="hold_for_data_check",
                confidence="unavailable",
                predicted_failure_type="unavailable",
                factors=[],
                quality_issues=quality_issues,
                model_artifact=None,
            )

        observation = fixture["observation"]
        derived = derive_features(observation)
        wear = float(observation["tool_wear_min"])
        torque = float(observation["torque_nm"])
        speed = float(observation["rotational_speed_rpm"])
        temp_gap = derived["temperature_difference_k"]
        power = derived["mechanical_power_w"]
        overstrain = derived["overstrain_index"]

        components = {
            "tool_wear_min": _sigmoid((wear - 185.0) / 18.0),
            "temperature_difference_k": _sigmoid((8.5 - temp_gap) / 0.5) * _sigmoid((1400.0 - speed) / 80.0),
            "mechanical_power_w": _sigmoid((power - 9500.0) / 1200.0),
            "overstrain_index": _sigmoid((overstrain - 12000.0) / 1500.0),
            "torque_nm": _sigmoid((torque - 62.0) / 8.0),
        }
        ordered = sorted(components.items(), key=lambda item: item[1], reverse=True)
        primary = ordered[0][1]
        secondary = ordered[1][1]
        probability = min(0.99, max(0.01, 0.05 + 0.72 * primary + 0.18 * secondary))

        criticality = fixture["equipment"]["criticality"]
        adjustment = float(self.policy["criticality_adjustments"][criticality])
        attention = float(self.policy["severity_rules"]["attention"]) + adjustment
        warning = float(self.policy["severity_rules"]["warning"]) + adjustment
        # Equipment criticality can surface an event earlier, but it must not
        # silently lower the critical/shutdown-review boundary.
        critical = float(self.policy["severity_rules"]["critical"])

        if probability >= critical:
            risk_band = "critical"
        elif probability >= warning:
            risk_band = "warning"
        elif probability >= attention:
            risk_band = "attention"
        else:
            risk_band = "normal"

        if risk_band == "normal":
            failure_type = "none"
        elif risk_band == "critical" and (components["mechanical_power_w"] > 0.75 or components["overstrain_index"] > 0.75):
            failure_type = "power_or_overstrain_failure"
        elif primary > 0.55 and secondary > 0.55 and primary - secondary < 0.25:
            failure_type = "multi_factor_risk"
        else:
            top_feature = ordered[0][0]
            failure_type = {
                "tool_wear_min": "tool_wear_failure",
                "temperature_difference_k": "heat_dissipation_failure",
                "mechanical_power_w": "power_or_overstrain_failure",
                "overstrain_index": "power_or_overstrain_failure",
                "torque_nm": "power_or_overstrain_failure",
            }[top_feature]

        if risk_band == "normal":
            confidence = "high"
        elif risk_band == "critical":
            confidence = "high"
        elif risk_band == "attention":
            confidence = "low"
            failure_type = "uncertain"
        elif primary - secondary < 0.25:
            confidence = "medium"
        else:
            confidence = "high"

        raw_values = {
            "tool_wear_min": wear,
            "temperature_difference_k": temp_gap,
            "mechanical_power_w": power,
            "overstrain_index": overstrain,
            "torque_nm": torque,
        }
        factors = [
            FactorScore(
                feature=name,
                raw_value=raw_values[name],
                score=float(round(score, 6)),
                direction="risk_up" if score >= 0.5 else "risk_down",
            )
            for name, score in ordered
        ]
        decision = self.policy["decision_mapping"][risk_band]
        return Prediction(
            model_version=self.model_version,
            probability=float(round(probability, 6)),
            risk_band=risk_band,
            recommended_decision=decision,
            confidence=confidence,
            predicted_failure_type=failure_type,
            factors=factors,
            quality_issues=[],
            model_artifact=None,
        )


class CompressorHeuristicPredictor:
    """Demo/local fallback for canonical compressor telemetry.

    Compressor observations use a sensor contract that is intentionally separate
    from the AI4I-style CNC feature contract. This fallback therefore must not run
    the CNC heuristic against compressor fields. It grades the canonical vibration
    zone and uses the other observed compressor signals as supporting factors.

    The trained/versioned Model Artifact remains the production path. This class is
    only used by an explicitly enabled heuristic fallback environment.
    """

    model_version = "compressor-signal-heuristic-v1"
    _ZONE_STATUS = {
        "A": "normal",
        "B": "attention",
        "C": "warning",
        "D": "critical",
    }

    def __init__(self, policy_path: str | Path | None = None) -> None:
        path = Path(policy_path) if policy_path else DEFAULT_POLICY_PATH
        self.policy = json.loads(path.read_text(encoding="utf-8"))

    def predict(self, fixture: dict[str, Any]) -> Prediction:
        observation = fixture.get("observation") or {}
        required = (
            "voltage_raw",
            "rotation_raw",
            "pressure_raw",
            "vibration_raw",
            "relative_vibration_z",
            "relative_vibration_zone",
        )
        issues: list[dict[str, str]] = []
        missing = [name for name in required if observation.get(name) is None]
        if missing:
            issues.append({"code": "missing_field", "message": ", ".join(missing)})
        numeric: dict[str, float] = {}
        for name in required[:-1]:
            if observation.get(name) is None:
                continue
            try:
                value = float(observation[name])
            except (TypeError, ValueError):
                issues.append({"code": "invalid_numeric", "message": name})
                continue
            if not math.isfinite(value):
                issues.append({"code": "invalid_numeric", "message": name})
                continue
            numeric[name] = value
        zone = str(observation.get("relative_vibration_zone") or "").upper()
        if zone not in self._ZONE_STATUS:
            issues.append({"code": "invalid_vibration_zone", "message": zone or "missing"})
        if issues:
            return Prediction(
                model_version=self.model_version,
                probability=None,
                risk_band="data_quality_hold",
                recommended_decision="hold_for_data_check",
                confidence="unavailable",
                predicted_failure_type="unavailable",
                factors=[],
                quality_issues=issues,
                model_artifact=None,
            )

        z_value = numeric["relative_vibration_z"]
        z_component = min(1.0, abs(z_value) / 3.5)
        components = {
            "relative_vibration_z": z_component,
            "vibration_raw": _sigmoid((abs(numeric["vibration_raw"] - 40.0) - 8.0) / 4.0),
            "pressure_raw": _sigmoid((abs(numeric["pressure_raw"] - 100.0) - 12.0) / 6.0),
            "rotation_raw": _sigmoid((abs(numeric["rotation_raw"] - 450.0) - 45.0) / 20.0),
            "voltage_raw": _sigmoid((abs(numeric["voltage_raw"] - 170.0) - 18.0) / 8.0),
        }
        ordered = sorted(components.items(), key=lambda item: item[1], reverse=True)
        support = sorted((score for name, score in components.items() if name != "relative_vibration_z"), reverse=True)
        probability = min(0.99, max(0.01, 0.03 + 0.72 * z_component + 0.15 * support[0] + 0.05 * support[1]))
        risk_band = self._ZONE_STATUS[zone]
        distance = abs(probability - 0.5) * 2.0
        confidence = "high" if distance >= 0.6 else "medium" if distance >= 0.3 else "low"
        failure_type = "none" if risk_band == "normal" else "compressor_signal_anomaly"
        factors = [
            FactorScore(
                feature=name,
                raw_value=numeric[name],
                score=float(round(score, 6)),
                direction="risk_up" if score >= 0.5 else "risk_down",
            )
            for name, score in ordered
        ]
        return Prediction(
            model_version=self.model_version,
            probability=float(round(probability, 6)),
            risk_band=risk_band,
            recommended_decision=self.policy["decision_mapping"][risk_band],
            confidence=confidence,
            predicted_failure_type=failure_type,
            factors=factors,
            quality_issues=[],
            model_artifact=None,
        )


class ArtifactPredictor:
    """Runtime inference against a versioned Model Artifact provided by URI."""

    def __init__(self, artifact_uri: str | Path, policy_path: str | Path | None = None) -> None:
        loaded = LocalModelArtifactProvider(artifact_uri).load()
        self.loaded = loaded
        self.model = loaded.model
        self.manifest = loaded.manifest
        self.feature_schema = loaded.feature_schema
        self.history_requirement = loaded.history_requirement
        self.model_version = str(self.manifest["model_version"])
        policy = Path(policy_path) if policy_path else DEFAULT_POLICY_PATH
        self.policy = json.loads(policy.read_text(encoding="utf-8"))

    def predict(self, fixture: dict[str, Any]) -> Prediction:
        engineering_kind = (self.feature_schema.get("feature_engineering") or {}).get("kind")
        temporal_compressor = engineering_kind == COMPRESSOR_TEMPORAL_KIND
        temporal_cnc = engineering_kind == CNC_TEMPORAL_KIND
        temporal_model = temporal_compressor or temporal_cnc
        quality_issues = [] if temporal_model else [issue.to_dict() for issue in audit_fixture(fixture)]
        if quality_issues:
            return Prediction(
                model_version=self.model_version,
                probability=None,
                risk_band="data_quality_hold",
                recommended_decision="hold_for_data_check",
                confidence="unavailable",
                predicted_failure_type="unavailable",
                factors=[],
                quality_issues=quality_issues,
                model_artifact=self._artifact_reference(),
            )

        declared_features = list(self.feature_schema.get("features") or [])
        feature_names = [
            str(item["name"]) if isinstance(item, dict) else str(item)
            for item in declared_features
        ]
        if not feature_names:
            raise ValueError("Model Artifact feature schema has no features")
        if temporal_model:
            try:
                values = (
                    derive_compressor_temporal_features(fixture, self.feature_schema)
                    if temporal_compressor
                    else derive_cnc_temporal_features(fixture, self.feature_schema)
                )
            except (TypeError, ValueError) as exc:
                return Prediction(
                    model_version=self.model_version,
                    probability=None,
                    risk_band="data_quality_hold",
                    recommended_decision="hold_for_data_check",
                    confidence="unavailable",
                    predicted_failure_type="unavailable",
                    factors=[],
                    quality_issues=[
                        {
                            "code": "insufficient_runtime_context",
                            "field": "history",
                            "message": str(exc),
                            "severity": "error",
                        }
                    ],
                    model_artifact=self._artifact_reference(),
                )
        else:
            observation = fixture["observation"]
            derived = derive_features(observation)
            direct_values = {**observation, **derived}
            values = execute_feature_contract(
                fixture,
                feature_names=feature_names,
                direct_values=direct_values,
                history_requirement=self.history_requirement,
                executor_version=str(
                    (self.manifest.get("compatibility") or {}).get("feature_executor_version") or ""
                )
                or None,
            )
        frame = pd.DataFrame([{feature: values[feature] for feature in feature_names}])
        probability = float(self.model.predict_proba(frame)[:, 1][0])

        criticality = fixture["equipment"]["criticality"]
        adjustment = float(self.policy["criticality_adjustments"][criticality])
        selected_threshold = float(
            self.manifest.get("training_config", {}).get("selected_threshold", 0.5)
        )
        if not 0.0 <= selected_threshold <= 1.0:
            raise ValueError("Model Artifact selected_threshold must be between 0 and 1")
        # A model-positive prediction must never be presented as operationally
        # normal/continue_monitoring.  The artifact threshold is therefore the
        # upper bound of the attention boundary, while warning/critical remain
        # Backend-owned operational severity thresholds.
        attention = min(
            float(self.policy["severity_rules"]["attention"]) + adjustment,
            selected_threshold,
        )
        warning = float(self.policy["severity_rules"]["warning"]) + adjustment
        critical = float(self.policy["severity_rules"]["critical"])
        if probability >= critical:
            risk_band = "critical"
        elif probability >= warning:
            risk_band = "warning"
        elif probability >= attention:
            risk_band = "attention"
        else:
            risk_band = "normal"

        distance = abs(probability - 0.5) * 2.0
        confidence = "high" if distance >= 0.6 else "medium" if distance >= 0.3 else "low"
        return Prediction(
            model_version=self.model_version,
            probability=float(round(probability, 6)),
            risk_band=risk_band,
            recommended_decision=self.policy["decision_mapping"][risk_band],
            confidence=confidence,
            predicted_failure_type="failure_risk" if probability >= selected_threshold else "none",
            factors=(
                self._temporal_factor_scores(feature_names, values)
                if temporal_model
                else self._factor_scores(feature_names, values, fixture)
            ),
            quality_issues=[],
            model_artifact=self._artifact_reference(),
        )

    def _temporal_factor_scores(self, feature_names: list[str], values: dict[str, Any]) -> list[FactorScore]:
        feature_weights, weights_are_signed = self._original_feature_weights(feature_names)
        if not feature_weights:
            return []
        scores: list[FactorScore] = []
        for feature, model_weight in feature_weights.items():
            if feature not in values:
                continue
            raw_value = float(values[feature])
            signed_score = model_weight * raw_value if weights_are_signed else abs(model_weight) * abs(raw_value)
            if not math.isfinite(signed_score) or signed_score == 0:
                continue
            scores.append(
                FactorScore(
                    feature=feature,
                    raw_value=raw_value,
                    score=float(round(abs(signed_score), 6)),
                    direction="risk_up" if signed_score > 0 else "risk_down",
                )
            )
        return sorted(scores, key=lambda item: item.score, reverse=True)[:5]

    def _factor_scores(self, feature_names: list[str], values: dict[str, Any], fixture: dict[str, Any]) -> list[FactorScore]:
        feature_weights, weights_are_signed = self._original_feature_weights(feature_names)
        if not feature_weights:
            return []

        baseline_window = build_history_baseline_window(fixture, enrich_row=derive_features)
        scores: list[FactorScore] = []
        for feature, model_weight in feature_weights.items():
            if feature not in values:
                continue
            try:
                raw_value = float(values[feature])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(raw_value):
                continue

            stat = baseline_window.stat(feature, raw_value)
            if stat.z_score is None:
                continue
            local_delta = stat.z_score
            if weights_are_signed:
                signed_score = model_weight * local_delta
            else:
                signed_score = abs(model_weight) * _domain_oriented_delta(feature, local_delta)
            if signed_score == 0:
                continue
            direction = "risk_up" if signed_score > 0 else "risk_down"
            scores.append(
                FactorScore(
                    feature=feature,
                    raw_value=raw_value,
                    score=float(round(abs(signed_score), 6)),
                    direction=direction,
                )
            )
        return sorted(scores, key=lambda item: item.score, reverse=True)

    def _original_feature_weights(self, feature_names: list[str]) -> tuple[dict[str, float], bool]:
        classifier = getattr(self.model, "named_steps", {}).get("classifier")
        if classifier is None:
            return {}, False
        weights = getattr(classifier, "feature_importances_", None)
        weights_are_signed = False
        if weights is None:
            coefficients = getattr(classifier, "coef_", None)
            if coefficients is not None and len(coefficients):
                weights = coefficients[0]
                weights_are_signed = True
        if weights is None:
            return {}, False

        preprocessor = getattr(self.model, "named_steps", {}).get("preprocess")
        if preprocessor is None:
            transformed_names = feature_names
        else:
            try:
                transformed_names = list(preprocessor.get_feature_names_out(feature_names))
            except ValueError:
                transformed_names = feature_names

        aggregated: dict[str, float] = {}
        for transformed_name, weight in zip(transformed_names, weights):
            original = _original_feature_name(str(transformed_name), feature_names)
            aggregated[original] = aggregated.get(original, 0.0) + float(weight)
        return aggregated, weights_are_signed

    def _artifact_reference(self) -> dict[str, Any]:
        return {
            "artifact_type": self.manifest["artifact_type"],
            "artifact_schema_version": self.manifest["artifact_schema_version"],
            "model_id": self.manifest["model_id"],
            "model_version": self.manifest["model_version"],
            "dataset_version": self.manifest["dataset_version"],
            "feature_schema_version": self.manifest["feature_schema_version"],
            "checksum": self.manifest["checksum"],
        }


def configured_predictor(asset_type: str | None = None) -> Predictor:
    """Resolve runtime inference from injected artifact or explicit Operations fallback."""

    # Preserve the historical no-argument resolver contract for compatibility
    # callers. Product runtime paths now pass the fixture asset family explicitly.
    normalized_asset_type = str(asset_type or "cnc").strip().lower()
    artifact_env = "CNC_MODEL_ARTIFACT_URI" if normalized_asset_type == "cnc" else "MODEL_ARTIFACT_URI"
    artifact_uri = os.getenv(artifact_env, "").strip()
    if artifact_uri:
        return ArtifactPredictor(artifact_uri)

    configured_fallback = os.getenv("ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK", "").strip().lower()
    app_env = os.getenv("APP_ENV", "local").strip().lower()
    fallback_enabled = (
        configured_fallback in _TRUTHY_ENV_VALUES
        if configured_fallback
        else app_env in _HEURISTIC_DEFAULT_ENVIRONMENTS
    )
    if not fallback_enabled:
        raise RuntimeError(
            f"{artifact_env} is required because heuristic fallback is disabled "
            f"for APP_ENV={app_env!r}; set "
            "ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK=1 only when an explicit fallback is intended"
        )
    return CompressorHeuristicPredictor() if normalized_asset_type == "compressor" else HeuristicPredictor()


def _original_feature_name(transformed_name: str, feature_names: list[str]) -> str:
    suffix = transformed_name.split("__", 1)[-1]
    for feature in feature_names:
        if suffix == feature or suffix.startswith(f"{feature}_"):
            return feature
    return suffix
def _domain_oriented_delta(feature: str, local_delta: float) -> float:
    if feature in _RISK_DOWN_FEATURES:
        return -local_delta
    return local_delta

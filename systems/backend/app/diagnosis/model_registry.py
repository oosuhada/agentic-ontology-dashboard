from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

import joblib
import numpy as np
import pandas as pd

from .model_contracts import (
    ArtifactReference,
    ExplanationArtifact,
    ExplanationFactor,
    ModelScoreResult,
    ModelVersion,
    ThresholdPolicy,
    canonical_checksum,
)


class ArtifactStore(Protocol):
    def read_bytes(self, reference: ArtifactReference) -> bytes: ...

REGISTRY_VERSION = "model-registry-v1"


def load_model(model: ModelVersion, artifact_store: ArtifactStore) -> Any:
    payload = artifact_store.read_bytes(model.artifact)
    return joblib.load(io.BytesIO(payload))


def input_schema_checksum(
    *,
    input_features: list[str],
    schema_metadata: dict[str, Any],
    recipe_set_id: str,
) -> str:
    column_by_name = {
        str(item.get("name")): str(item.get("dtype"))
        for item in schema_metadata.get("columns", [])
        if isinstance(item, dict) and item.get("name")
    }
    return canonical_checksum(
        {
            "recipe_set_id": recipe_set_id,
            "features": [
                {"name": feature, "dtype": column_by_name.get(feature, "unknown")}
                for feature in input_features
            ],
            "feature_engine_version": schema_metadata.get("feature_engine_version"),
        }
    )


def validate_scoring_input(model: ModelVersion, features: dict[str, Any], expected_checksum: str) -> None:
    if expected_checksum != model.input_schema_checksum_sha256:
        raise ValueError("scoring input schema checksum does not match active Model Version")
    expected = set(model.input_features)
    supplied = set(features)
    missing = sorted(expected - supplied)
    extra = sorted(supplied - expected)
    if missing or extra:
        raise ValueError(
            "scoring input fields do not match Model Version: "
            f"missing={missing}, extra={extra}"
        )


def _positive_probability(pipeline: Any, frame: pd.DataFrame) -> float:
    probabilities = pipeline.predict_proba(frame)
    if probabilities.shape[1] != 2:
        raise ValueError("operational predictive model must expose binary probabilities")
    return float(probabilities[0, 1])


def _linear_factors(pipeline: Any, frame: pd.DataFrame, input_features: list[str]) -> list[ExplanationFactor]:
    preprocessor = pipeline.named_steps["preprocess"]
    classifier = pipeline.named_steps["classifier"]
    transformed = np.asarray(preprocessor.transform(frame))
    coefficients = np.asarray(classifier.coef_).reshape(-1)
    values = transformed.reshape(-1)
    names = list(preprocessor.get_feature_names_out())
    contributions = values * coefficients
    ranked = sorted(
        zip(names, values, contributions, strict=True),
        key=lambda item: abs(float(item[2])),
        reverse=True,
    )[:10]
    return [
        ExplanationFactor(
            rank=index,
            feature=str(name).split("__", 1)[-1],
            observed_value=float(value),
            direction="risk_up" if contribution > 0 else "risk_down" if contribution < 0 else "neutral",
            contribution=float(contribution),
        )
        for index, (name, value, contribution) in enumerate(ranked, start=1)
    ]


def _tree_perturbation_factors(
    pipeline: Any,
    frame: pd.DataFrame,
    input_features: list[str],
) -> list[ExplanationFactor]:
    full_probability = _positive_probability(pipeline, frame)
    contributions: list[tuple[str, Any, float]] = []
    for feature in input_features:
        perturbed = frame.copy(deep=True)
        value = perturbed.iloc[0][feature]
        perturbed.loc[:, feature] = 0 if isinstance(value, (int, float, np.number)) else None
        probability_without_feature = _positive_probability(pipeline, perturbed)
        contributions.append((feature, value, full_probability - probability_without_feature))
    ranked = sorted(contributions, key=lambda item: abs(float(item[2])), reverse=True)[:10]
    return [
        ExplanationFactor(
            rank=index,
            feature=feature,
            observed_value=(value.item() if isinstance(value, np.generic) else value),
            direction="risk_up" if contribution > 0 else "risk_down" if contribution < 0 else "neutral",
            contribution=float(contribution),
        )
        for index, (feature, value, contribution) in enumerate(ranked, start=1)
    ]


def explain_prediction(
    *,
    pipeline: Any,
    model: ModelVersion,
    prediction_result_id: str,
    observation_id: str,
    observed_at: datetime,
    features: dict[str, Any],
) -> ExplanationArtifact:
    frame = pd.DataFrame([{feature: features[feature] for feature in model.input_features}])
    try:
        if model.algorithm == "logistic_regression":
            factors = _linear_factors(pipeline, frame, model.input_features)
            provider = "linear_contribution"
        else:
            factors = _tree_perturbation_factors(pipeline, frame, model.input_features)
            provider = "feature_perturbation"
        status = "available"
        unavailable_reason = None
    except Exception as exc:
        factors = []
        provider = model.explanation_provider
        status = "unavailable"
        unavailable_reason = f"{type(exc).__name__}: {exc}"
    identity_payload = {
        "prediction_result_id": prediction_result_id,
        "observation_id": observation_id,
        "model_version_id": model.model_version_id,
        "recipe_set_id": model.recipe_set_id,
        "provider": provider,
        "provider_version": model.explanation_provider_version,
        "top_factors": [item.model_dump(mode="json") for item in factors],
        "status": status,
        "unavailable_reason": unavailable_reason,
    }
    checksum = canonical_checksum(identity_payload)
    return ExplanationArtifact(
        organization_id=model.organization_id,
        project_id=model.project_id,
        workspace_id=model.workspace_id,
        explanation_id=f"explanation-{checksum[:24]}",
        prediction_result_id=prediction_result_id,
        observation_id=observation_id,
        observed_at=observed_at,
        model_version_id=model.model_version_id,
        recipe_set_id=model.recipe_set_id,
        provider=provider,
        provider_version=model.explanation_provider_version,
        status=status,
        top_factors=factors,
        input_schema_checksum_sha256=model.input_schema_checksum_sha256,
        checksum_sha256=checksum,
        unavailable_reason=unavailable_reason,
        causal_proof=False,
    )


def score_model(
    *,
    model: ModelVersion,
    artifact_store: ArtifactStore,
    observation_id: str,
    observed_at: datetime,
    features: dict[str, Any],
    expected_input_schema_checksum_sha256: str,
) -> tuple[ModelScoreResult, ExplanationArtifact]:
    if str(model.status) != "active":
        raise ValueError("only an active Model Version can score operational observations")
    validate_scoring_input(model, features, expected_input_schema_checksum_sha256)
    pipeline = load_model(model, artifact_store)
    frame = pd.DataFrame([{feature: features[feature] for feature in model.input_features}])
    probability = _positive_probability(pipeline, frame)
    threshold = model.threshold_policy.selected_operational_threshold
    prediction_result_id = f"prediction-{uuid.uuid5(uuid.NAMESPACE_URL, canonical_checksum({'model': model.model_version_id, 'observation': observation_id, 'observed_at': observed_at.isoformat(), 'features': features}))}"
    explanation = explain_prediction(
        pipeline=pipeline,
        model=model,
        prediction_result_id=prediction_result_id,
        observation_id=observation_id,
        observed_at=observed_at,
        features=features,
    )
    result = ModelScoreResult(
        prediction_result_id=prediction_result_id,
        model_version_id=model.model_version_id,
        prediction_task=model.prediction_task,
        failure_probability=probability,
        decision_threshold=threshold,
        predicted_label="failure_risk" if probability >= threshold else "no_significant_risk",
        confidence=None,
        confidence_status=model.confidence_status,
        observation_id=observation_id,
        observed_at=observed_at,
        input_schema_checksum_sha256=model.input_schema_checksum_sha256,
        explanation_id=explanation.explanation_id,
    )
    return result, explanation


def threshold_from_experiment_report(report: dict[str, Any]) -> ThresholdPolicy:
    return ThresholdPolicy.model_validate(report["threshold_policy"])


__all__ = [
    "REGISTRY_VERSION",
    "explain_prediction",
    "input_schema_checksum",
    "load_model",
    "score_model",
    "threshold_from_experiment_report",
    "validate_scoring_input",
]

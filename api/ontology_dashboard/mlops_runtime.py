"""Governed feature, drift, promotion and rollback contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DriftEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metric: Literal["psi", "js_divergence", "missing_rate", "performance_drop"]
    value: float = Field(ge=0)
    threshold: float = Field(gt=0)
    sample_size: int = Field(ge=1)
    delayed_labels_available: bool = False


class MLOpsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    feature_view: dict[str, object]
    deployment: dict[str, object]
    drift: dict[str, object]
    retraining: dict[str, object]
    rollback: dict[str, object]
    explanation: dict[str, object]
    limitations: tuple[str, ...]


def evaluate_drift(request: DriftEvaluationRequest) -> dict[str, object]:
    minimum = 500
    enough_samples = request.sample_size >= minimum
    breached = enough_samples and request.value >= request.threshold
    return {
        "metric": request.metric,
        "value": request.value,
        "threshold": request.threshold,
        "sample_size": request.sample_size,
        "minimum_sample_size": minimum,
        "state": "breached" if breached else "insufficient_sample" if not enough_samples else "healthy",
        "retraining_action": "queue_review" if breached else "none",
        "automatic_promotion": False,
        "delayed_labels_available": request.delayed_labels_available,
    }


def mlops_snapshot() -> MLOpsSnapshot:
    drift = evaluate_drift(DriftEvaluationRequest(metric="psi", value=0.24, threshold=0.2, sample_size=1800))
    return MLOpsSnapshot(
        feature_view={
            "id": "asset-risk-features", "version": 1,
            "offline": "point-in-time as-of join", "online": "not_configured",
            "parity": "schema and transform checksum enforced",
            "freshness": "stale online values fail closed",
            "markings": ["confidential"],
        },
        deployment={
            "champion": "model-v3.1", "challenger": "model-v4-candidate",
            "mode": "shadow", "traffic_percent": 0,
            "shadow_can_trigger_actions": False,
            "canary_gate": "human approval + metric window",
        },
        drift=drift,
        retraining={
            "state": "review_required", "reproducibility": "Dataset Version + Feature View + code checksum",
            "test_data_for_threshold_selection": False,
        },
        rollback={
            "target": "model-v3.1", "unit": "model + feature + policy + artifact",
            "trigger": "canary SLO breach", "automatic": "only to approved previous unit",
        },
        explanation={"provider": "tree-shap", "quality_state": "monitored", "fallback_label": "unavailable"},
        limitations=(
            "online feature store requires Redis-compatible production configuration",
            "current benchmark data is synthetic and not production performance evidence",
            "drift queues review; it never promotes a model by itself",
        ),
    )


__all__ = ["DriftEvaluationRequest", "MLOpsSnapshot", "evaluate_drift", "mlops_snapshot"]

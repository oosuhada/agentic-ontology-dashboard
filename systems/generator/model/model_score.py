"""Neutral ModelScore contract for offline evaluation in the model domain."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelScore:
    """Neutral model prediction score and explainability result.

    Decoupled from operational runtime PredictionOutput and backend evidence schemas.
    """

    probability: float
    predicted_class: int
    feature_importance: dict[str, float] | None = None
    shap_values: dict[str, float] | None = None

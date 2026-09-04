"""XGBoost model implementation for predictive maintenance."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb

from systems.generator.model.model_score import ModelScore

logger = logging.getLogger(__name__)

EXCLUDE_META_COLUMNS = {
    "datetime",
    "observed_at",
    "machineID",
    "asset_id",
    "period_start",
    "anchor",
    "failure_point",
    "exclusion_end",
    "degradation_start",
    "label",
}


class XGBoostModel:
    """XGBoost-based failure probability prediction model."""

    name = "xgboost"
    algorithm = "xgboost"
    framework = "xgboost"

    def __init__(self) -> None:
        self.model: Any = None
        self.feature_cols: list[str] | None = None

    def train(
        self,
        df: pd.DataFrame,
        feature_names: list[str] | None = None,
        target_col: str = "label",
        id_col: str | None = None,
        time_col: str | None = None,
        random_state: int = 42,
        **kwargs: Any,
    ) -> None:
        """Train the XGBoost classifier with explicit feature allowlist."""
        if target_col not in df.columns:
            raise ValueError(f"Target column '{target_col}' not found in training DataFrame.")

        if feature_names is not None:
            self.feature_cols = list(feature_names)
        else:
            exclude = set(EXCLUDE_META_COLUMNS)
            if id_col:
                exclude.add(id_col)
            if time_col:
                exclude.add(time_col)
            exclude.add(target_col)
            self.feature_cols = [c for c in df.columns if c not in exclude]

        if not self.feature_cols:
            raise ValueError("No feature columns available for training.")

        missing_features = [c for c in self.feature_cols if c not in df.columns]
        if missing_features:
            raise ValueError(f"Declared feature columns missing from DataFrame: {missing_features}")

        for col in self.feature_cols:
            if not pd.api.types.is_numeric_dtype(df[col]):
                raise ValueError(f"Feature column '{col}' has non-numeric dtype '{df[col].dtype}'.")

        X = df[self.feature_cols]
        y = df[target_col].astype(int)

        logger.info(f"[{self.name}] Training with {len(self.feature_cols)} features on shape {X.shape}")
        self.model = xgb.XGBClassifier(
            random_state=random_state,
            eval_metric="logloss",
            **kwargs,
        )
        self.model.fit(X, y)

    def predict_proba(self, df: pd.DataFrame) -> np.ndarray:
        """Predict class probabilities for the input DataFrame."""
        if self.model is None or self.feature_cols is None:
            raise RuntimeError("Model has not been trained or loaded yet.")

        missing = [c for c in self.feature_cols if c not in df.columns]
        if missing:
            raise ValueError(f"Input DataFrame is missing required features: {missing}")

        X = df[self.feature_cols]
        return self.model.predict_proba(X)

    def predict(self, df: pd.DataFrame) -> ModelScore:
        """Predict failure probability and class for recent sample."""
        return self.explain(df)

    def explain(self, df: pd.DataFrame) -> ModelScore:
        """Calculate feature importance and optional SHAP contribution for offline evaluation."""
        if self.model is None or self.feature_cols is None:
            raise RuntimeError("Model has not been trained or loaded yet.")

        probs = self.predict_proba(df)
        last_prob = float(probs[-1, 1]) if probs.ndim == 2 else float(probs[-1])
        pred_class = int(last_prob >= 0.5)

        raw_importances = getattr(self.model, "feature_importances_", None)
        if raw_importances is not None and len(raw_importances) == len(self.feature_cols):
            importance = {k: float(v) for k, v in zip(self.feature_cols, raw_importances)}
        else:
            importance = {k: 0.0 for k in self.feature_cols}

        shap_dict: dict[str, float] | None = None
        try:
            import shap

            last_row = df[self.feature_cols].iloc[[-1]]
            explainer = shap.TreeExplainer(self.model)
            shap_values = explainer.shap_values(last_row)

            if isinstance(shap_values, list):
                sv = np.array(shap_values[1])[0] if len(shap_values) > 1 else np.array(shap_values[0])[0]
            elif isinstance(shap_values, np.ndarray):
                if len(shap_values.shape) == 3:
                    sv = shap_values[0, :, 1]
                else:
                    sv = shap_values[0]
            else:
                sv = np.array(shap_values)[0]

            sv = np.array(sv).flatten()
            if len(sv) == len(self.feature_cols):
                shap_dict = {k: float(v) for k, v in zip(self.feature_cols, sv)}
        except Exception as e:
            logger.debug(f"[{self.name}] SHAP explanation skipped: {e}")

        return ModelScore(
            probability=last_prob,
            predicted_class=pred_class,
            feature_importance=importance,
            shap_values=shap_dict,
        )

    def save(self, path: str | Path) -> None:
        """Save the sklearn-compatible estimator expected by Backend runtime."""
        if self.model is None:
            raise RuntimeError("Model has not been trained or loaded yet.")
        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, target_path)

    def load(self, path: str | Path) -> None:
        """Load estimator, accepting the pre-contract wrapper format for local compatibility."""
        data = joblib.load(path)
        if isinstance(data, dict) and "model" in data:
            self.model = data["model"]
            self.feature_cols = list(data.get("feature_cols") or [])
            return
        self.model = data
        names = getattr(self.model, "feature_names_in_", None)
        if names is None:
            booster = getattr(self.model, "get_booster", lambda: None)()
            names = getattr(booster, "feature_names", None)
        self.feature_cols = [str(name) for name in names] if names is not None else None

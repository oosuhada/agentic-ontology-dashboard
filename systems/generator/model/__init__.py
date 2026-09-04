"""Model training, multi-algorithm offline evaluation, and immutable Model Artifact publication."""

from __future__ import annotations

from .lightgbm import LightGBMModel
from .model_registry import (
    ModelRegistry,
    get_latest_model_path,
    get_next_run_version,
    has_any_published_model_artifact,
    has_any_trained_model,
    load_registry,
    publish_model_artifact,
    save_run_result,
    train_and_publish_model,
    validate_manifest,
    validate_model_artifact_directory,
)


from .model_score import ModelScore
from .model_training import (
    FRAMEWORK_BY_ALGORITHM,
    MODEL_SPECS,
    REGISTERED_MODELS,
    ModelTraining,
    asset_time_split,
    get_model_class,
    infer_history_requirement,
    run_parsing_only,
    train_all,
    train_and_evaluate,
)
from .random_forest import RandomForestModel
from .xgboost import XGBoostModel

__all__ = [
    "FRAMEWORK_BY_ALGORITHM",
    "LightGBMModel",
    "MODEL_SPECS",
    "ModelRegistry",
    "ModelScore",
    "ModelTraining",
    "REGISTERED_MODELS",
    "RandomForestModel",
    "XGBoostModel",
    "asset_time_split",
    "get_latest_model_path",
    "get_model_class",
    "get_next_run_version",
    "has_any_published_model_artifact",
    "has_any_trained_model",
    "infer_history_requirement",

    "load_registry",
    "publish_model_artifact",
    "run_parsing_only",
    "save_run_result",
    "train_all",
    "train_and_evaluate",
    "train_and_publish_model",
    "validate_manifest",
    "validate_model_artifact_directory",
]

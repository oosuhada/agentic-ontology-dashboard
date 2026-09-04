"""Training service orchestrating Feature Bundle consumption, training, and artifact publishing."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from systems.generator.app.feature.feature_repository import FeatureRepository
from systems.generator.app.feature.feature_schema_provider import FeatureSchemaProvider
from systems.generator.app.feature.label_schema_provider import LabelSchemaProvider
from systems.generator.app.training.data_splitter import asset_time_split
from systems.generator.app.training.training_config_provider import (
    TrainingConfigProvider,
    TrainingConfigSpec,
)
from systems.generator.app.training.training_exception import (
    FeatureDatasetIntegrityError,
    ModelActivationCommitError,
    ModelActivationInProgressError,
    ModelActivationTargetInvalidError,
    ModelActivationVerifyError,
    TrainingContractError,
    TrainingDependencyError,
    TrainingExecutionError,
    TrainingInputNotFoundError,
    TrainingModelNotFoundError,
)
from systems.generator.app.training.training_schema import (
    ModelTrainingResult,
    TrainingRequest,
    TrainingResponse,
)
from systems.generator.model.publisher import (
    ModelArtifactPublisher,
    build_history_requirement_from_feature_schema,
)
from systems.generator.model.registry import REGISTERED_MODELS, ModelTrainer

logger = logging.getLogger(__name__)


class TrainingService:
    """Service handling dataset splitting, multi-model training execution, and artifact publishing."""

    def __init__(
        self,
        feature_repository: FeatureRepository | None = None,
        artifact_publisher: ModelArtifactPublisher | None = None,
        training_config_provider: TrainingConfigProvider | None = None,
        feature_schema_provider: FeatureSchemaProvider | None = None,
        label_schema_provider: LabelSchemaProvider | None = None,
    ) -> None:
        self.feature_repository = feature_repository or FeatureRepository()
        self.artifact_publisher = artifact_publisher or ModelArtifactPublisher()
        self.training_config_provider = training_config_provider or TrainingConfigProvider()
        self.feature_schema_provider = feature_schema_provider or FeatureSchemaProvider()
        self.label_schema_provider = label_schema_provider or LabelSchemaProvider()

    def train_models(
        self,
        req: TrainingRequest,
        target_model: str | None = None,
        request_id: str | None = None,
    ) -> TrainingResponse:
        """Execute model training for all registered models or a specific base model."""
        req_id = request_id or f"req-{uuid.uuid4().hex[:12]}"
        run_id = f"run-{uuid.uuid4().hex[:12]}"

        logger.info(
            f"[TrainingService] Starting training run_id={run_id}, req_id={req_id}, "
            f"dataset={req.dataset_id}:{req.dataset_version}, feature_ver={req.feature_dataset_version}, "
            f"config_ver={req.training_config_version}, target_model={target_model or 'ALL'}"
        )

        # 1. Load and validate Training Configuration from versioned config file
        config_spec: TrainingConfigSpec = self.training_config_provider.load_training_config(
            req.training_config_version
        )

        # 2. Load and validate Feature Dataset Bundle
        bundle_data = self.feature_repository.load_bundle_data(
            dataset_id=req.dataset_id,
            dataset_version=req.dataset_version,
            feature_dataset_version=req.feature_dataset_version,
        )
        if bundle_data is None:
            raise TrainingInputNotFoundError(
                f"Feature Dataset Bundle '{req.feature_dataset_version}'을 찾을 수 없습니다."
            )

        # 3. Strict identity & fingerprint cross-validation
        meta = bundle_data.feature_metadata
        if meta.get("dataset_id") != req.dataset_id:
            raise TrainingContractError(
                f"Feature Bundle dataset_id('{meta.get('dataset_id')}')과 요청 dataset_id('{req.dataset_id}')가 일치하지 않습니다."
            )
        if meta.get("dataset_version") != req.dataset_version:
            raise TrainingContractError(
                f"Feature Bundle dataset_version('{meta.get('dataset_version')}')과 요청 dataset_version('{req.dataset_version}')이 일치하지 않습니다."
            )
        if meta.get("feature_dataset_version") != req.feature_dataset_version:
            raise TrainingContractError(
                f"Feature Bundle feature_dataset_version('{meta.get('feature_dataset_version')}')과 요청 버전('{req.feature_dataset_version}')이 일치하지 않습니다."
            )

        # 4. Strict provenance and schema snapshot validation (No silent fallback!)
        prov = meta.get("provenance", {})
        feat_schema_ver = prov.get("feature_schema_version")
        if not feat_schema_ver or not str(feat_schema_ver).strip():
            raise TrainingContractError("Feature Bundle provenance에 feature_schema_version이 누락되었습니다.")

        expected_feat_sha = prov.get("feature_schema_sha256")
        if not expected_feat_sha or not str(expected_feat_sha).strip():
            raise FeatureDatasetIntegrityError("Feature Bundle provenance에 feature_schema_sha256이 누락되었습니다.")

        label_schema_ver = prov.get("label_schema_version")
        if not label_schema_ver or not str(label_schema_ver).strip():
            raise TrainingContractError("Feature Bundle provenance에 label_schema_version이 누락되었습니다.")

        expected_label_sha = prov.get("label_schema_sha256")
        if not expected_label_sha or not str(expected_label_sha).strip():
            raise FeatureDatasetIntegrityError("Feature Bundle provenance에 label_schema_sha256이 누락되었습니다.")

        horizon_hours = prov.get("prediction_horizon_hours")
        if horizon_hours is None:
            raise TrainingContractError("Feature Bundle provenance에 prediction_horizon_hours가 누락되었습니다.")
        if type(horizon_hours) is not int or horizon_hours <= 0:
            raise TrainingContractError(
                f"Feature Bundle provenance 'prediction_horizon_hours' must be a positive integer, got {horizon_hours!r} ({type(horizon_hours).__name__})"
            )

        # Load official feature schema snapshot and verify checksum against bundle provenance
        try:
            feature_schema_spec = getattr(self.feature_schema_provider, "load_feature_schema", getattr(self.feature_schema_provider, "get_feature_schema"))(feat_schema_ver)
        except Exception as exc:
            raise TrainingContractError(f"Feature Schema 로드 실패: {exc}") from exc

        actual_feat_sha = feature_schema_spec.compute_checksum()
        if actual_feat_sha != expected_feat_sha:
            raise FeatureDatasetIntegrityError(
                f"Feature Schema SHA-256 불일치: Feature Bundle 기록={expected_feat_sha}, 실제 로드={actual_feat_sha}"
            )

        feature_schema_snapshot = (
            json.loads(feature_schema_spec.schema_file_path.read_text(encoding="utf-8"))
            if feature_schema_spec.schema_file_path and feature_schema_spec.schema_file_path.exists()
            else {
                "feature_schema_version": feat_schema_ver,
                "features": [
                    {
                        "feature_name": f.feature_name,
                        "source_field": f.source_field,
                        "dtype": f.dtype,
                        "operation": f.operation,
                        "parameters": f.parameters,
                        "missing_value_policy": f.missing_value_policy,
                    }
                    for f in feature_schema_spec.features
                ],
            }
        )

        # Load official label schema snapshot and verify checksum against bundle provenance
        try:
            label_schema_spec = getattr(self.label_schema_provider, "load_label_schema", getattr(self.label_schema_provider, "get_label_schema"))(label_schema_ver)
        except Exception as exc:
            raise TrainingContractError(f"Label Schema 로드 실패: {exc}") from exc

        actual_label_sha = label_schema_spec.compute_checksum()
        if actual_label_sha != expected_label_sha:
            raise FeatureDatasetIntegrityError(
                f"Label Schema SHA-256 불일치: Label Schema 기록={expected_label_sha}, 실제 로드={actual_label_sha}"
            )

        label_schema_snapshot = (
            json.loads(label_schema_spec.schema_file_path.read_text(encoding="utf-8"))
            if label_schema_spec.schema_file_path and label_schema_spec.schema_file_path.exists()
            else {
                "label_schema_version": label_schema_ver,
                "prediction_task": label_schema_spec.prediction_task,
                "prediction_horizon_hours": label_schema_spec.prediction_horizon_hours,
                "anchor": label_schema_spec.anchor,
                "exclusion_end": label_schema_spec.exclusion_end,
                "positive_window": label_schema_spec.positive_window,
                "active_failure_policy": label_schema_spec.active_failure_policy,
                "target_name": label_schema_spec.target_name,
            }
        )

        label_horizon = label_schema_snapshot.get("prediction_horizon_hours")
        if label_horizon != horizon_hours:
            raise TrainingContractError(
                f"Prediction horizon mismatch: Feature Bundle has {horizon_hours}h, but Label Schema has {label_horizon}h"
            )

        # 5. Deterministically derive history requirements from feature schema recipe
        history_requirement_snapshot = build_history_requirement_from_feature_schema(feature_schema_snapshot)

        # 6. Split dataset by asset and time using TrainingConfig ratios
        train_ratio = config_spec.split_ratio.get("train", 0.70)
        val_ratio = config_spec.split_ratio.get("validation", 0.15)
        test_ratio = config_spec.split_ratio.get("test", 0.15)

        splits = asset_time_split(
            features=bundle_data.features,
            labels=bundle_data.labels,
            row_metadata=bundle_data.row_metadata,
            train_ratio=train_ratio,
            val_ratio=val_ratio,
            test_ratio=test_ratio,
        )

        # 7. Determine models to train
        if target_model is not None:
            normalized_target = target_model.strip().lower()
            if normalized_target not in REGISTERED_MODELS:
                raise TrainingModelNotFoundError(
                    f"지원하지 않는 base_model입니다: '{target_model}'. 지원 목록: {list(REGISTERED_MODELS.keys())}"
                )
            models_to_train = [normalized_target]
        else:
            models_to_train = list(REGISTERED_MODELS.keys())

        results: list[ModelTrainingResult] = []

        for base_model in models_to_train:
            trainer_cls = REGISTERED_MODELS[base_model]
            trainer = trainer_cls()

            model_id = f"pdm-{base_model}"
            if req.model_version and req.model_version.strip():
                model_ver = req.model_version.strip()
            else:
                fp_content = f"{req.feature_dataset_version}:{config_spec.training_config_version}:{config_spec.sha256}:{bundle_data.feature_metadata_sha256}:{base_model}"
                fp_hash = hashlib.sha256(fp_content.encode("utf-8")).hexdigest()[:8]
                model_ver = f"{base_model}-fp{fp_hash}"

            stage_logger = {
                "request_id": req_id,
                "run_id": run_id,
                "base_model": base_model,
                "model_id": model_id,
                "model_version": model_ver,
            }

            try:
                configured_params = dict(config_spec.hyperparameters.get(base_model, {}))
                resolved_params = trainer.resolve_parameters(
                    configured=configured_params,
                    random_seed=config_spec.random_seed,
                )

                logger.info(f"[TrainingService] Training model {base_model} with resolved parameters: {resolved_params}...", extra=stage_logger)
                trained = trainer.train(
                    X_train=splits.X_train,
                    y_train=splits.y_train,
                    X_val=splits.X_val,
                    y_val=splits.y_val,
                    feature_names=bundle_data.feature_columns,
                    model_parameters=resolved_params,
                )

                metrics_payload = {
                    "metrics_schema_version": "pdm-metrics-v1",
                    "evaluation_dataset": {
                        "dataset_id": req.dataset_id,
                        "dataset_version": req.dataset_version,
                        "feature_dataset_version": req.feature_dataset_version,
                    },
                    "split_strategy": splits.summary["strategy"],
                    "split_summary": splits.summary,
                    "primary_metric": config_spec.primary_metric,
                    "validation_metrics": trained.metrics,
                    "feature_importance": trained.feature_importance,
                    "training_duration_seconds": trained.training_duration_seconds,
                }

                training_config_payload = {
                    "training_config_version": config_spec.training_config_version,
                    "training_config_sha256": config_spec.sha256,
                    "training_config_uri": config_spec.uri,
                    "base_model": base_model,
                    "algorithm": getattr(trainer, "algorithm", base_model),
                    "feature_count": len(bundle_data.feature_columns),
                    "random_seed": config_spec.random_seed,
                    "split_strategy": config_spec.split_strategy,
                    "split_ratio": config_spec.split_ratio,
                    "hyperparameters": config_spec.hyperparameters.get(base_model, {}),
                    "configured_parameters": configured_params,
                    "resolved_parameters": resolved_params,
                    "activation_policy": req.activation_policy,
                }

                provenance_payload = {
                    "run_id": run_id,
                    "request_id": req_id,
                    "dataset_id": req.dataset_id,
                    "dataset_version": req.dataset_version,
                    "feature_dataset_version": req.feature_dataset_version,
                    "feature_dataset_metadata_sha256": bundle_data.feature_metadata_sha256,
                    "training_config_version": config_spec.training_config_version,
                    "training_config_sha256": config_spec.sha256,
                    "training_config_uri": config_spec.uri,
                    "preprocessing_plan_id": prov.get("preprocessing_plan_id", ""),
                    "preprocessing_plan_version": prov.get("preprocessing_plan_version", ""),
                    "feature_schema_version": feat_schema_ver,
                    "feature_schema_sha256": prov.get("feature_schema_sha256", feature_schema_spec.compute_checksum()),
                    "label_schema_version": label_schema_ver,
                    "label_schema_sha256": prov.get("label_schema_sha256", label_schema_spec.compute_checksum()),
                    "prediction_horizon_hours": horizon_hours,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

                pub_result = self.artifact_publisher.publish_artifact(
                    model_id=model_id,
                    model_version=model_ver,
                    base_model=base_model,
                    model_obj=trained.model,
                    dataset_id=req.dataset_id,
                    dataset_version=req.dataset_version,
                    feature_dataset_version=req.feature_dataset_version,
                    feature_schema=feature_schema_snapshot,
                    label_schema=label_schema_snapshot,
                    history_requirement=history_requirement_snapshot,
                    metrics=metrics_payload,
                    training_config=training_config_payload,
                    provenance=provenance_payload,
                    activation_policy=req.activation_policy,
                )

                if pub_result.published and pub_result.latest_updated:
                    results.append(
                        ModelTrainingResult(
                            base_model=base_model,
                            model_id=model_id,
                            model_version=model_ver,
                            status="succeeded",
                            published=True,
                            latest_updated=True,
                            model_artifact_uri=pub_result.artifact_uri,
                            artifact_uri=pub_result.artifact_uri,
                            metrics_summary=trained.metrics,
                            latest_error_code=None,
                            latest_error_message=None,
                            activated=True,
                            activation_error_code=None,
                            error_code=None,
                        )
                    )
                    logger.info(f"[TrainingService] Model {base_model} succeeded: f1={trained.metrics.get('f1', 0.0):.4f}")
                elif pub_result.published and not pub_result.latest_updated:
                    logger.warning(
                        f"[TrainingService] Model {base_model} artifact published at {pub_result.artifact_uri} but pointer update failed: {pub_result.latest_error_code}"
                    )
                    if target_model is not None:
                        details_payload = [{
                            "published": True,
                            "model_artifact_uri": pub_result.artifact_uri,
                            "latest_updated": False,
                            "latest_error_code": pub_result.latest_error_code,
                        }]
                        if pub_result.latest_error_code == "MODEL_LATEST_UPDATE_IN_PROGRESS":
                            raise ModelActivationInProgressError(
                                f"Model Artifact '{model_id}/{model_ver}'가 발행되었으나 최신 포인터 갱신 락 획득에 실패했습니다: {pub_result.latest_error_message}",
                                details=details_payload,
                            )
                        elif pub_result.latest_error_code == "MODEL_LATEST_TARGET_INVALID":
                            raise ModelActivationTargetInvalidError(
                                f"Model Artifact '{model_id}/{model_ver}'가 발행되었으나 최신 포인터 대상 검증에 실패했습니다: {pub_result.latest_error_message}",
                                details=details_payload,
                            )
                        elif pub_result.latest_error_code == "MODEL_LATEST_VERIFY_FAILED":
                            raise ModelActivationVerifyError(
                                f"Model Artifact '{model_id}/{model_ver}'가 발행되었으나 최신 포인터 재검증에 실패했습니다: {pub_result.latest_error_message}",
                                details=details_payload,
                            )
                        else:
                            raise ModelActivationCommitError(
                                f"Model Artifact '{model_id}/{model_ver}'가 발행되었으나 최신 포인터 갱신에 실패했습니다: {pub_result.latest_error_message}",
                                details=details_payload,
                            )
                    results.append(
                        ModelTrainingResult(
                            base_model=base_model,
                            model_id=model_id,
                            model_version=model_ver,
                            status="failed",
                            published=True,
                            latest_updated=False,
                            model_artifact_uri=pub_result.artifact_uri,
                            artifact_uri=pub_result.artifact_uri,
                            metrics_summary=trained.metrics,
                            latest_error_code=pub_result.latest_error_code,
                            latest_error_message=pub_result.latest_error_message,
                            activated=False,
                            activation_error_code=pub_result.latest_error_code,
                            error_code=pub_result.latest_error_code,
                        )
                    )

            except Exception as exc:
                logger.exception(f"[TrainingService] Model {base_model} failed: {exc}", extra=stage_logger)
                # If training single model explicitly requested, raise the error directly
                if target_model is not None:
                    raise

                err_code = getattr(exc, "code", type(exc).__name__)

                # For full train, isolate error and mark model as failed
                results.append(
                    ModelTrainingResult(
                        base_model=base_model,
                        model_id=model_id,
                        model_version=model_ver,
                        status="failed",
                        published=False,
                        latest_updated=False,
                        model_artifact_uri=None,
                        artifact_uri=None,
                        metrics_summary=None,
                        latest_error_code=None,
                        latest_error_message=None,
                        activated=False,
                        activation_error_code=None,
                        error_code=err_code,
                    )
                )

        # 8. Compute overall response status
        succeeded_count = sum(1 for r in results if r.status == "succeeded")
        total_count = len(results)

        if succeeded_count == total_count:
            overall_status = "succeeded"
        elif succeeded_count > 0:
            overall_status = "partially_succeeded"
        else:
            overall_status = "failed"

        return TrainingResponse(
            request_id=req_id,
            run_id=run_id,
            status=overall_status,
            dataset_id=req.dataset_id,
            dataset_version=req.dataset_version,
            feature_dataset_version=req.feature_dataset_version,
            training_config_version=config_spec.training_config_version,
            results=results,
        )

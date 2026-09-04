"""Service for executing multi-model predictions against active Model Artifacts across equipment."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np

from systems.generator.generator_config import PATHS
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.model.publisher import ModelArtifactPublisher
from systems.generator.app.runtime_pipeline.pipeline_exception import (
    PipelineAssetIdColumnMissingError,
    PipelineModelArtifactInvalidError,
    PipelineModelPredictionFailedError,
    PipelinePredictionObservationAlignmentNotImplementedError,
)
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    ArtifactReference,
    InternalModelPredictionResult,
)
from systems.generator.app.runtime_pipeline.runtime_feature_service import RuntimeFeatureBundle

logger = logging.getLogger(__name__)

REGISTERED_BASE_MODELS = ["lightgbm", "xgboost", "random_forest"]


def _fallback_history_requirement_version(model_id: str, model_version: str) -> str:
    """Return a stable history-contract version for legacy runtime artifacts.

    The Mac mini runtime model artifacts published before the generator strict
    contract included feature/label versions and history requirement checksum,
    but some omitted the textual history_requirement_version.  Preserve the
    strict checksum validation downstream while filling only that missing version
    label from the model family.
    """
    identity = f"{model_id} {model_version}".lower()
    if "cnc" in identity:
        return "cnc-history-requirement-v1"
    if "compressor" in identity:
        return "compressor-history-requirement-v1"
    return "pdm-history-v1"


@dataclass
class LoadedModelArtifact:
    model_id: str
    model_version: str
    model: Any
    manifest: dict[str, Any]
    feature_schema: dict[str, Any]
    label_schema: dict[str, Any]
    history_requirement: dict[str, Any]
    metrics: dict[str, Any]
    artifact_dir: Path
    artifact_ref: ArtifactReference
    manifest_checksum: str


class PredictionService:
    """Loads active Model Artifacts and executes inference from published Runtime Feature references per equipment."""

    def __init__(
        self,
        models_store_dir: Optional[Path] = None,
        publisher: Optional[ModelArtifactPublisher] = None,
    ) -> None:
        if models_store_dir is None:
            self.models_store = PATHS.models_store
            self.artifacts_dir = self.models_store / "artifacts"
        else:
            base_p = Path(models_store_dir)
            if base_p.name == "artifacts":
                self.artifacts_dir = base_p
                self.models_store = base_p.parent
            else:
                self.models_store = base_p
                self.artifacts_dir = base_p / "artifacts"

        self.publisher = publisher or ModelArtifactPublisher(self.artifacts_dir)

    def resolve_model_id(self, base_or_id: str) -> str:
        clean = base_or_id.strip()
        if clean in {"lightgbm", "xgboost", "random_forest"}:
            return f"pdm-{clean}"
        return clean

    def load_active_artifact(
        self,
        base_or_id: str,
        target_version: Optional[str] = None,
    ) -> LoadedModelArtifact:
        """Resolve artifact for explicit version or latest.json, strictly verify all 6 files and checksums, and load model."""
        model_id = self.resolve_model_id(base_or_id)
        if target_version:
            model_version = target_version
        else:
            latest_file = self.artifacts_dir / model_id / "latest.json"
            if not latest_file.exists():
                raise PipelineModelArtifactInvalidError(
                    f"모델 '{model_id}'의 latest.json 포인터가 존재하지 않습니다.",
                    details=[{"model_id": model_id, "pointer_path": str(latest_file)}],
                    retryable=False,
                )

            try:
                with open(latest_file, "r", encoding="utf-8") as f:
                    pointer_data = json.load(f)
            except Exception as exc:
                raise PipelineModelArtifactInvalidError(
                    f"모델 '{model_id}'의 latest.json 파싱 실패: {exc}",
                    details=[{"model_id": model_id, "error": str(exc)}],
                    retryable=False,
                ) from exc

            model_version = pointer_data.get("model_version") or pointer_data.get("active_version")
            if not model_version:
                raise PipelineModelArtifactInvalidError(
                    f"latest.json에 유효한 model_version이 없습니다 ({model_id}).",
                    retryable=False,
                )

        target_artifact_dir = self.artifacts_dir / model_id / model_version
        from systems.generator.model.publisher import (
            ModelArtifactContractValidationError,
            validate_model_artifact,
        )
        try:
            validated = validate_model_artifact(
                artifact_dir=target_artifact_dir,
                expected_model_id=model_id,
                expected_model_version=model_version,
                load_model=True,
                artifacts_root=self.artifacts_dir,
            )
        except ModelArtifactContractValidationError as exc:
            raise PipelineModelArtifactInvalidError(
                f"아티팩트 검증 및 로드 실패 ({model_id}/{model_version}): {exc.message}",
                details=[{"model_id": model_id, "model_version": model_version, "reason": exc.reason, "error": exc.message}],
                retryable=False,
            ) from exc

        model_obj = validated.model
        manifest_data = validated.manifest
        feat_schema = validated.feature_schema
        lbl_schema = validated.label_schema
        hist_req = validated.history_requirement
        metrics = validated.metrics
        manifest_sha = validated.manifest_checksum

        artifact_ref = ArtifactReference(
            uri=str(target_artifact_dir).replace("\\", "/"),
            sha256=manifest_sha,
            role="model_artifact",
            size_bytes=None,
        )

        return LoadedModelArtifact(
            model_id=model_id,
            model_version=model_version,
            model=model_obj,
            manifest=manifest_data,
            feature_schema=feat_schema,
            label_schema=lbl_schema,
            history_requirement=hist_req,
            metrics=metrics,
            artifact_dir=target_artifact_dir,
            artifact_ref=artifact_ref,
            manifest_checksum=manifest_sha,
        )

    def predict_for_models(
        self,
        base_models: list[str],
        model_feature_refs: dict[str, ArtifactReference],
        model_feature_bundles: Optional[dict[str, RuntimeFeatureBundle]] = None,
        model_feature_errors: Optional[dict[str, Any]] = None,
        asset_ids: Optional[list[str]] = None,
        active_model_set: Optional[ActiveModelSet] = None,
    ) -> list[InternalModelPredictionResult]:
        """Run pure inference for the applicable models pinned by the Active Model Set."""
        from systems.generator.app.runtime_pipeline.pipeline_schema import ActiveModelSet
        results: list[InternalModelPredictionResult] = []

        # Resolve all known equipment IDs strictly
        known_assets: set[str] = set(asset_ids or [])
        if model_feature_bundles:
            for b in model_feature_bundles.values():
                if b and b.row_metadata:
                    for rm in b.row_metadata:
                        known_assets.add(rm.asset_id)

        model_items: list[tuple[str, Optional[str], bool]] = []
        if active_model_set:
            model_set_id = active_model_set.model_set_id
            model_set_version = active_model_set.model_set_version
            for bm in base_models:
                cfg = active_model_set.models.get(bm)
                if cfg is None:
                    resolved = self.resolve_model_id(bm)
                    for configured_name, candidate in active_model_set.models.items():
                        if self.resolve_model_id(configured_name) == resolved:
                            cfg = candidate
                            break
                if cfg is None:
                    raise PipelineModelPredictionFailedError(
                        f"요청된 모델 '{bm}'이 Active Model Set에 포함되어 있지 않습니다.",
                        details=[
                            {
                                "base_model": bm,
                                "model_set_id": model_set_id,
                                "model_set_version": model_set_version,
                                "active_models": sorted(active_model_set.models),
                            }
                        ],
                        retryable=False,
                    )
                model_items.append((bm, cfg.model_version, cfg.required))
        else:
            raise PipelineModelPredictionFailedError(
                "Runtime Prediction requires an explicitly pinned Active Model Set.",
                details=[{"base_models": list(base_models)}],
                retryable=False,
            )

        for base_model, target_ver, is_required in model_items:
            model_id = self.resolve_model_id(base_model)

            # Load active artifact
            try:
                artifact = self.load_active_artifact(base_model, target_version=target_ver)
            except Exception as exc:
                err_code = getattr(exc, "code", "PIPELINE_MODEL_ARTIFACT_INVALID")
                logger.warning(f"[PredictionService] Failed to load active artifact for '{model_id}': {exc}")
                if is_required:
                    raise PipelineModelPredictionFailedError(
                        f"필수 모델 '{model_id}' ({target_ver or 'latest'}) 로드 실패: {exc}",
                        details=[{"model_id": model_id, "error": str(exc)}],
                        retryable=False,
                    ) from exc
                for target_asset in known_assets:
                    results.append(
                        InternalModelPredictionResult(
                            asset_id=target_asset,
                            model_id=model_id,
                            model_version=target_ver,
                            status="failed",
                            observed_at="",
                            score_type="positive_class_probability",
                            score_source=None,
                            score=None,
                            artifact_ref=None,
                            feature_ref=None,
                            manifest_checksum=None,
                            feature_schema_version=None,
                            label_schema_version=None,
                            history_requirement_version=None,
                            model_set_id=model_set_id,
                            model_set_version=model_set_version,
                            error_code=err_code,
                            error_message=str(exc),
                        )
                    )
                continue

            feat_schema_ver = (
                artifact.manifest.get("feature_schema_version")
                or artifact.feature_schema.get("feature_schema_version")
                or artifact.feature_schema.get("schema_version")
            )
            lbl_schema_ver = (
                artifact.manifest.get("label_schema_version")
                or artifact.label_schema.get("label_schema_version")
                or artifact.label_schema.get("schema_version")
            )
            hist_req_ver = (
                artifact.manifest.get("history_requirement_version")
                or artifact.history_requirement.get("history_requirement_version")
                or artifact.history_requirement.get("version")
                or _fallback_history_requirement_version(model_id, artifact.model_version)
            )

            missing_versions = [
                name
                for name, value in (
                    ("feature_schema_version", feat_schema_ver),
                    ("label_schema_version", lbl_schema_ver),
                    ("history_requirement_version", hist_req_ver),
                )
                if not value or not str(value).strip()
            ]
            if missing_versions:
                raise PipelineModelPredictionFailedError(
                    f"모델 '{model_id}' Artifact에 필수 계약 버전이 누락되었습니다: {', '.join(missing_versions)}",
                    details=[{"model_id": model_id, "missing_fields": missing_versions}],
                    retryable=False,
                )

            feature_ref = model_feature_refs.get(base_model)
            bundle = (model_feature_bundles or {}).get(base_model)

            if feature_ref is None:
                err_info = (model_feature_errors or {}).get(base_model)
                err_code = getattr(err_info, "code", "PIPELINE_RUNTIME_FEATURE_FAILED") if err_info else "PIPELINE_RUNTIME_FEATURE_FAILED"
                err_msg = str(err_info) if err_info else f"모델 '{model_id}'에 해당하는 Runtime Feature가 생성되지 않았습니다."
                if is_required:
                    raise PipelineModelPredictionFailedError(
                        f"필수 모델 '{model_id}'의 Feature 생성 실패: {err_msg}",
                        details=[{"model_id": model_id, "error": err_msg}],
                        retryable=False,
                    )
                for target_asset in known_assets:
                    results.append(
                        InternalModelPredictionResult(
                            asset_id=target_asset,
                            model_id=model_id,
                            model_version=artifact.model_version,
                            status="failed",
                            observed_at="",
                            score_type="positive_class_probability",
                            score_source=None,
                            score=None,
                            artifact_ref=artifact.artifact_ref,
                            feature_ref=None,
                            manifest_checksum=artifact.manifest_checksum,
                            feature_schema_version=feat_schema_ver,
                            label_schema_version=lbl_schema_ver,
                            history_requirement_version=hist_req_ver,
                            model_set_id=model_set_id,
                            model_set_version=model_set_version,
                            error_code=err_code,
                            error_message=err_msg,
                        )
                    )
                continue

            # Load feature matrix from published npy file
            try:
                feat_path = Path(feature_ref.uri)
                if not feat_path.exists():
                    raise FileNotFoundError(f"Runtime feature file not found: {feat_path}")
                features_matrix = np.load(feat_path, allow_pickle=False)
                if features_matrix.size == 0:
                    raise ValueError("Feature matrix is empty")
            except Exception as exc:
                logger.warning(f"[PredictionService] Failed to load feature npy for '{model_id}': {exc}")
                if is_required:
                    raise PipelineModelPredictionFailedError(
                        f"필수 모델 '{model_id}'의 Feature npy 로드 실패: {exc}",
                        details=[{"model_id": model_id, "error": str(exc)}],
                        retryable=False,
                    ) from exc
                for target_asset in known_assets:
                    results.append(
                        InternalModelPredictionResult(
                            asset_id=target_asset,
                            model_id=model_id,
                            model_version=artifact.model_version,
                            status="failed",
                            observed_at="",
                            score_type="positive_class_probability",
                            score_source=None,
                            score=None,
                            artifact_ref=artifact.artifact_ref,
                            feature_ref=feature_ref,
                            manifest_checksum=artifact.manifest_checksum,
                            feature_schema_version=feat_schema_ver,
                            label_schema_version=lbl_schema_ver,
                            history_requirement_version=hist_req_ver,
                            model_set_id=model_set_id,
                            model_set_version=model_set_version,
                            error_code="PIPELINE_RUNTIME_FEATURE_FAILED",
                            error_message=f"Runtime feature npy 로드 실패: {exc}",
                        )
                    )
                continue

            # Map row metadata to equipments
            asset_latest_row: dict[str, int] = {}
            row_meta_by_index: dict[int, Any] = {}
            if bundle and bundle.row_metadata:
                for row_meta in bundle.row_metadata:
                    asset_latest_row[row_meta.asset_id] = row_meta.row_index
                    row_meta_by_index[row_meta.row_index] = row_meta

            # If bundle metadata is missing, fail-closed
            if not asset_latest_row:
                if is_required:
                    raise PipelineModelPredictionFailedError(
                        f"필수 모델 '{model_id}'의 Feature 메타데이터 매핑이 누락되었습니다.",
                        details=[{"model_id": model_id}],
                        retryable=False,
                    )
                for target_asset in known_assets:
                    results.append(
                        InternalModelPredictionResult(
                            asset_id=target_asset,
                            model_id=model_id,
                            model_version=artifact.model_version,
                            status="failed",
                            observed_at="",
                            score_type="positive_class_probability",
                            score_source=None,
                            score=None,
                            artifact_ref=artifact.artifact_ref,
                            feature_ref=feature_ref,
                            manifest_checksum=artifact.manifest_checksum,
                            feature_schema_version=feat_schema_ver,
                            label_schema_version=lbl_schema_ver,
                            history_requirement_version=hist_req_ver,
                            model_set_id=model_set_id,
                            model_set_version=model_set_version,
                            error_code="PIPELINE_FEATURE_METADATA_ALIGNMENT_ERROR",
                            error_message="Feature 메타데이터 매핑이 누락되었습니다.",
                        )
                    )
                continue

            # Iterate over each equipment
            for asset_id, latest_idx in asset_latest_row.items():
                target_metadata = row_meta_by_index.get(latest_idx)
                if target_metadata is None or not target_metadata.observed_at:
                    raise PipelinePredictionObservationAlignmentNotImplementedError(
                        f"설비 '{asset_id}'의 최신 예측 행(index={latest_idx})에 대응하는 row metadata 또는 observed_at이 없습니다.",
                        details=[{"model_id": model_id, "asset_id": asset_id, "row_index": latest_idx}],
                        retryable=False,
                    )
                observed_at_val = target_metadata.observed_at

                # Check history sufficiency for this asset
                history_status = (bundle.asset_history_status or {}).get(asset_id) if bundle else None
                if history_status and not history_status.get("ready", True):
                    actual_count = history_status.get("count", 0)
                    min_req = history_status.get("minimum_history_rows", 1)
                    results.append(
                        InternalModelPredictionResult(
                            asset_id=asset_id,
                            model_id=model_id,
                            model_version=artifact.model_version,
                            status="unknown",
                            observed_at=observed_at_val,
                            score_type="positive_class_probability",
                            score_source=None,
                            score=None,
                            artifact_ref=artifact.artifact_ref,
                            feature_ref=feature_ref,
                            manifest_checksum=artifact.manifest_checksum,
                            feature_schema_version=feat_schema_ver,
                            label_schema_version=lbl_schema_ver,
                            history_requirement_version=hist_req_ver,
                            model_set_id=model_set_id,
                            model_set_version=model_set_version,
                            error_code="PIPELINE_HISTORY_INSUFFICIENT",
                            error_message=f"설비 '{asset_id}'의 관측 이력 부족 (요구치={min_req}, 실제={actual_count})",
                        )
                    )
                    continue

                # Extract latest feature vector for this equipment
                target_features = features_matrix[latest_idx : latest_idx + 1]

                # Perform inference
                try:
                    model_obj = artifact.model
                    if hasattr(model_obj, "predict_proba"):
                        probs = model_obj.predict_proba(target_features)
                        if probs.ndim == 2 and probs.shape[1] >= 2:
                            score_val = float(probs[0, 1])
                        else:
                            score_val = float(probs[0, 0])
                        score_source_val = "predict_proba"
                    elif hasattr(model_obj, "decision_function"):
                        df_val = float(model_obj.decision_function(target_features)[0])
                        score_val = float(1.0 / (1.0 + np.exp(-df_val)))
                        score_source_val = "decision_function_compat"
                    elif hasattr(model_obj, "predict"):
                        preds = model_obj.predict(target_features)
                        score_val = float(preds[0])
                        score_source_val = "predict_compat"
                    else:
                        raise PipelineModelPredictionFailedError(f"Model object has no predict method: {type(model_obj)}")

                    # Validate finite numeric value and probability bounds
                    if math.isnan(score_val) or math.isinf(score_val):
                        raise PipelineModelPredictionFailedError(
                            f"Model '{model_id}' returned non-finite score {score_val}"
                        )
                    if not (0.0 <= score_val <= 1.0):
                        raise PipelineModelPredictionFailedError(
                            f"Model '{model_id}' score {score_val} out of bounds [0.0, 1.0]"
                        )

                    results.append(
                        InternalModelPredictionResult(
                            asset_id=asset_id,
                            model_id=model_id,
                            model_version=artifact.model_version,
                            status="succeeded",
                            observed_at=observed_at_val,
                            score_type="positive_class_probability",
                            score_source=score_source_val,
                            score=score_val,
                            artifact_ref=artifact.artifact_ref,
                            feature_ref=feature_ref,
                            manifest_checksum=artifact.manifest_checksum,
                            feature_schema_version=feat_schema_ver,
                            label_schema_version=lbl_schema_ver,
                            history_requirement_version=hist_req_ver,
                            model_set_id=model_set_id,
                            model_set_version=model_set_version,
                            error_code=None,
                            error_message=None,
                        )
                    )
                    logger.info(
                        f"[PredictionService] Equipment '{asset_id}', Model '{model_id}' ({artifact.model_version}): "
                        f"score={score_val:.4f} (source={score_source_val}, observed_at={observed_at_val})"
                    )
                except PipelineModelPredictionFailedError:
                    raise
                except Exception as exc:
                    logger.warning(f"[PredictionService] Model '{model_id}' prediction execution failed for asset '{asset_id}': {exc}")
                    if is_required:
                        raise PipelineModelPredictionFailedError(
                            f"필수 모델 '{model_id}'의 추론 실패: {exc}",
                            details=[
                                {
                                    "asset_id": asset_id,
                                    "model_id": model_id,
                                    "model_version": artifact.model_version,
                                    "observed_at": observed_at_val,
                                    "error": str(exc),
                                }
                            ],
                            retryable=False,
                        ) from exc
                    else:
                        results.append(
                            InternalModelPredictionResult(
                                asset_id=asset_id,
                                model_id=model_id,
                                model_version=artifact.model_version,
                                status="failed",
                                observed_at=observed_at_val,
                                score_type="positive_class_probability",
                                score_source=None,
                                score=None,
                                artifact_ref=artifact.artifact_ref,
                                feature_ref=feature_ref,
                                manifest_checksum=artifact.manifest_checksum,
                                feature_schema_version=feat_schema_ver,
                                label_schema_version=lbl_schema_ver,
                                history_requirement_version=hist_req_ver,
                                model_set_id=model_set_id,
                                model_set_version=model_set_version,
                                error_code="PIPELINE_MODEL_PREDICTION_FAILED",
                                error_message=str(exc),
                            )
                        )

        return results

"""Pipeline orchestration service executing Preprocessing, Runtime Feature, Prediction, Batch Building, and Delivery."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from datetime import datetime, timezone

from systems.generator.generator_config import (
    PROJECT_ROOT,
    PATHS,
    validate_pipeline_source_uri,
)
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.app.preprocessing.preprocessing_repository import (
    compute_source_schema_fingerprint,
)
from systems.generator.app.preprocessing.preprocessing_service import PreprocessingService
from systems.generator.app.runtime_pipeline.prediction_batch_service import (
    EquipmentModelBatch,
    PredictionBatchService,
    PredictionBatchSummary,
    build_external_prediction_batch,
    sort_prediction_result_items,
    to_external_result_item,
    validate_external_results_array,
)
from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
    PredictionDeliveryService,
)
from systems.generator.app.runtime_pipeline.pipeline_exception import (
    PipelineAssetIdColumnMissingError,
    PipelineAssetIdMissingError,
    PipelineAssetIdValueMissingError,
    PipelineCheckpointChecksumMismatchError,
    PipelineCheckpointIncompatibleError,
    PipelineCheckpointInvalidError,
    PipelineCheckpointOutputMissingError,
    PipelineInputChecksumMismatchError,
    PipelineInputNotFoundError,
    PipelineIntermediateCleanupFailedError,
    PipelineMappingNotImplementedError,
    PipelineModelArtifactInvalidError,
    PipelineModelPredictionFailedError,
    PipelineModelSetChangedError,
    PipelineModelSnapshotArtifactMissingError,
    PipelineModelSnapshotChecksumMismatchError,
    PipelineModelSnapshotIncompatibleError,
    PipelineNoActiveModelError,
    PipelineOutboxEventConflictError,
    PipelineOutboxPayloadChecksumMismatchError,
    PipelinePredictionObservationAlignmentNotImplementedError,
    PipelinePreprocessingFailedError,
    PipelineResumeFailedError,
    PipelineResumeNotAllowedError,
    PipelineRuntimeFeatureFailedError,
    PipelineRuntimePredictionDisabledError,
    PipelineSourceChecksumChangedError,
    PipelineSourceFileNotStableError,
    PipelineTimestampInvalidError,
    PipelineModelSetMembershipChangeNotImplementedError,
)
from systems.generator.app.runtime_pipeline.active_model_set_service import (
    ActiveModelSetService,
)
from systems.generator.app.runtime_pipeline.pipeline_repository import (
    PipelineRepository,
)
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    ActiveModelSet,
    ActiveModelSetSnapshot,
    ActiveModelSnapshotItem,
    ArtifactReference,
    InternalModelPredictionResult,
    ModelSnapshotEntry,
    PipelineCheckpoint,
    PipelineQueueItem,
    PipelineRunState,
    PredictionDeliveryEventState,
    PredictionResultBatchPayload,
    PredictionResultItem,
    PredictionResultLineage,
    PredictionResultProducer,
    PredictionResultSourceRef,
    RuntimeInputIdentity,
    RuntimeSourceContext,
    SourceLineage,
    compute_model_set_payload_sha256,
    compute_source_identity,
    now_utc_iso,
)
from systems.generator.app.runtime_pipeline.pipeline_state import (
    PipelineStateManager,
)
from systems.generator.app.runtime_pipeline.prediction_service import (
    LoadedModelArtifact,
    PredictionService,
    REGISTERED_BASE_MODELS,
)
from systems.generator.app.runtime_pipeline.runtime_feature_service import (
    RuntimeFeatureBundle,
    RuntimeFeatureService,
)

logger = logging.getLogger(__name__)


def _compute_canonical_dict_sha256(data_dict: dict[str, Any]) -> str:
    """Compute SHA-256 checksum of compact canonical JSON serialization."""
    c_json = json.dumps(data_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(c_json.encode("utf-8")).hexdigest()


class PipelineService:
    """Orchestrates individual pipeline run execution across 5 independent stages with checkpoint resumption."""

    def __init__(
        self,
        repository: Optional[PipelineRepository] = None,
        preprocessing_service: Optional[PreprocessingService] = None,
        runtime_feature_service: Optional[RuntimeFeatureService] = None,
        prediction_service: Optional[PredictionService] = None,
        prediction_batch_service: Optional[PredictionBatchService] = None,
        prediction_delivery_service: Optional[PredictionDeliveryService] = None,
        active_model_set_service: Optional[ActiveModelSetService] = None,
    ) -> None:
        self.repository = repository or PipelineRepository()
        self.preprocessing_service = preprocessing_service or PreprocessingService()
        self.runtime_feature_service = runtime_feature_service or RuntimeFeatureService()
        self.prediction_service = prediction_service or PredictionService()
        self.prediction_batch_service = prediction_batch_service or PredictionBatchService()
        self.prediction_delivery_service = prediction_delivery_service or PredictionDeliveryService()
        self.active_model_set_service = active_model_set_service or ActiveModelSetService(models_store_dir=self.prediction_service.models_store)

    @staticmethod
    def _filter_observations_for_artifact(
        observations: pd.DataFrame,
        artifact: LoadedModelArtifact,
    ) -> pd.DataFrame:
        """Return only observations owned by the artifact's declared family.

        Runtime snapshots may contain CNC and compressor observations together.  A
        family-specific artifact must never see the other family's sparse columns,
        because doing so turns a valid mixed snapshot into NaN feature input.  Older
        generic artifacts without an ``observation_family`` declaration retain the
        previous all-row behaviour.
        """
        compatibility = artifact.manifest.get("compatibility") or {}
        family = str(compatibility.get("observation_family") or "").strip().lower()
        if not family:
            return observations

        if "asset_type" not in observations.columns:
            raise PipelineRuntimeFeatureFailedError(
                "설비군별 Model Artifact를 실행하려면 입력에 asset_type이 필요합니다.",
                details=[{"model_id": artifact.model_id, "observation_family": family}],
                retryable=False,
            )

        aliases = {
            "cnc": {"cnc", "cnc_machine"},
            "compressor": {"compressor", "air_compressor"},
        }
        accepted = aliases.get(family, {family})
        normalized = observations["asset_type"].astype("string").str.strip().str.lower()
        return observations.loc[normalized.isin(accepted)].copy()

    def get_logical_source_uri(self, source_path: Path) -> str:
        """Convert filesystem path to logical relative URI without exposing local drives or absolute paths."""
        try:
            p = source_path.resolve()
            for root in (PROJECT_ROOT, PATHS.data_incoming, PATHS.data_preprocessed, PATHS.data_dir, getattr(PATHS, "observations_root", None)):
                if root is None:
                    continue
                try:
                    rel = p.relative_to(root.resolve())
                    if root.resolve() == PATHS.data_dir.resolve():
                        normalized_rel = str(rel).replace("\\", "/")
                        return f"data/{normalized_rel}"
                    return str(rel).replace("\\", "/")
                except ValueError:
                    pass
        except Exception:
            pass
        return f"data/incoming/{source_path.name}"

    def _load_source_df(self, source_path: Path) -> pd.DataFrame:
        """Parse source observation protocol file (.jsonl or .csv)."""
        if not source_path.exists() or not source_path.is_file():
            raise PipelineInputNotFoundError(
                f"입력 소스 파일을 찾을 수 없습니다: {source_path}",
                details=[{"source_path": str(source_path)}],
                retryable=False,
            )

        if source_path.suffix.lower() == ".jsonl":
            records = []
            with open(source_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        records.append(json.loads(stripped))
            if not records:
                raise PipelineInputNotFoundError(
                    f"입력 jsonl 파일이 비어 있습니다: {source_path}",
                    retryable=False,
                )
            return pd.DataFrame(records)
        elif source_path.suffix.lower() == ".csv":
            df = pd.read_csv(source_path)
            if df.empty:
                raise PipelineInputNotFoundError(
                    f"입력 csv 파일이 비어 있습니다: {source_path}",
                    retryable=False,
                )
            return df
        else:
            raise PipelineInputNotFoundError(
                f"지원하지 않는 입력 파일 형식입니다: {source_path.suffix}",
                retryable=False,
            )

    def _publish_preprocessed_dataset(
        self,
        run_id: str,
        preprocessed_df: pd.DataFrame,
    ) -> ArtifactReference:
        """Atomically persist preprocessed dataset to disk and return validated ArtifactReference."""
        datasets_dir = PATHS.data_preprocessed / "pipeline_datasets" / run_id
        datasets_dir.mkdir(parents=True, exist_ok=True)
        dest_csv = datasets_dir / "observations.csv"
        temp_csv = datasets_dir / f".tmp_{uuid.uuid4().hex}_observations.csv"

        try:
            preprocessed_df.to_csv(temp_csv, index=False, encoding="utf-8")
            temp_csv.replace(dest_csv)
        except Exception as exc:
            if temp_csv.exists():
                try:
                    temp_csv.unlink()
                except Exception:
                    pass
            raise PipelinePreprocessingFailedError(
                f"전처리 데이터셋 파일 저장 실패: {exc}",
                retryable=False,
            ) from exc

        sha256 = compute_file_sha256(dest_csv)
        size_bytes = dest_csv.stat().st_size
        return ArtifactReference(
            uri=str(dest_csv).replace("\\", "/"),
            sha256=sha256,
            role="preprocessed_dataset",
            size_bytes=size_bytes,
        )

    def _validate_checkpoint_output_ref(self, ref: ArtifactReference) -> bool:
        """Verify on-disk existence and SHA-256 integrity for a stage output reference."""
        p = Path(ref.uri)
        if not p.is_file():
            if not p.is_absolute():
                p_str = ref.uri.replace("\\", "/")
                rel_p = p_str[len("data_preprocessed/"):] if p_str.startswith("data_preprocessed/") else p_str
                candidates = [
                    (PATHS.data_preprocessed / rel_p).resolve(),
                    (self.repository.base_dir / rel_p).resolve(),
                    (self.repository.base_dir / p).resolve(),
                    (PROJECT_ROOT / p).resolve(),
                ]
                try:
                    candidates.append((PATHS.models_store.parent / p).resolve())
                except Exception:
                    pass
                try:
                    candidates.append((PATHS.models_store / p).resolve())
                except Exception:
                    pass
                try:
                    candidates.append((PATHS.data_preprocessed.parent / p).resolve())
                except Exception:
                    pass
                try:
                    candidates.append((PATHS.data_preprocessed / p).resolve())
                except Exception:
                    pass
                try:
                    candidates.append((self.preprocessing_service.repository.base_dir / p).resolve())
                except Exception:
                    pass

                found = False
                for c in candidates:
                    if c.is_file():
                        p = c
                        found = True
                        break
                if not found:
                    return False
            else:
                return False
        try:
            actual_sha = compute_file_sha256(p)
            return actual_sha == ref.sha256
        except Exception:
            return False

    def _build_model_snapshot(
        self,
        base_models: list[str],
        active_model_set: Optional[ActiveModelSet] = None,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[dict[str, dict[str, Any]], dict[str, LoadedModelArtifact]]:
        """Construct Model Snapshot dictionary for active models and return loaded artifacts."""
        snapshot: dict[str, dict[str, Any]] = {}
        artifacts: dict[str, LoadedModelArtifact] = {}

        model_items: list[tuple[str, Optional[str]]] = []
        if active_model_set and active_model_set.models:
            for bm, cfg in active_model_set.models.items():
                model_items.append((bm, cfg.model_version))
        else:
            for bm in base_models:
                model_items.append((bm, None))

        for bm, target_ver in model_items:
            model_id = self.prediction_service.resolve_model_id(bm)
            try:
                art = self.prediction_service.load_active_artifact(bm, target_version=target_ver)
            except TypeError:
                art = self.prediction_service.load_active_artifact(bm)
            artifacts[bm] = art

            manifest_sha = art.manifest_checksum

            f_schema_ver = (art.feature_schema or {}).get("feature_schema_version", "v1")
            f_schema_sha = _compute_canonical_dict_sha256(art.feature_schema or {})
            h_req_ver = (art.history_requirement or {}).get("history_requirement_version", "v1")
            h_req_sha = _compute_canonical_dict_sha256(art.history_requirement or {})
            l_schema_ver = (art.label_schema or {}).get("label_schema_version", getattr(art, "label_schema_version", "1.0.0") if hasattr(art, "label_schema_version") else "1.0.0")
            l_schema_sha = _compute_canonical_dict_sha256(art.label_schema or {"model_id": model_id, "manifest_checksum": manifest_sha})
            selected_threshold = (art.manifest.get("training_config") or {}).get("selected_threshold")

            snapshot[model_id] = {
                "model_id": model_id,
                "model_version": art.model_version,
                "manifest_sha256": manifest_sha,
                "selected_threshold": selected_threshold,
                "feature_schema_version": f_schema_ver,
                "feature_schema_sha256": f_schema_sha,
                "history_requirement_version": h_req_ver,
                "history_requirement_sha256": h_req_sha,
                "label_schema_version": l_schema_ver,
                "label_schema_sha256": l_schema_sha,
            }
        return snapshot, artifacts

    def execute_queue_item(self, item: PipelineQueueItem) -> PipelineRunState:
        """Execute complete 5-stage pipeline lifecycle for a claimed queue item with checkpoint resumption."""
        # 0. Check Runtime Prediction Enabled Feature Flag
        if not PATHS.runtime_prediction_enabled:
            logger.warning(
                "[PipelineService] Generator Runtime Prediction is disabled (GENERATOR_RUNTIME_PREDICTION_ENABLED=false). "
                "Rejecting queue item execution."
            )
            raise PipelineRuntimePredictionDisabledError(
                "Runtime Prediction Pipeline이 비활성화되어 있습니다. (GENERATOR_RUNTIME_PREDICTION_ENABLED=false)",
                retryable=False,
            )

        # 1. Path, File Existence and Stability Validation
        source_path = validate_pipeline_source_uri(item.source_uri)
        if not source_path.exists() or not source_path.is_file():
            raise PipelineInputNotFoundError(
                f"입력 소스 파일을 찾을 수 없습니다: {source_path}",
                details=[{"source_path": str(source_path)}],
                retryable=False,
            )

        actual_size = source_path.stat().st_size
        if item.size_bytes is not None and actual_size != item.size_bytes:
            raise PipelineSourceFileNotStableError(
                f"소스 파일 크기가 변경되었습니다 (작성 중 또는 불안정 상태): 등록 시={item.size_bytes}B, 현재={actual_size}B",
                details=[{"registered_size": item.size_bytes, "current_size": actual_size}],
                retryable=True,
            )

        actual_sha = compute_file_sha256(source_path)
        if actual_sha != item.source_checksum:
            raise PipelineSourceChecksumChangedError(
                f"소스 파일 체크섬이 변경되었습니다: 등록 시={item.source_checksum}, 현재={actual_sha}",
                details=[{"expected": item.source_checksum, "actual": actual_sha}],
                retryable=True,
            )

        contract_ver = item.pipeline_contract_version
        if item.source_uri and not (item.source_uri.startswith("/") or ":" in item.source_uri[:2]):
            logical_source_uri = item.source_uri
        else:
            logical_source_uri = self.get_logical_source_uri(source_path)

        runtime_source_context = RuntimeSourceContext(
            source_uri=logical_source_uri,
            source_checksum=actual_sha,
            source_kind=item.source_kind,
            source_contract_version=item.source_contract_version,
            source_schema_version=item.source_schema_version,
            pipeline_contract_version=contract_ver,
            lineage=item.lineage,
        )

        runtime_input = RuntimeInputIdentity(
            dataset_id=item.dataset_id,
            dataset_version=item.dataset_version,
            source=runtime_source_context,
        )

        source_identity = item.source_identity or compute_source_identity(
            source_checksum=actual_sha,
            dataset_id=runtime_input.dataset_id,
            dataset_version=runtime_input.dataset_version,
            pipeline_contract_version=runtime_input.source.pipeline_contract_version,
            source_contract_version=runtime_input.source.source_contract_version,
            source_schema_version=runtime_input.source.source_schema_version,
            source_kind=runtime_input.source.source_kind,
            lineage=runtime_input.source.lineage,
        )

        # Load active model set pointer
        active_model_set = self.active_model_set_service.load_active_model_set()
        active_model_names = tuple(active_model_set.models.keys())

        # Pin active base models for this run
        current_snapshot, model_artifacts = self._build_model_snapshot(list(active_model_names), active_model_set=active_model_set)
        if not model_artifacts:
            raise PipelineNoActiveModelError(
                "활성화된 머신러닝 모델 아티팩트가 0개입니다.",
                retryable=False,
            )

        active_snapshot_items = [
            ActiveModelSnapshotItem(
                model_id=self.prediction_service.resolve_model_id(bm),
                model_version=current_snapshot[self.prediction_service.resolve_model_id(bm)]["model_version"],
                required=active_model_set.models[bm].required if bm in active_model_set.models else True,
                model_artifact_manifest_sha256=current_snapshot[self.prediction_service.resolve_model_id(bm)]["manifest_sha256"],
                selected_threshold=current_snapshot[self.prediction_service.resolve_model_id(bm)].get("selected_threshold"),
            )
            for bm in active_model_names
        ]
        active_model_set_snapshot = ActiveModelSetSnapshot(
            model_set_id=active_model_set.model_set_id,
            model_set_version=active_model_set.model_set_version,
            models=active_snapshot_items,
        )

        current_model_set_payload_sha256 = compute_model_set_payload_sha256(
            model_set_id=active_model_set.model_set_id,
            model_set_version=active_model_set.model_set_version,
            models=active_snapshot_items,
        )

        model_schema_map = {}
        for bm in active_model_names:
            mid = self.prediction_service.resolve_model_id(bm)
            snap_info = current_snapshot.get(mid, {})
            model_schema_map[mid] = {
                "feature_schema_sha256": snap_info.get("feature_schema_sha256"),
                "history_requirement_sha256": snap_info.get("history_requirement_sha256"),
                "label_schema_sha256": snap_info.get("label_schema_sha256"),
                "label_schema_version": snap_info.get("label_schema_version"),
            }

        # 2. Resumption Planning: Search for existing resumable run
        resumable_run = self.repository.find_resumable_run(source_identity)
        resumed_stage: Optional[str] = None
        checkpoint_to_resume: Optional[PipelineCheckpoint] = None

        if resumable_run:
            try:
                chk = self.repository.get_checkpoint(resumable_run.run_id) or resumable_run.checkpoint
                if (
                    chk is None
                    or not chk.source_identity
                    or chk.source_context is None
                    or not chk.dataset_id
                    or not chk.dataset_version
                    or not chk.pipeline_contract_version
                    or not chk.source_kind
                    or not chk.source_contract_version
                    or not chk.source_schema_version
                    or not chk.lineage_json
                    or not getattr(chk, "model_set_id", None)
                    or not getattr(chk, "model_set_version", None)
                    or not getattr(chk, "model_set_payload_sha256", None)
                ):
                    logger.warning(
                        f"[PipelineService] Run '{resumable_run.run_id}' lacks mandatory source/model_set context or identity. "
                        "Marking as invalidated (PIPELINE_SOURCE_CONTEXT_MIGRATION_REQUIRED)."
                    )
                    if chk:
                        chk.status = "invalidated"
                        self.repository.save_checkpoint(chk)
                    resumable_run.status = "failed"
                    resumable_run.checkpoint_status = "invalidated"
                    self.repository.save_run_state(resumable_run)
                else:
                    source_context_mismatch = (
                        chk.source_checksum != actual_sha
                        or chk.dataset_id != runtime_input.dataset_id
                        or chk.dataset_version != runtime_input.dataset_version
                        or chk.source_kind != runtime_input.source.source_kind
                        or chk.source_contract_version != runtime_input.source.source_contract_version
                        or chk.source_schema_version != runtime_input.source.source_schema_version
                        or chk.pipeline_contract_version != runtime_input.source.pipeline_contract_version
                    )
                    if source_context_mismatch:
                        logger.warning(
                            f"[PipelineService] Source context or checksum changed for run '{resumable_run.run_id}'. "
                            "Marking existing checkpoint as invalidated and starting fresh run."
                        )
                        chk.status = "invalidated"
                        self.repository.save_checkpoint(chk)
                        resumable_run.status = "failed"
                        resumable_run.checkpoint_status = "invalidated"
                        self.repository.save_run_state(resumable_run)
                    elif chk.status == "resumable":
                        chk_models = chk.model_snapshot or {}
                        current_keys = set(current_snapshot.keys())
                        chk_keys = set(chk_models.keys())

                        if current_keys != chk_keys:
                            raise PipelineModelSetMembershipChangeNotImplementedError(
                                f"Model Set 구성원(모델 종류/개수) 변경은 현재 지원되지 않습니다. (Current={sorted(current_keys)}, Checkpoint={sorted(chk_keys)})",
                                details=[{
                                    "current_models": sorted(current_keys),
                                    "checkpoint_models": sorted(chk_keys),
                                }],
                                retryable=False,
                            )

                        model_set_digest_mismatch = (
                            chk.model_set_id != active_model_set.model_set_id
                            or chk.model_set_version != active_model_set.model_set_version
                            or chk.model_set_payload_sha256 != current_model_set_payload_sha256
                        )

                        if model_set_digest_mismatch:
                            logger.info(
                                f"[PipelineService] Active Model Set changed for run '{resumable_run.run_id}' "
                                f"(chk_ver='{chk.model_set_version}', current_ver='{active_model_set.model_set_version}', "
                                f"chk_sha='{chk.model_set_payload_sha256[:8]}', curr_sha='{current_model_set_payload_sha256[:8]}'). "
                                "Invalidating cached prediction and batch outputs."
                            )
                            # Check if feature schema or history requirement changed
                            feature_schemas_changed = False
                            for bm in active_model_names:
                                mid = self.prediction_service.resolve_model_id(bm)
                                active_ent = current_snapshot.get(mid, {})
                                chk_ent = chk_models.get(mid, {})
                                if (
                                    active_ent.get("feature_schema_sha256") != chk_ent.get("feature_schema_sha256")
                                    or active_ent.get("history_requirement_sha256") != chk_ent.get("history_requirement_sha256")
                                ):
                                    feature_schemas_changed = True
                                    break

                            # Invalidate cached prediction results and batch manifest
                            resumable_run.prediction_results = []
                            chk.batch_manifest_ref = None
                            chk.delivery_outputs = {}
                            if feature_schemas_changed:
                                chk.stage_outputs.pop("runtime_feature", None)
                                chk.model_stage_outputs.pop("runtime_feature", None)
                                chk.last_completed_stage = "preprocessing"
                                chk.next_stage = "runtime_feature"
                            else:
                                if chk.last_completed_stage in ("runtime_prediction", "batch_building", "prediction_delivery"):
                                    chk.last_completed_stage = "runtime_feature"
                                    chk.next_stage = "runtime_prediction"

                            # Update checkpoint model_set info to current
                            chk.model_set_id = active_model_set.model_set_id
                            chk.model_set_version = active_model_set.model_set_version
                            chk.model_set_payload_sha256 = current_model_set_payload_sha256
                            chk.model_snapshot = current_snapshot
                            checkpoint_to_resume = chk
                        else:
                            checkpoint_to_resume = chk
            except Exception as exc:
                if isinstance(exc, PipelineModelSetMembershipChangeNotImplementedError):
                    raise
                logger.warning(
                    f"[PipelineService] Error inspecting resumable run '{resumable_run.run_id}': {exc}"
                )
                resumable_run.status = "failed"
                resumable_run.checkpoint_status = "invalidated"
                self.repository.save_run_state(resumable_run)

        if checkpoint_to_resume and resumable_run:
            run_id = resumable_run.run_id
            manager = PipelineStateManager(resumable_run)
            manager.state.job_id = item.job_id
            if not manager.state.source_context:
                manager.state.source_context = runtime_source_context

            last_stg = checkpoint_to_resume.last_completed_stage

            prep_outputs = checkpoint_to_resume.stage_outputs.get("preprocessing", [])
            prep_valid = bool(prep_outputs) and all(self._validate_checkpoint_output_ref(r) for r in prep_outputs)

            feat_outputs = checkpoint_to_resume.stage_outputs.get("runtime_feature", [])
            feat_valid = prep_valid and bool(feat_outputs) and all(self._validate_checkpoint_output_ref(r) for r in feat_outputs)

            pred_valid = feat_valid and bool(resumable_run.prediction_results) and last_stg in ("runtime_prediction", "batch_building", "prediction_delivery")
            batch_valid = pred_valid and checkpoint_to_resume.batch_manifest_ref is not None and self._validate_checkpoint_output_ref(checkpoint_to_resume.batch_manifest_ref)

            if batch_valid and last_stg in ("batch_building", "prediction_delivery"):
                resumed_stage = "prediction_delivery"
            elif pred_valid:
                resumed_stage = "batch_building"
            elif feat_valid:
                resumed_stage = "runtime_prediction"
            elif prep_valid:
                resumed_stage = "runtime_feature"
            else:
                resumed_stage = "preprocessing"

            manager.mark_resumed(from_stage=resumed_stage)
        else:
            run_id = f"run-{uuid.uuid4().hex[:12]}"
            source_ref = ArtifactReference(
                uri=logical_source_uri,
                sha256=item.source_checksum,
                role="source_observation_protocol",
                size_bytes=actual_size,
            )
            manager = PipelineStateManager.create(
                run_id=run_id,
                job_id=item.job_id,
                source_ref=source_ref,
                source_context=runtime_source_context,
            )
            manager.start_run()

            # Checkpoint 0: Source Validated
            manager.record_checkpoint(
                stage_name="source_validated",
                next_stage="preprocessing",
                source_identity=source_identity,
                runtime_input=runtime_input,
                model_set_id=active_model_set.model_set_id,
                model_set_version=active_model_set.model_set_version,
                model_set_payload_sha256=current_model_set_payload_sha256,
                model_snapshot=current_snapshot,
                status="resumable",
            )
            if manager.state.checkpoint:
                self.repository.save_checkpoint(manager.state.checkpoint)
            self.repository.save_run_state(manager.state)

        # -------------------------------------------------------------
        # Stage 1: Preprocessing (Plan building + Dataset publishing)
        # -------------------------------------------------------------
        dataset_ref: Optional[ArtifactReference] = None
        plan_ref: Optional[ArtifactReference] = None
        plan: dict[str, Any] = {}

        if resumed_stage in ("runtime_feature", "runtime_prediction", "batch_building", "prediction_delivery") and checkpoint_to_resume:
            prep_outputs = checkpoint_to_resume.stage_outputs.get("preprocessing", [])
            for r in prep_outputs:
                if r.role == "preprocessed_dataset":
                    dataset_ref = r
                elif r.role == "preprocessing_plan":
                    plan_ref = r
            logger.info(f"[PipelineService] Resuming: Stage 1 Preprocessing skipped for run '{run_id}'")
            if plan_ref:
                try:
                    plan = self.preprocessing_service.repository.get_plan(item.dataset_id, item.dataset_version) or {}
                except Exception:
                    plan = {}
        else:
            manager.start_stage("preprocessing", input_refs=[manager.state.source_ref])
            try:
                raw_df = self._load_source_df(source_path)

                id_cols = [c for c in ("asset_id", "Product ID", "UDI", "equipment_id", "machine_id") if c in raw_df.columns]
                if not id_cols:
                    raise PipelineMappingNotImplementedError(
                        "입력 데이터에 확정된 설비 식별자 컬럼이 없어 LLM 기반 자동 매핑이 필요합니다. 현재 단계에서는 지원되지 않습니다.",
                        details=[{
                            "enhancement_issue": 117,
                            "required_capability": "llm_mapping_generation",
                            "source_schema_fingerprint": compute_source_schema_fingerprint(raw_df),
                        }],
                        retryable=False,
                    )

                target_id = id_cols[0]
                raw_id_series = raw_df[target_id]
                invalid_id_mask = (
                    raw_id_series.isna()
                    | raw_id_series.astype(str).str.strip().str.lower().isin(["", "null", "none", "nan"])
                )
                if invalid_id_mask.any():
                    invalid_indices = [int(i) for i in raw_df.index[invalid_id_mask]]
                    raise PipelineAssetIdValueMissingError(
                        f"설비 식별자 컬럼 '{target_id}'에 누락/무효 값(None, 빈문자열, null, none)이 {len(invalid_indices)}건 존재합니다.",
                        details=[{
                            "id_column": target_id,
                            "invalid_row_count": len(invalid_indices),
                            "sample_row_indexes": invalid_indices[:10],
                        }],
                        retryable=False,
                    )

                time_cols = [c for c in ("timestamp", "observed_at", "time", "date", "datetime") if c in raw_df.columns]
                if time_cols:
                    target_time = time_cols[0]
                    raw_ts = raw_df[target_time]
                    if raw_ts.isna().any() or raw_ts.astype(str).str.strip().isin(["", "null", "none", "nan"]).any():
                        raise PipelineTimestampInvalidError(
                            f"타임스탬프 컬럼 '{target_time}'에 결측치 또는 유효하지 않은 값이 포함되어 있습니다.",
                            details=[{"time_column": target_time}],
                            retryable=False,
                        )
                    try:
                        converted_ts = pd.to_datetime(raw_ts, utc=True)
                        if converted_ts.isna().any():
                            raise ValueError("NaT detected")
                    except Exception as exc:
                        raise PipelineTimestampInvalidError(
                            f"타임스탬프 컬럼 '{target_time}' 파싱 실패: {exc}",
                            details=[{"time_column": target_time, "error": str(exc)}],
                            retryable=False,
                        ) from exc

                    raw_df_chk = raw_df.copy()
                    raw_df_chk[target_time] = converted_ts
                    dups = raw_df_chk.duplicated(subset=[target_id, target_time], keep=False)
                    if dups.any():
                        dup_sample = raw_df_chk[dups].iloc[0]
                        sample_asset = str(dup_sample[target_id])
                        sample_ts = str(dup_sample[target_time])
                        raise PipelineTimestampInvalidError(
                            f"동일 설비 '{sample_asset}' 및 시각 '{sample_ts}'에 대한 중복 관측 행이 {dups.sum()}건 존재합니다. 계약상 중복 병합 정책이 정의되지 않아 처리를 중단합니다.",
                            details=[{"asset_id": sample_asset, "timestamp": sample_ts, "duplicate_count": int(dups.sum())}],
                            retryable=False,
                        )

                schema_fp = compute_source_schema_fingerprint(raw_df)
                plan = self.preprocessing_service.planner.build_plan(str(source_path))
                if item.source_kind in {
                    "live_sensor",
                    "simulation_overlay",
                    "maintenance_replay_overlay",
                }:
                    # Runtime snapshot envelopes are already validated at the
                    # enqueue boundary.  Preserve their discriminator, lineage,
                    # and both sensor-family column sets; generic profiling can
                    # otherwise drop sparse CNC columns from a mixed fleet file.
                    plan.update(
                        {
                            "structure_type": "tabular_column_as_attribute",
                            "selected_columns": list(raw_df.columns),
                            "id_column": target_id,
                            "time_column": time_cols[0] if time_cols else None,
                            "duplicate_policy": "error",
                        }
                    )
                self.preprocessing_service.validate_plan(raw_df, plan)

                try:
                    logical_src_uri = self.preprocessing_service.repository.get_logical_uri(source_path)
                except Exception:
                    logical_src_uri = f"data/incoming/{source_path.name}"

                plan_data_to_publish = dict(plan)
                plan_data_to_publish.update({
                    "source_dataset_uri": logical_src_uri,
                    "source_dataset_sha256": item.source_checksum,
                    "source_schema_fingerprint": schema_fp,
                    "source_dataset_size_bytes": source_path.stat().st_size if source_path.exists() else None,
                })
                published_plan = self.preprocessing_service.repository.publish_plan(
                    dataset_id=item.dataset_id,
                    dataset_version=item.dataset_version,
                    plan_data=plan_data_to_publish,
                )

                plan_ref = ArtifactReference(
                    uri=published_plan.preprocessing_plan_uri,
                    sha256=published_plan.sha256,
                    role="preprocessing_plan",
                    size_bytes=None,
                )

                preprocessed_df = self.preprocessing_service.preprocess_with_plan(str(source_path), plan)
                dataset_ref = self._publish_preprocessed_dataset(run_id, preprocessed_df)

                manager.register_intermediate_outputs([dataset_ref])
                manager.succeed_stage("preprocessing", output_refs=[plan_ref, dataset_ref])

                # Checkpoint 1: Preprocessing Completed
                manager.record_checkpoint(
                    stage_name="preprocessing",
                    next_stage="runtime_feature",
                    source_identity=source_identity,
                    runtime_input=runtime_input,
                    model_set_id=active_model_set.model_set_id,
                    model_set_version=active_model_set.model_set_version,
                    model_set_payload_sha256=current_model_set_payload_sha256,
                    stage_outputs=[plan_ref, dataset_ref],
                    model_snapshot=current_snapshot,
                    status="resumable",
                )
                if manager.state.checkpoint:
                    self.repository.save_checkpoint(manager.state.checkpoint)
                self.repository.save_run_state(manager.state)
            except Exception as exc:
                err_code = getattr(exc, "code", "PIPELINE_PREPROCESSING_FAILED")
                retryable = getattr(exc, "retryable", False)
                manager.fail_stage("preprocessing", err_code, str(exc), retryable=retryable)
                manager.finish_run("failed")
                self.repository.save_run_state(manager.state)
                raise

        # -------------------------------------------------------------
        # Stage 2: Runtime Feature (Structured Per-Model Checkpoint)
        # -------------------------------------------------------------
        assert dataset_ref is not None, "dataset_ref must be available"
        model_feature_refs: dict[str, ArtifactReference] = {}
        model_feature_bundles: dict[str, RuntimeFeatureBundle] = {}
        model_feature_outputs_map: dict[str, dict[str, Any]] = {}
        model_feature_errors: dict[str, Any] = {}
        last_feat_error: Optional[Exception] = None

        prep_file_path = Path(dataset_ref.uri)
        if not prep_file_path.is_file():
            prep_file_path = (self.repository.base_dir / dataset_ref.uri).resolve()
        preprocessed_input_df = pd.read_csv(prep_file_path)

        id_col = plan.get("id_column") or "asset_id"
        if id_col not in preprocessed_input_df.columns:
            candidates = [c for c in ("asset_id", "Product ID", "UDI", "equipment_id", "machine_id") if c in preprocessed_input_df.columns]
            if candidates:
                id_col = candidates[0]
            else:
                raise PipelineAssetIdColumnMissingError(
                    "전처리 데이터셋에 설비 식별자(asset_id) 컬럼이 누락되었습니다.",
                    retryable=False,
                )

        # Lookup structured stage outputs from checkpoint
        cached_model_feat_outputs = (
            checkpoint_to_resume.model_stage_outputs.get("runtime_feature", {})
            if checkpoint_to_resume and checkpoint_to_resume.model_stage_outputs
            else {}
        )
        cached_model_snapshot = (
            checkpoint_to_resume.model_snapshot
            if checkpoint_to_resume and checkpoint_to_resume.model_snapshot
            else {}
        )

        manager.start_stage("runtime_feature", input_refs=[dataset_ref, plan_ref] if plan_ref else [dataset_ref])

        applicable_model_names: list[str] = []
        try:
            for base_model in active_model_names:
                model_id = self.prediction_service.resolve_model_id(base_model)
                artifact = model_artifacts[base_model]
                model_input_df = self._filter_observations_for_artifact(
                    preprocessed_input_df,
                    artifact,
                )
                if model_input_df.empty:
                    logger.info(
                        "[PipelineService] Skipping model '%s': input contains no '%s' observations",
                        model_id,
                        (artifact.manifest.get("compatibility") or {}).get("observation_family"),
                    )
                    continue
                applicable_model_names.append(base_model)

                # Verify snapshot & feature schema match
                active_snap_entry = current_snapshot.get(model_id, {})
                chk_snap_entry = cached_model_snapshot.get(model_id, {})
                cached_entry = cached_model_feat_outputs.get(model_id, {})

                cached_ref = None
                if cached_entry and "artifact_ref" in cached_entry:
                    cached_ref = ArtifactReference.model_validate(cached_entry["artifact_ref"])

                # Check if feature NPY can be reused
                feature_schema_match = (
                    active_snap_entry.get("feature_schema_sha256") == chk_snap_entry.get("feature_schema_sha256")
                    and active_snap_entry.get("history_requirement_sha256") == chk_snap_entry.get("history_requirement_sha256")
                )

                if cached_ref and feature_schema_match and self._validate_checkpoint_output_ref(cached_ref):
                    try:
                        bundle = self.runtime_feature_service.load_bundle_from_artifact(
                            artifact_ref=cached_ref,
                            preprocessed_df=model_input_df,
                            feature_schema_dict=artifact.feature_schema,
                            id_column=id_col,
                            time_column=plan.get("time_column"),
                            dataset_id=item.dataset_id,
                            dataset_version=item.dataset_version,
                        )
                        model_feature_refs[base_model] = cached_ref
                        model_feature_bundles[base_model] = bundle
                        model_feature_outputs_map[model_id] = {
                            "artifact_ref": cached_ref.model_dump(),
                            "model_version": artifact.model_version,
                            "feature_schema_version": artifact.feature_schema.get("feature_schema_version", "v1"),
                            "history_requirement_version": artifact.history_requirement.get("history_requirement_version", "v1"),
                        }
                        logger.info(f"[PipelineService] Reused verified feature for '{model_id}' from structured checkpoint")
                        continue
                    except Exception as exc:
                        logger.warning(f"[PipelineService] Failed to load cached feature bundle for '{model_id}': {exc}")

                # Re-extract feature for model_id
                try:
                    bundle, feat_ref = self.runtime_feature_service.extract_and_publish(
                        preprocessed_df=model_input_df,
                        feature_schema_dict=artifact.feature_schema,
                        history_requirement_dict=artifact.history_requirement,
                        model_id=model_id,
                        model_version=artifact.model_version,
                        id_column=id_col,
                        time_column=plan.get("time_column"),
                        dataset_id=item.dataset_id,
                        dataset_version=item.dataset_version,
                        run_id=run_id,
                    )
                    model_feature_refs[base_model] = feat_ref
                    model_feature_bundles[base_model] = bundle
                    model_feature_outputs_map[model_id] = {
                        "artifact_ref": feat_ref.model_dump(),
                        "model_version": artifact.model_version,
                        "feature_schema_version": artifact.feature_schema.get("feature_schema_version", "v1"),
                        "history_requirement_version": artifact.history_requirement.get("history_requirement_version", "v1"),
                    }
                    logger.info(f"[PipelineService] Extracted fresh feature for '{model_id}'")
                except Exception as exc:
                    last_feat_error = exc
                    model_feature_errors[base_model] = exc
                    logger.warning(f"[PipelineService] Feature extraction failed for '{model_id}': {exc}")

            if not model_feature_refs:
                if last_feat_error is not None:
                    raise last_feat_error
                raise PipelineRuntimeFeatureFailedError(
                    "모든 모델에 대해 Runtime Feature 생성이 실패했습니다.",
                    retryable=False,
                )

            manager.register_intermediate_outputs(list(model_feature_refs.values()))
            if not (resumed_stage in ("runtime_prediction", "batch_building", "prediction_delivery")):
                manager.succeed_stage("runtime_feature", output_refs=list(model_feature_refs.values()))

            # Checkpoint 2: Runtime Feature Completed
            manager.record_checkpoint(
                stage_name="runtime_feature",
                next_stage="runtime_prediction",
                source_identity=source_identity,
                runtime_input=runtime_input,
                model_set_id=active_model_set.model_set_id,
                model_set_version=active_model_set.model_set_version,
                model_set_payload_sha256=current_model_set_payload_sha256,
                stage_outputs=list(model_feature_refs.values()),
                model_stage_outputs={"runtime_feature": model_feature_outputs_map},
                model_snapshot=current_snapshot,
                snapshot_validation_status="valid",
                status="resumable",
            )
            if manager.state.checkpoint:
                self.repository.save_checkpoint(manager.state.checkpoint)
            self.repository.save_run_state(manager.state)
        except Exception as exc:
            err_code = getattr(exc, "code", "PIPELINE_RUNTIME_FEATURE_FAILED")
            retryable = getattr(exc, "retryable", False)
            if manager.state.stages.get("runtime_feature") and manager.state.stages["runtime_feature"].status == "running":
                manager.fail_stage("runtime_feature", err_code, str(exc), retryable=retryable)
            manager.finish_run("failed")
            self.repository.save_run_state(manager.state)
            raise

        # -------------------------------------------------------------
        # Stage 3: Prediction (Score Calculation across Models per Equipment)
        # -------------------------------------------------------------
        model_results: list[InternalModelPredictionResult] = []

        # Check if prediction results can be reused based on snapshot match
        can_reuse_pred = (
            resumed_stage in ("batch_building", "prediction_delivery")
            and resumable_run is not None
            and bool(resumable_run.prediction_results)
            and checkpoint_to_resume is not None
        )
        if can_reuse_pred:
            # Check model versions & manifest sha256 match for prediction reuse
            for bm in active_model_names:
                mid = self.prediction_service.resolve_model_id(bm)
                active_entry = current_snapshot.get(mid, {})
                chk_entry = cached_model_snapshot.get(mid, {})
                if active_entry.get("model_version") != chk_entry.get("model_version") or active_entry.get("manifest_sha256") != chk_entry.get("manifest_sha256"):
                    can_reuse_pred = False
                    logger.info(f"[PipelineService] Model version/manifest changed for '{mid}'. Invalidating prediction reuse.")
                    break

        if can_reuse_pred and resumable_run:
            model_results = list(resumable_run.prediction_results)
            logger.info(f"[PipelineService] Resuming: Stage 3 Runtime Prediction skipped for run '{run_id}'")
        else:
            manager.start_stage("prediction", input_refs=list(model_feature_refs.values()))
            try:
                model_results = self.prediction_service.predict_for_models(
                    base_models=applicable_model_names,
                    model_feature_refs=model_feature_refs,
                    model_feature_bundles=model_feature_bundles,
                    model_feature_errors=model_feature_errors,
                    active_model_set=active_model_set,
                )

                succeeded_count = sum(1 for r in model_results if r.status == "succeeded")
                if succeeded_count == 0:
                    raise PipelineModelPredictionFailedError(
                        "모든 모델의 예측 계산이 실패하여 전달 가능한 결과가 없습니다.",
                        details=[{"total_results": len(model_results)}],
                        retryable=False,
                    )

                pred_output_refs = [
                    r.artifact_ref for r in model_results if r.artifact_ref is not None
                ]
                manager.succeed_stage("prediction", output_refs=pred_output_refs)

                # Checkpoint 3: Runtime Prediction Completed
                manager.record_checkpoint(
                    stage_name="runtime_prediction",
                    next_stage="batch_building",
                    source_identity=source_identity,
                    runtime_input=runtime_input,
                    model_set_id=active_model_set.model_set_id,
                    model_set_version=active_model_set.model_set_version,
                    model_set_payload_sha256=current_model_set_payload_sha256,
                    stage_outputs=pred_output_refs,
                    model_snapshot=current_snapshot,
                    status="resumable",
                )
                if manager.state.checkpoint:
                    self.repository.save_checkpoint(manager.state.checkpoint)
                self.repository.save_run_state(manager.state)
            except Exception as exc:
                err_code = getattr(exc, "code", "PIPELINE_MODEL_PREDICTION_FAILED")
                retryable = getattr(exc, "retryable", False)
                manager.fail_stage("prediction", err_code, str(exc), retryable=retryable)
                manager.finish_run("failed")
                self.repository.save_run_state(manager.state)
                raise

        # -------------------------------------------------------------
        # Stage 4: Batch Building (Batch Staging & Manifest Verification)
        # -------------------------------------------------------------
        manager.start_stage("batch_building")
        staged_batches: Optional[dict[str, Any]] = None

        if checkpoint_to_resume and checkpoint_to_resume.batch_manifest_ref:
            if self._validate_checkpoint_output_ref(checkpoint_to_resume.batch_manifest_ref):
                try:
                    staged_batches = self.prediction_batch_service.load_staged_batches(checkpoint_to_resume.batch_manifest_ref)
                    logger.info(f"[PipelineService] Loaded {len(staged_batches)} staged batches from manifest")
                except Exception as exc:
                    logger.warning(f"[PipelineService] Failed to load staged batches: {exc}")

        try:
            if not staged_batches:
                batch_summary: PredictionBatchSummary = self.prediction_batch_service.collect(model_results)
                manager.record_predictions(model_results)

                batch_manifest_ref = self.prediction_batch_service.stage_batches(
                    run_id=run_id,
                    job_id=item.job_id,
                    summary=batch_summary,
                    dataset_id=item.dataset_id,
                    dataset_version=item.dataset_version,
                    pipeline_contract_version=contract_ver,
                    source_lineage=SourceLineage(
                        source_uri=logical_source_uri,
                        source_checksum=item.source_checksum,
                        pipeline_contract_version=contract_ver,
                    ),
                    model_set_id=active_model_set.model_set_id,
                    model_set_version=active_model_set.model_set_version,
                    sensor_data_ref={"uri": logical_source_uri, "sha256": item.source_checksum},
                    source_context=runtime_source_context,
                    active_model_set_snapshot=active_model_set_snapshot,
                    model_schema_map=model_schema_map,
                )
                manager.register_intermediate_outputs([batch_manifest_ref])
            else:
                eq_batches = {}
                for aid, payload in staged_batches.items():
                    obs_str = payload.results[0].observed_at.isoformat() if payload.results else ""
                    succeeded_m = [r.model_id for r in payload.results if r.output_status == "predicted"]
                    failed_m = [r.model_id for r in payload.results if r.output_status != "predicted"]
                    eq_batches[aid] = EquipmentModelBatch(
                        asset_id=aid,
                        status="succeeded" if not failed_m else "partially_succeeded",
                        observed_at=obs_str,
                        succeeded_models=succeeded_m,
                        failed_models=failed_m,
                        model_results={},
                    )
                batch_summary = PredictionBatchSummary(
                    overall_status="succeeded",
                    equipment_batches=eq_batches,
                    total_equipments=len(eq_batches),
                    succeeded_equipments=list(eq_batches.keys()),
                )
                batch_manifest_ref = checkpoint_to_resume.batch_manifest_ref if checkpoint_to_resume else None

            manager.succeed_stage("batch_building", output_refs=[batch_manifest_ref] if batch_manifest_ref else [])

            # Checkpoint 4: Batch Built
            manager.record_checkpoint(
                stage_name="batch_building",
                next_stage="prediction_delivery",
                source_identity=source_identity,
                runtime_input=runtime_input,
                model_set_id=active_model_set.model_set_id,
                model_set_version=active_model_set.model_set_version,
                model_set_payload_sha256=current_model_set_payload_sha256,
                stage_outputs=[batch_manifest_ref] if batch_manifest_ref else [],
                batch_manifest_ref=batch_manifest_ref,
                model_snapshot=current_snapshot,
                status="resumable",
            )
            if manager.state.checkpoint:
                self.repository.save_checkpoint(manager.state.checkpoint)
            self.repository.save_run_state(manager.state)
        except Exception as exc:
            err_code = getattr(exc, "code", "PIPELINE_BATCH_BUILDING_FAILED")
            retryable = getattr(exc, "retryable", False)
            manager.fail_stage("batch_building", err_code, str(exc), retryable=retryable)
            manager.finish_run("failed")
            self.repository.save_run_state(manager.state)
            raise

        # -------------------------------------------------------------
        # Stage 5: Prediction Delivery (Idempotent Outbox Persistence)
        # -------------------------------------------------------------
        if batch_summary.equipment_batches:
            manager.start_stage("prediction_delivery")
            manager.record_prediction_delivery("pending")

            post_sha = compute_file_sha256(source_path)
            post_size = source_path.stat().st_size
            if post_sha != item.source_checksum or (item.size_bytes is not None and post_size != item.size_bytes):
                raise PipelineSourceChecksumChangedError(
                    f"파이프라인 실행 도중 소스 파일이 변경되었습니다: 시작={item.source_checksum}, 완료={post_sha}",
                    details=[{"expected": item.source_checksum, "actual": post_sha, "start_size": item.size_bytes, "finish_size": post_size}],
                    retryable=True,
                )

            event_ids: list[str] = []
            events_state: list[PredictionDeliveryEventState] = []
            delivery_outputs_map: dict[str, dict[str, Any]] = {}

            existing_delivery = checkpoint_to_resume.delivery_outputs if checkpoint_to_resume and checkpoint_to_resume.delivery_outputs else {}

            for asset_id, eq_batch in batch_summary.equipment_batches.items():
                batch_observed_at = eq_batch.observed_at
                if not batch_observed_at:
                    raise PipelinePredictionObservationAlignmentNotImplementedError(
                        f"설비 '{asset_id}'의 결과 배치를 위한 관측 시각(observed_at)이 누락되었습니다.",
                        details=[{"asset_id": asset_id}],
                        retryable=False,
                    )

                if staged_batches and asset_id in staged_batches:
                    batch_payload = staged_batches[asset_id]
                else:
                    internal_items: list[InternalModelPredictionResult] = []
                    if eq_batch.internal_results:
                        internal_items = list(eq_batch.internal_results)
                    else:
                        for m_id, m_res in eq_batch.model_results.items():
                            internal_r = InternalModelPredictionResult(
                                asset_id=asset_id,
                                model_id=m_id,
                                model_version=m_res.model_version,
                                status=m_res.status,
                                observed_at=m_res.observed_at,
                                score_type=m_res.score_type,
                                score_source=m_res.score_source,
                                score=m_res.score,
                                artifact_ref=m_res.artifact_ref,
                                feature_ref=m_res.feature_ref,
                                manifest_checksum=m_res.manifest_checksum,
                                feature_schema_version=m_res.feature_schema_version,
                                label_schema_version=m_res.label_schema_version,
                                history_requirement_version=m_res.history_requirement_version,
                                model_set_id=m_res.model_set_id or active_model_set.model_set_id,
                                model_set_version=m_res.model_set_version or active_model_set.model_set_version,
                                error_code=m_res.error_code,
                                error_message=m_res.error_message,
                            )
                            internal_items.append(internal_r)

                    batch_payload = build_external_prediction_batch(
                        internal_results=internal_items,
                        source_context=runtime_source_context,
                        dataset_id=item.dataset_id,
                        dataset_version=item.dataset_version,
                        active_model_set_snapshot=active_model_set_snapshot,
                        model_schema_map=model_schema_map,
                    )

                prev_delivery = existing_delivery.get(asset_id)
                if prev_delivery and prev_delivery.get("status") == "published":
                    event_id = prev_delivery["event_id"]
                    payload_sha256 = prev_delivery["payload_sha256"]
                    existing_outbox = self.prediction_delivery_service.get_outbox_item(event_id)
                    if existing_outbox is not None:
                        _, current_sha = self.prediction_delivery_service.compute_canonical_payload_sha256(batch_payload)
                        if current_sha == payload_sha256:
                            logger.info(f"[PipelineService] Skipping already published outbox item '{event_id}' for equipment '{asset_id}'")
                            event_ids.append(event_id)
                            events_state.append(
                                PredictionDeliveryEventState(
                                    event_id=event_id,
                                    asset_id=asset_id,
                                    status="sent" if existing_outbox.status == "sent" else "pending",
                                    attempt=existing_outbox.attempt,
                                    max_attempts=5,
                                    updated_at=existing_outbox.updated_at,
                                )
                            )
                            delivery_outputs_map[asset_id] = prev_delivery
                            continue

                outbox_item, payload_sha256 = self.prediction_delivery_service.register_idempotent_outbox_record(batch_payload, run_id=run_id)
                self.repository.save_event(batch_payload)

                event_ids.append(outbox_item.event_id)
                events_state.append(
                    PredictionDeliveryEventState(
                        event_id=outbox_item.event_id,
                        asset_id=asset_id,
                        status="pending",
                        attempt=0,
                        max_attempts=5,
                        updated_at=now_utc_iso(),
                    )
                )
                delivery_outputs_map[asset_id] = {
                    "event_id": outbox_item.event_id,
                    "payload_sha256": payload_sha256,
                    "status": "published",
                    "outbox_ref": {
                        "uri": f"data/outbox/notification/{outbox_item.event_id}.json",
                        "sha256": payload_sha256,
                        "role": "prediction_outbox",
                    },
                }

            manager.state.prediction_event_ids = event_ids
            manager.state.prediction_events = events_state
            manager.succeed_stage("prediction_delivery", output_refs=[])

            # Checkpoint 5: Final Published Completed
            manager.record_checkpoint(
                stage_name="prediction_delivery",
                next_stage="completed",
                source_identity=source_identity,
                runtime_input=runtime_input,
                model_set_id=active_model_set.model_set_id,
                model_set_version=active_model_set.model_set_version,
                model_set_payload_sha256=current_model_set_payload_sha256,
                delivery_outputs=delivery_outputs_map,
                model_snapshot=current_snapshot,
                status="completed",
            )
            if manager.state.checkpoint:
                self.repository.save_checkpoint(manager.state.checkpoint)
        else:
            manager.record_prediction_delivery("not_required")
            manager.state.prediction_events = []

        # -------------------------------------------------------------
        # Intermediate Outputs Cleanup (Run-Dedicated Files Only)
        # -------------------------------------------------------------
        manager.mark_cleanup_pending()
        self.repository.save_run_state(manager.state)

        cleanup_success, deleted_paths, cleanup_error = self.repository.cleanup_run_intermediate_outputs(
            run_id=run_id,
            intermediate_refs=manager.state.intermediate_outputs,
        )

        manager.state.cleanup_deleted_paths = deleted_paths

        if cleanup_success:
            manager.mark_cleaned()
            final_run_status = batch_summary.overall_status
        else:
            manager.state.cleanup_failed_paths = [cleanup_error] if cleanup_error else []
            manager.mark_cleanup_failed(
                error_code="PIPELINE_INTERMEDIATE_CLEANUP_FAILED",
                error_message=cleanup_error or "Intermediate cleanup failed",
            )
            final_run_status = "succeeded_with_cleanup_warning" if batch_summary.overall_status == "succeeded" else batch_summary.overall_status

        # -------------------------------------------------------------
        # Finish Run and Persist
        # -------------------------------------------------------------
        manager.finish_run(final_run_status)
        self.repository.save_run_state(manager.state)

        return manager.state

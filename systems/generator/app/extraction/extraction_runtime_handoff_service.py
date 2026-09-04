"""Service managing dataset integrity validation, handoff creation, and runtime prediction queue delivery."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import jsonschema

from systems.generator.file_integrity import compute_file_sha256
from systems.generator.generator_config import PATHS, PROJECT_ROOT
from systems.generator.app.extraction.extraction_exception import (
    ExtractionHandoffChecksumMismatchError,
    ExtractionHandoffDatasetIdentityMismatchError,
    ExtractionHandoffDisabledError,
    ExtractionHandoffEnqueueFailedError,
    ExtractionHandoffManifestInvalidError,
    ExtractionHandoffObservationsMissingError,
    ExtractionHandoffPathUnsupportedError,
    ExtractionHandoffQueueConflictError,
    ExtractionHandoffRetryExhaustedError,
    ExtractionHandoffRuntimeDisabledError,
)
from systems.generator.app.extraction.extraction_handoff_repository import (
    ExtractionHandoffRepository,
    compute_handoff_id,
    compute_runtime_job_id,
)
from systems.generator.app.extraction.extraction_schema import (
    ExtractionRuntimeHandoff,
    ExtractionRuntimeHandoffDataset,
    ExtractionRuntimeHandoffDelivery,
    ExtractionRuntimeHandoffLineage,
    ExtractionRuntimeHandoffRuntimeInput,
    ExtractionRuntimeHandoffSource,
)
from systems.generator.app.runtime_pipeline.pipeline_exception import (
    PipelineDuplicateInputError,
    PipelineInputNotFoundError,
    PipelineQueueItemInvalidError,
    PipelineQueuePersistError,
    PipelineSourceAlreadyRegisteredError,
)
from systems.generator.app.runtime_pipeline.pipeline_manager import (
    PipelineManager,
)
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    PipelineQueueItem,
    PredictionResultLineage,
    RuntimeInputIdentity,
    RuntimeSourceContext,
)

logger = logging.getLogger(__name__)

MANIFEST_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "schemas" / "generator-dataset-input-manifest.schema.json"


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExtractionRuntimeHandoffService:
    """Validates published datasets and coordinates atomic handoff delivery to Runtime Prediction Pipeline."""

    def __init__(
        self,
        repository: Optional[ExtractionHandoffRepository] = None,
        pipeline_manager: Optional[PipelineManager] = None,
    ) -> None:
        self.repository = repository or ExtractionHandoffRepository()
        self._pipeline_manager = pipeline_manager
        self._manifest_schema_validator: Optional[jsonschema.Draft202012Validator] = None

    @property
    def pipeline_manager(self) -> PipelineManager:
        if self._pipeline_manager is not None:
            return self._pipeline_manager
        return PipelineManager.get_instance()

    def _get_manifest_validator(self) -> jsonschema.Draft202012Validator:
        if self._manifest_schema_validator is None:
            schema_file = MANIFEST_SCHEMA_PATH
            if not schema_file.is_file():
                schema_file = Path.cwd() / MANIFEST_SCHEMA_PATH
            schema = json.loads(schema_file.read_text(encoding="utf-8"))
            self._manifest_schema_validator = jsonschema.Draft202012Validator(
                schema, format_checker=jsonschema.FormatChecker()
            )
        return self._manifest_schema_validator

    def _get_logical_uri(self, path: Path) -> str:
        """Convert path to relative logical URI under project root or data dir."""
        try:
            rel = path.relative_to(PROJECT_ROOT)
            return str(rel.as_posix())
        except ValueError:
            pass
        try:
            rel = path.relative_to(PATHS.data_dir)
            return f"data/{str(rel.as_posix())}"
        except ValueError:
            return str(path.as_posix())

    def create_or_get_handoff(
        self,
        dataset_manifest_path: Path,
    ) -> ExtractionRuntimeHandoff:
        """Verify published dataset integrity and construct or load persistent handoff record."""
        manifest_file = dataset_manifest_path.resolve()
        if not manifest_file.is_file():
            raise ExtractionHandoffManifestInvalidError(
                f"Dataset manifest file not found: '{manifest_file}'"
            )

        # Path traversal guard
        if ".." in str(manifest_file):
            raise ExtractionHandoffPathUnsupportedError(
                f"Manifest path contains unsafe traversal: '{manifest_file}'"
            )

        # 1. Load and validate manifest schema
        try:
            manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
            self._get_manifest_validator().validate(manifest_data)
        except Exception as exc:
            raise ExtractionHandoffManifestInvalidError(
                f"Dataset manifest failed JSON schema validation: {exc}"
            ) from exc

        dataset_id = manifest_data.get("dataset_id")
        dataset_version = manifest_data.get("dataset_version")
        source_contract_version = manifest_data.get("manifest_version")
        source_schema_version = manifest_data.get("schema_version")

        if not dataset_id or not dataset_version or not source_contract_version or not source_schema_version:
            raise ExtractionHandoffManifestInvalidError(
                "dataset_manifest.json must declare non-empty 'dataset_id', 'dataset_version', "
                "'manifest_version', and 'schema_version'."
            )

        # 2. Check observations.jsonl
        dataset_dir = manifest_file.parent
        obs_file = dataset_dir / "observations.jsonl"
        if not obs_file.is_file():
            raise ExtractionHandoffObservationsMissingError(
                f"Required observations.jsonl not found in dataset directory '{dataset_dir}'"
            )

        # Check declared file entry in manifest
        files = manifest_data.get("files", [])
        obs_entries = [f for f in files if f.get("path") == "observations.jsonl"]
        if not obs_entries:
            raise ExtractionHandoffManifestInvalidError(
                "dataset_manifest.json must declare 'observations.jsonl' in files array."
            )
        declared_entry = obs_entries[0]
        declared_sha = declared_entry.get("sha256", "").strip().lower()
        declared_size = declared_entry.get("size_bytes", 0)

        # 3. Compute actual SHA-256 and size
        actual_sha = compute_file_sha256(obs_file)
        actual_size = obs_file.stat().st_size

        if actual_sha != declared_sha:
            raise ExtractionHandoffChecksumMismatchError(
                f"observations.jsonl checksum mismatch: declared '{declared_sha}', computed '{actual_sha}'"
            )
        if actual_size != declared_size:
            raise ExtractionHandoffChecksumMismatchError(
                f"observations.jsonl size mismatch: declared {declared_size}, actual {actual_size}"
            )

        obs_uri = self._get_logical_uri(obs_file)
        manifest_uri = self._get_logical_uri(manifest_file)

        # 4. Compute deterministic handoff ID
        handoff_id = compute_handoff_id(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            observations_uri=obs_uri,
            observations_sha256=actual_sha,
            source_kind="live_sensor",
            source_contract_version=source_contract_version,
            source_schema_version=source_schema_version,
            pipeline_contract_version="generator-prediction-result-v1",
        )

        # Check if already exists in repository
        existing, _ = self.repository.find_handoff_by_id(handoff_id)
        if existing is not None:
            return existing

        now_str = now_utc_iso()
        initial_status = (
            "pending" if PATHS.runtime_prediction_enabled else "runtime_disabled"
        )

        new_handoff = ExtractionRuntimeHandoff(
            handoff_schema_version="generator-extraction-runtime-handoff-v1",
            handoff_id=handoff_id,
            status=initial_status,
            created_at=now_str,
            updated_at=now_str,
            dataset=ExtractionRuntimeHandoffDataset(
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                manifest_uri=manifest_uri,
                observations_uri=obs_uri,
                observations_sha256=actual_sha,
                observations_size_bytes=actual_size,
            ),
            runtime_input=ExtractionRuntimeHandoffRuntimeInput(
                dataset_id=dataset_id,
                dataset_version=dataset_version,
                source=ExtractionRuntimeHandoffSource(
                    source_uri=obs_uri,
                    source_checksum=actual_sha,
                    source_kind="live_sensor",
                    source_contract_version=source_contract_version,
                    source_schema_version=source_schema_version,
                    pipeline_contract_version="generator-prediction-result-v1",
                    lineage=ExtractionRuntimeHandoffLineage(),
                ),
            ),
            delivery=ExtractionRuntimeHandoffDelivery(
                attempt_count=0,
                runtime_job_id=None,
                queue_item_id=None,
                last_error_code=None,
                last_error_message=None,
                next_retry_at=None,
            ),
        )

        self.repository.save_handoff(new_handoff)
        logger.info(f"[ExtractionRuntimeHandoffService] Created handoff record {handoff_id} with status={initial_status}")
        return new_handoff

    def _get_existing_queue_item(
        self,
        *,
        handoff: ExtractionRuntimeHandoff,
        runtime_job_id: str,
    ) -> Optional[PipelineQueueItem]:
        """Query existing queue item by job_id with strict error classification.

        Rules:
        - get_item() returns None -> Item does not exist -> return None
        - PipelineQueueItemInvalidError -> Handoff blocked, EXTRACTION_HANDOFF_CORRUPT_QUEUE_ITEM, non-retryable
        - PipelineQueuePersistError -> Handoff retry_wait, attempt_count += 1, storage error code, retryable
        - Other exception -> Handoff blocked, EXTRACTION_HANDOFF_UNKNOWN_QUEUE_ERROR, enqueue aborted
        """
        try:
            return self.pipeline_manager.queue.get_item(runtime_job_id)
        except PipelineQueueItemInvalidError as exc:
            logger.error(
                f"[ExtractionRuntimeHandoffService] Corrupt/legacy queue item for job '{runtime_job_id}': {exc}"
            )
            handoff.status = "blocked"
            handoff.delivery.last_error_code = "EXTRACTION_HANDOFF_CORRUPT_QUEUE_ITEM"
            handoff.delivery.last_error_message = str(exc)
            handoff.updated_at = now_utc_iso()
            self.repository.save_handoff(handoff)
            raise ExtractionHandoffQueueConflictError(
                f"Corrupt or legacy queue item for job '{runtime_job_id}': {exc}"
            ) from exc
        except PipelineQueuePersistError as exc:
            logger.warning(
                f"[ExtractionRuntimeHandoffService] Transient error fetching queue item '{runtime_job_id}': {exc}"
            )
            handoff.status = "retry_wait"
            handoff.delivery.attempt_count += 1
            handoff.delivery.last_error_code = getattr(exc, "code", "PIPELINE_QUEUE_STORAGE_ERROR")
            handoff.delivery.last_error_message = str(exc)
            handoff.updated_at = now_utc_iso()
            self.repository.save_handoff(handoff)
            raise
        except Exception as exc:
            logger.exception(
                f"[ExtractionRuntimeHandoffService] Unknown error fetching queue item '{runtime_job_id}': {exc}"
            )
            handoff.status = "blocked"
            handoff.delivery.last_error_code = "EXTRACTION_HANDOFF_UNKNOWN_QUEUE_ERROR"
            handoff.delivery.last_error_message = str(exc)
            handoff.updated_at = now_utc_iso()
            self.repository.save_handoff(handoff)
            raise ExtractionHandoffEnqueueFailedError(
                f"Unknown error fetching queue item '{runtime_job_id}': {exc}"
            ) from exc

    def _validate_queue_context_and_heal(
        self,
        *,
        existing_job: PipelineQueueItem,
        handoff: ExtractionRuntimeHandoff,
        runtime_job_id: str,
    ) -> ExtractionRuntimeHandoff:
        """Validate all 9 context fields against existing queue item and self-heal handoff to enqueued if matched."""
        src = handoff.runtime_input.source
        handoff_lin = src.lineage.model_dump() if hasattr(src.lineage, "model_dump") else (src.lineage or {})
        existing_lin = existing_job.lineage.model_dump() if hasattr(existing_job.lineage, "model_dump") else (existing_job.lineage or {})

        matches = (
            existing_job.source_uri == src.source_uri
            and existing_job.source_checksum == src.source_checksum
            and existing_job.source_kind == src.source_kind
            and existing_job.source_contract_version == src.source_contract_version
            and existing_job.source_schema_version == src.source_schema_version
            and existing_job.pipeline_contract_version == src.pipeline_contract_version
            and existing_job.dataset_id == handoff.runtime_input.dataset_id
            and existing_job.dataset_version == handoff.runtime_input.dataset_version
            and existing_lin == handoff_lin
        )

        if matches:
            logger.info(
                f"[ExtractionRuntimeHandoffService] Job '{runtime_job_id}' already present in runtime queue with matching context; healing handoff {handoff.handoff_id} to enqueued."
            )
            handoff.status = "enqueued"
            handoff.delivery.runtime_job_id = runtime_job_id
            handoff.delivery.queue_item_id = existing_job.job_id
            handoff.delivery.last_error_code = None
            handoff.delivery.last_error_message = None
            handoff.updated_at = now_utc_iso()
            self.repository.save_handoff(handoff)
            return handoff
        else:
            logger.error(
                f"[ExtractionRuntimeHandoffService] Queue conflict for job '{runtime_job_id}': existing item context does not match handoff {handoff.handoff_id}."
            )
            handoff.status = "blocked"
            handoff.delivery.last_error_code = "EXTRACTION_HANDOFF_QUEUE_CONFLICT"
            handoff.delivery.last_error_message = "Conflicting queue item context exists for runtime job ID"
            handoff.updated_at = now_utc_iso()
            self.repository.save_handoff(handoff)
            raise ExtractionHandoffQueueConflictError(
                f"Conflicting queue item context exists for runtime job ID '{runtime_job_id}'"
            )

    def process_handoff(
        self,
        handoff: ExtractionRuntimeHandoff,
    ) -> ExtractionRuntimeHandoff:
        """Deliver handoff record to Runtime Prediction Queue with idempotency and self-healing."""
        if handoff.status == "enqueued":
            return handoff
        if handoff.status in ("blocked", "retry_exhausted"):
            return handoff

        # Check runtime prediction enablement
        if not PATHS.runtime_prediction_enabled:
            if handoff.status != "runtime_disabled":
                handoff.status = "runtime_disabled"
                handoff.updated_at = now_utc_iso()
                self.repository.save_handoff(handoff)
            return handoff

        # Compute deterministic runtime job ID
        runtime_job_id = compute_runtime_job_id(handoff.handoff_id)

        # 1. Check if queue item already exists in Runtime Queue
        try:
            existing_job = self._get_existing_queue_item(handoff=handoff, runtime_job_id=runtime_job_id)
        except PipelineQueuePersistError:
            return handoff

        if existing_job is not None:
            return self._validate_queue_context_and_heal(
                existing_job=existing_job,
                handoff=handoff,
                runtime_job_id=runtime_job_id,
            )

        # 2. Transition to enqueueing state before calling enqueue
        handoff.status = "enqueueing"
        handoff.delivery.runtime_job_id = runtime_job_id
        handoff.updated_at = now_utc_iso()
        self.repository.save_handoff(handoff)

        # 3. Construct canonical RuntimeInputIdentity and call PipelineManager.enqueue
        try:
            runtime_input = RuntimeInputIdentity(
                dataset_id=handoff.runtime_input.dataset_id,
                dataset_version=handoff.runtime_input.dataset_version,
                source=RuntimeSourceContext(
                    source_uri=handoff.runtime_input.source.source_uri,
                    source_checksum=handoff.runtime_input.source.source_checksum,
                    source_kind=handoff.runtime_input.source.source_kind,
                    source_contract_version=handoff.runtime_input.source.source_contract_version,
                    source_schema_version=handoff.runtime_input.source.source_schema_version,
                    pipeline_contract_version=handoff.runtime_input.source.pipeline_contract_version,
                    lineage=PredictionResultLineage.model_validate(
                        handoff.runtime_input.source.lineage.model_dump()
                        if hasattr(handoff.runtime_input.source.lineage, "model_dump")
                        else (handoff.runtime_input.source.lineage or {})
                    ),
                ),
            )

            queue_item = self.pipeline_manager.enqueue(
                job_id=runtime_job_id,
                runtime_input=runtime_input,
                size_bytes=handoff.dataset.observations_size_bytes,
            )

            # 4. Transition to enqueued
            handoff.status = "enqueued"
            handoff.delivery.runtime_job_id = runtime_job_id
            handoff.delivery.queue_item_id = queue_item.job_id
            handoff.delivery.last_error_code = None
            handoff.delivery.last_error_message = None
            handoff.updated_at = now_utc_iso()
            self.repository.save_handoff(handoff)
            logger.info(f"[ExtractionRuntimeHandoffService] Successfully enqueued handoff {handoff.handoff_id} as job {runtime_job_id}")
            return handoff

        except Exception as exc:
            if isinstance(exc, (PipelineSourceAlreadyRegisteredError, PipelineDuplicateInputError)):
                try:
                    existing_job = self._get_existing_queue_item(handoff=handoff, runtime_job_id=runtime_job_id)
                except PipelineQueuePersistError:
                    return handoff
                if existing_job is not None:
                    return self._validate_queue_context_and_heal(
                        existing_job=existing_job,
                        handoff=handoff,
                        runtime_job_id=runtime_job_id,
                    )

            err_code = getattr(exc, "code", "EXTRACTION_HANDOFF_ENQUEUE_FAILED")
            err_msg = str(exc)
            retryable = getattr(exc, "retryable", True)

            handoff.delivery.last_error_code = err_code
            handoff.delivery.last_error_message = err_msg
            handoff.updated_at = now_utc_iso()

            if retryable:
                handoff.delivery.attempt_count += 1
                if handoff.delivery.attempt_count >= PATHS.extraction_handoff_max_retries:
                    handoff.status = "retry_exhausted"
                    handoff.delivery.last_error_code = "EXTRACTION_HANDOFF_RETRY_EXHAUSTED"
                    logger.error(
                        f"[ExtractionRuntimeHandoffService] Handoff {handoff.handoff_id} exceeded max retries ({PATHS.extraction_handoff_max_retries}). Status -> retry_exhausted."
                    )
                else:
                    handoff.status = "retry_wait"
                    logger.warning(
                        f"[ExtractionRuntimeHandoffService] Retryable enqueue error for handoff {handoff.handoff_id} (attempt {handoff.delivery.attempt_count}/{PATHS.extraction_handoff_max_retries}): {err_code} - {err_msg}"
                    )
            else:
                handoff.status = "blocked"
                logger.error(
                    f"[ExtractionRuntimeHandoffService] Non-retryable error for handoff {handoff.handoff_id}: {err_code} - {err_msg}. Status -> blocked."
                )

            self.repository.save_handoff(handoff)
            if not retryable:
                raise
            return handoff

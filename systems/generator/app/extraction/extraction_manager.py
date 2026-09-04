"""Extraction Manager Singleton coordinating Background Worker, Source Queues, and Extraction Pipelines."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from systems.generator.generator_config import PATHS, PROJECT_ROOT
from systems.generator.app.extraction.checkpoint_repository import (
    GenDataExtractionCheckpointRepository,
)
from systems.generator.app.extraction.extraction_exception import (
    ExtractionConfigurationInvalidError,
    ExtractionError,
    ExtractionMappingConfigurationMissingError,
    ExtractionMappingNotFoundError,
    ExtractionRetryExhaustedError,
    ExtractionSourceNotFoundError,
)
from systems.generator.app.extraction.extraction_handoff_repository import (
    ExtractionHandoffRepository,
)
from systems.generator.app.extraction.extraction_runtime_handoff_service import (
    ExtractionRuntimeHandoffService,
)
from systems.generator.app.extraction.extraction_schema import (
    ExtractionManagerStatus,
    ExtractionSourceStatus,
    GenDataExtractionRequest,
    GenDataExtractionResponse,
    PublishedDatasetSummary,
    RuntimeHandoffStatusSummary,
    SourceProcessingResult,
)
from systems.generator.app.extraction.fragment_lifecycle import (
    GenDataFragmentLifecycleManager,
)
from systems.generator.app.extraction.gen_data_fragment import (
    GenDataFragmentRepository,
)
from systems.generator.app.extraction.gen_data_identity import (
    compute_gen_data_source_identity,
)
from systems.generator.app.extraction.gen_data_incremental_service import (
    GenDataIncrementalExtractionService,
)
from systems.generator.app.extraction.gen_data_source import (
    GenDataSensorStreamSource,
    discover_gen_data_sensor_streams,
)
from systems.generator.app.extraction.mapping_repository import (
    MappingRepository,
)
from systems.generator.app.extraction.mapping_validator import (
    compute_mapping_canonical_sha256,
)
from systems.generator.app.extraction.window_publish_service import (
    ExtractionWindowPublishService,
)

logger = logging.getLogger(__name__)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExtractionManager:
    """Process-level Singleton managing state, queues, background worker, and API extraction execution."""

    _instance: Optional[ExtractionManager] = None

    def __init__(
        self,
        checkpoint_repo: Optional[GenDataExtractionCheckpointRepository] = None,
        fragment_repo: Optional[GenDataFragmentRepository] = None,
        mapping_repo: Optional[MappingRepository] = None,
        incremental_service: Optional[GenDataIncrementalExtractionService] = None,
        publish_service: Optional[ExtractionWindowPublishService] = None,
        lifecycle_mgr: Optional[GenDataFragmentLifecycleManager] = None,
        handoff_repo: Optional[ExtractionHandoffRepository] = None,
        handoff_service: Optional[ExtractionRuntimeHandoffService] = None,
        lock_dir: Optional[Path] = None,
    ) -> None:
        self.checkpoint_repo = checkpoint_repo or GenDataExtractionCheckpointRepository()
        self.fragment_repo = fragment_repo or GenDataFragmentRepository()
        self.mapping_repo = mapping_repo or MappingRepository()
        self.lock_dir = lock_dir or (PATHS.data_preprocessed / "extraction_locks")
        self.incremental_service = incremental_service or GenDataIncrementalExtractionService(
            checkpoint_repo=self.checkpoint_repo,
            fragment_repo=self.fragment_repo,
            lock_dir=self.lock_dir,
        )
        self.lifecycle_mgr = lifecycle_mgr or GenDataFragmentLifecycleManager(
            fragment_repo=self.fragment_repo,
        )
        self.publish_service = publish_service or ExtractionWindowPublishService(
            fragment_repo=self.fragment_repo,
            lifecycle_mgr=self.lifecycle_mgr,
        )
        self.handoff_repo = handoff_repo or ExtractionHandoffRepository()
        self.handoff_service = handoff_service or ExtractionRuntimeHandoffService(
            repository=self.handoff_repo
        )

        self._source_states: dict[str, ExtractionSourceStatus] = {}
        self._source_async_locks: dict[str, asyncio.Lock] = {}
        self._global_semaphore = asyncio.Semaphore(PATHS.extraction_max_concurrency)

        self._worker: Optional[Any] = None
        self._handoff_worker: Optional[Any] = None
        self._last_poll_started_at: Optional[str] = None
        self._last_poll_completed_at: Optional[str] = None

    @classmethod
    def get_instance(cls) -> ExtractionManager:
        if cls._instance is None:
            cls._instance = ExtractionManager()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: Optional[ExtractionManager]) -> None:
        cls._instance = instance

    @property
    def enabled(self) -> bool:
        return PATHS.extraction_enabled

    @property
    def running(self) -> bool:
        worker_running = self._worker is not None and getattr(self._worker, "is_running", False)
        handoff_running = self._handoff_worker is not None and getattr(self._handoff_worker, "is_running", False)
        return worker_running or handoff_running

    async def start(self) -> None:
        """Start background extraction worker and handoff worker if enabled."""
        PATHS.validate_extraction_config()

        # 1. Extraction Polling Worker
        if self.enabled and (self._worker is None or not getattr(self._worker, "is_running", False)):
            from systems.generator.app.extraction.extraction_worker import ExtractionWorker

            self._worker = ExtractionWorker(manager=self)
            await self._worker.start()
            logger.info("[ExtractionManager] Background extraction worker started.")
        elif not self.enabled:
            logger.info("[ExtractionManager] Background extraction worker is disabled by configuration.")

        # 2. Runtime Handoff Worker
        if PATHS.extraction_runtime_handoff_enabled and (
            self._handoff_worker is None or not getattr(self._handoff_worker, "is_running", False)
        ):
            from systems.generator.app.extraction.extraction_handoff_worker import (
                ExtractionHandoffWorker,
            )

            self._handoff_worker = ExtractionHandoffWorker(service=self.handoff_service)
            await self._handoff_worker.start()
            logger.info("[ExtractionManager] Background handoff worker started.")
        elif not PATHS.extraction_runtime_handoff_enabled:
            logger.info("[ExtractionManager] Background handoff worker is disabled by configuration.")

    async def stop(self) -> None:
        """Stop background extraction worker and handoff worker if running."""
        if self._worker is not None:
            await self._worker.stop()
            self._worker = None
            logger.info("[ExtractionManager] Background extraction worker stopped.")

        if self._handoff_worker is not None:
            await self._handoff_worker.stop()
            self._handoff_worker = None
            logger.info("[ExtractionManager] Background handoff worker stopped.")

    def get_source_lock(self, key: str) -> asyncio.Lock:
        if key not in self._source_async_locks:
            self._source_async_locks[key] = asyncio.Lock()
        return self._source_async_locks[key]

    def get_status(self) -> ExtractionManagerStatus:
        """Return current status of ExtractionManager, tracked sources, and runtime handoff queue."""
        sources_list = list(self._source_states.values())
        discovered = len(sources_list)
        queued = sum(1 for s in sources_list if s.status == "queued")
        processing = sum(1 for s in sources_list if s.status == "processing")
        blocked = sum(1 for s in sources_list if s.status == "blocked")

        # Handoff counts
        handoff_counts = self.handoff_repo.count_by_status()
        handoff_summary = RuntimeHandoffStatusSummary(
            enabled=PATHS.extraction_runtime_handoff_enabled,
            runtime_prediction_enabled=PATHS.runtime_prediction_enabled,
            pending=handoff_counts.get("pending", 0),
            runtime_disabled=handoff_counts.get("runtime_disabled", 0),
            enqueueing=handoff_counts.get("enqueueing", 0),
            enqueued=handoff_counts.get("enqueued", 0),
            retry_wait=handoff_counts.get("retry_wait", 0),
            blocked=handoff_counts.get("blocked", 0),
            retry_exhausted=handoff_counts.get("retry_exhausted", 0),
        )

        return ExtractionManagerStatus(
            enabled=self.enabled,
            running=self.running,
            poll_interval_seconds=PATHS.extraction_poll_interval_seconds,
            discovered_source_count=discovered,
            queued_source_count=queued,
            processing_source_count=processing,
            blocked_source_count=blocked,
            last_poll_started_at=self._last_poll_started_at,
            last_poll_completed_at=self._last_poll_completed_at,
            sources=sources_list,
            runtime_handoff=handoff_summary,
        )

    def _resolve_mapping_data(
        self,
        mapping_id: Optional[str] = None,
        mapping_version: Optional[str] = None,
        mapping_sha256: Optional[str] = None,
    ) -> dict[str, Any]:
        """Resolve and validate approved static mapping table."""
        m_id = mapping_id or PATHS.extraction_mapping_id
        m_ver = mapping_version or PATHS.extraction_mapping_version
        m_sha = mapping_sha256 or PATHS.extraction_mapping_sha256

        # Try loading from mapping repository
        try:
            res = self.mapping_repo.load_mapping(m_id, m_ver)
            mapping_data = res[0] if isinstance(res, tuple) else res
        except Exception:
            mapping_data = None

        if mapping_data is None:
            raise ExtractionMappingNotFoundError(
                f"Mapping table '{m_id}/{m_ver}' not found in repository."
            )

        calc_sha = compute_mapping_canonical_sha256(mapping_data)
        if m_sha and calc_sha != m_sha:
            from systems.generator.app.extraction.extraction_exception import (
                ExtractionMappingChecksumMismatchError,
            )
            raise ExtractionMappingChecksumMismatchError(
                f"Mapping SHA-256 mismatch: expected '{m_sha}', computed '{calc_sha}'"
            )

        mapping_data["mapping_sha256"] = calc_sha
        return mapping_data

    async def process_source_once(
        self,
        *,
        source: GenDataSensorStreamSource,
        mapping_id: Optional[str] = None,
        mapping_version: Optional[str] = None,
        mapping_sha256: Optional[str] = None,
        flush_before: Optional[datetime] = None,
        run_id: Optional[str] = None,
        max_records: Optional[int] = None,
        mapping_data_override: Optional[dict[str, Any]] = None,
        raise_on_error: bool = False,
    ) -> SourceProcessingResult:
        """Process a single gen_data source incrementally with single-writer concurrency guarantee."""
        source_key = source.source_uri
        lock = self.get_source_lock(source_key)

        if lock.locked():
            logger.warning(f"[ExtractionManager] Source '{source_key}' is already locked/processing; skipping duplicate.")
            return SourceProcessingResult(
                source_uri=source.source_uri,
                source_identity=None,
                status="no_data",
                start_offset=0,
                committed_offset=0,
                records_read=0,
                observations_staged=0,
                rejected_staged=0,
                error_message="Source is currently processing",
            )

        async with lock:
            async with self._global_semaphore:
                effective_run_id = run_id or f"run-ext-{uuid4().hex[:12]}"
                now_str = now_utc_iso()

                state = self._source_states.get(
                    source_key,
                    ExtractionSourceStatus(
                        source_identity=None,
                        source_uri=source.source_uri,
                        site_id=source.site_id,
                        cell_id=source.cell_id,
                        status="processing",
                        last_started_at=now_str,
                    ),
                )
                state.status = "processing"
                state.last_started_at = now_str
                self._source_states[source_key] = state

                try:
                    # 1. Resolve mapping
                    if mapping_data_override:
                        mapping_data = mapping_data_override
                    else:
                        mapping_data = self._resolve_mapping_data(
                            mapping_id=mapping_id,
                            mapping_version=mapping_version,
                            mapping_sha256=mapping_sha256,
                        )

                    # 2. Incremental Parsing & Fragment Staging
                    inc_res = self.incremental_service.process_available_records(
                        source=source,
                        mapping_data=mapping_data,
                        run_id=effective_run_id,
                        max_records=max_records or PATHS.extraction_max_records,
                    )

                    state.source_identity = inc_res.source_identity
                    state.last_committed_offset = inc_res.committed_offset

                    if inc_res.status == "no_data":
                        state.status = "waiting"
                        state.last_succeeded_at = now_utc_iso()
                        state.attempt = 0
                        state.error_code = None
                        state.error_message = None
                        return SourceProcessingResult(
                            source_uri=source.source_uri,
                            source_identity=inc_res.source_identity,
                            status="no_data",
                            start_offset=inc_res.start_offset,
                            committed_offset=inc_res.committed_offset,
                            records_read=0,
                            observations_staged=0,
                            rejected_staged=0,
                        )

                    # 3. Window Dataset Publishing
                    pub_res = self.publish_service.publish_available_windows(
                        source_identity=inc_res.source_identity,
                        run_id=effective_run_id,
                        window_minutes=PATHS.extraction_window_minutes,
                        flush_before=flush_before,
                    )

                    pub_summaries = [
                        PublishedDatasetSummary(
                            dataset_id=ds.dataset_id,
                            dataset_version=ds.dataset_version,
                            manifest_uri=ds.manifest_uri,
                        )
                        for ds in pub_res.published_datasets
                    ]

                    # 4. Create Handoff Record and optionally deliver to Runtime Prediction Queue
                    for ds in pub_res.published_datasets:
                        try:
                            manifest_path = Path(ds.manifest_uri)
                            if not manifest_path.is_file():
                                manifest_path = PROJECT_ROOT / ds.manifest_uri
                            if not manifest_path.is_file():
                                manifest_path = (PATHS.data_dir / "observations" / ds.dataset_id / ds.dataset_version / "dataset_manifest.json").resolve()
                            handoff = self.handoff_service.create_or_get_handoff(manifest_path)
                            if PATHS.extraction_runtime_handoff_enabled and PATHS.runtime_prediction_enabled:
                                self.handoff_service.process_handoff(handoff)
                        except Exception as h_exc:
                            logger.error(
                                f"[ExtractionManager] Handoff creation/processing failed for dataset '{ds.dataset_id}/{ds.dataset_version}': {h_exc}"
                            )

                    if pub_summaries:
                        state.last_published_window = pub_summaries[-1].dataset_version

                    state.status = "waiting"
                    state.last_succeeded_at = now_utc_iso()
                    state.attempt = 0
                    state.error_code = None
                    state.error_message = None

                    return SourceProcessingResult(
                        source_uri=source.source_uri,
                        source_identity=inc_res.source_identity,
                        status="succeeded",
                        start_offset=inc_res.start_offset,
                        committed_offset=inc_res.committed_offset,
                        records_read=inc_res.records_read,
                        observations_staged=inc_res.observations_staged,
                        rejected_staged=inc_res.rejected_staged,
                        published_datasets=pub_summaries,
                        pending_windows=pub_res.pending_window_ids,
                    )

                except Exception as exc:
                    err_code = getattr(exc, "code", "EXTRACTION_UNEXPECTED_ERROR")
                    retryable = getattr(exc, "retryable", False)
                    err_msg = str(exc)

                    state.last_failed_at = now_utc_iso()
                    state.error_code = err_code
                    state.error_message = err_msg
                    state.retryable = retryable

                    if retryable:
                        state.attempt += 1
                        if state.attempt >= PATHS.extraction_max_attempts:
                            state.status = "failed"
                            state.error_code = "EXTRACTION_RETRY_EXHAUSTED"
                            logger.error(
                                f"[ExtractionManager] Source '{source_key}' exceeded max retry attempts ({PATHS.extraction_max_attempts}). Status -> failed."
                            )
                        else:
                            state.status = "queued"
                            logger.warning(
                                f"[ExtractionManager] Retryable error for source '{source_key}' (attempt {state.attempt}/{PATHS.extraction_max_attempts}): {err_code} - {err_msg}"
                            )
                    else:
                        state.status = "blocked"
                        logger.error(
                            f"[ExtractionManager] Non-retryable error for source '{source_key}': {err_code} - {err_msg}. Status -> blocked."
                        )

                    if raise_on_error:
                        raise

                    return SourceProcessingResult(
                        source_uri=source.source_uri,
                        source_identity=state.source_identity,
                        status="blocked" if state.status == "blocked" else "failed",
                        start_offset=state.last_committed_offset,
                        committed_offset=state.last_committed_offset,
                        records_read=0,
                        observations_staged=0,
                        rejected_staged=0,
                        error_code=state.error_code,
                        error_message=err_msg,
                    )

    async def execute_request(
        self,
        request_body: GenDataExtractionRequest,
        request_id: str,
    ) -> GenDataExtractionResponse:
        """Execute extraction manually on demand via POST /extraction."""
        run_id = f"run-api-{uuid4().hex[:12]}"
        sensor_root = PATHS.gen_data_sensor_root or (PATHS.gen_data_output_dir / "sensor" if PATHS.gen_data_output_dir else None)

        if not sensor_root or not sensor_root.exists():
            from systems.generator.app.extraction.extraction_exception import (
                ExtractionGenDataRootNotConfiguredError,
            )
            raise ExtractionGenDataRootNotConfiguredError(
                f"gen_data sensor root directory not found or not configured: {sensor_root}"
            )

        discovered = discover_gen_data_sensor_streams(sensor_root)
        if not discovered:
            return GenDataExtractionResponse(
                request_id=request_id,
                run_id=run_id,
                status="no_data",
                processed_sources=0,
                succeeded_sources=0,
                failed_sources=0,
                sources=[],
            )

        target_sources: list[GenDataSensorStreamSource] = []
        is_single_source_request = bool(request_body.source_uri)
        if request_body.source_uri:
            clean_uri = request_body.source_uri.strip().replace("\\", "/")
            matched = [s for s in discovered if s.source_uri == clean_uri]
            if not matched:
                raise ExtractionSourceNotFoundError(
                    f"Requested source_uri '{clean_uri}' was not found under sensor root."
                )
            target_sources = matched
        else:
            target_sources = discovered

        results: list[SourceProcessingResult] = []
        succeeded_count = 0
        failed_count = 0

        for src in target_sources:
            res = await self.process_source_once(
                source=src,
                mapping_id=request_body.mapping_id,
                mapping_version=request_body.mapping_version,
                mapping_sha256=request_body.mapping_sha256,
                flush_before=request_body.flush_before,
                run_id=run_id,
                max_records=request_body.max_records,
                raise_on_error=is_single_source_request,
            )
            results.append(res)
            if res.status == "succeeded":
                succeeded_count += 1
            elif res.status in ("failed", "blocked"):
                failed_count += 1

        overall_status = "no_data"
        if succeeded_count > 0 and failed_count == 0:
            overall_status = "succeeded"
        elif succeeded_count > 0 and failed_count > 0:
            overall_status = "partially_succeeded"
        elif failed_count > 0:
            overall_status = "partially_succeeded" if succeeded_count > 0 else "no_data"

        return GenDataExtractionResponse(
            request_id=request_id,
            run_id=run_id,
            status=overall_status,
            processed_sources=len(target_sources),
            succeeded_sources=succeeded_count,
            failed_sources=failed_count,
            sources=results,
        )


def get_extraction_manager() -> ExtractionManager:
    """Return the global ExtractionManager singleton instance."""
    return ExtractionManager.get_instance()

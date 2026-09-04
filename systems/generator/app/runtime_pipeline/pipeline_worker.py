"""Single-consumer background worker processing FIFO queue items sequentially."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from systems.generator.generator_config import PATHS
from systems.generator.app.runtime_pipeline.pipeline_queue import PipelineQueue
from systems.generator.app.runtime_pipeline.pipeline_schema import PipelineQueueItem, PipelineRunState
from systems.generator.app.runtime_pipeline.pipeline_service import PipelineService

logger = logging.getLogger(__name__)


class PipelineWorker:
    """Single consumer background worker reading from PipelineQueue with exponential backoff retry."""

    def __init__(
        self,
        queue: PipelineQueue,
        service: PipelineService,
        poll_interval: float = 0.5,
        max_attempts: Optional[int] = None,
        retry_backoff_seconds: Optional[float] = None,
    ) -> None:
        self.queue = queue
        self.service = service
        self.poll_interval = poll_interval
        self.max_attempts = max_attempts or PATHS.pipeline_max_attempts
        self.retry_backoff_seconds = retry_backoff_seconds or PATHS.pipeline_retry_backoff_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._current_job: Optional[PipelineQueueItem] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the single consumer background worker thread."""
        if not PATHS.runtime_prediction_enabled:
            logger.info("[PipelineWorker] Runtime Prediction is disabled. Worker start skipped.")
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, name="PipelineWorkerThread", daemon=True)
            self._thread.start()
            logger.info("[PipelineWorker] Background worker started")

    def stop(self, timeout: float = 10.0) -> None:
        """Signal stop and wait for current job to complete."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            logger.info("[PipelineWorker] Background worker stopped")

    def process_one(self) -> Optional[PipelineRunState]:
        """Claim and process a single item from the queue (synchronous execution)."""
        if not PATHS.runtime_prediction_enabled:
            logger.info("[PipelineWorker] Runtime Prediction is disabled. Skipping process_one.")
            return None
        item = self.queue.claim_next()
        if item is None:
            return None

        self._current_job = item
        try:
            logger.info(f"[PipelineWorker] Processing claimed job '{item.job_id}' (seq={item.sequence}, attempt={item.attempt})")
            run_state = self.service.execute_queue_item(item)
            self.queue.mark_succeeded(item.job_id)
            logger.info(f"[PipelineWorker] Completed job '{item.job_id}' with status '{run_state.status}'")
            return run_state
        except Exception as exc:
            err_code = getattr(exc, "code", "PIPELINE_ERROR")
            retryable = getattr(exc, "retryable", False)
            logger.exception(f"[PipelineWorker] Job '{item.job_id}' failed: {exc} (retryable={retryable}, attempt={item.attempt})")
            if retryable and item.attempt < self.max_attempts:
                backoff = self.retry_backoff_seconds * (2 ** (item.attempt - 1))
                logger.info(f"[PipelineWorker] Retrying job '{item.job_id}' in {backoff:.1f}s (next attempt={item.attempt + 1})")
                time.sleep(backoff)
                self.queue.mark_retry_wait(item.job_id, error_code=err_code)
            else:
                self.queue.mark_failed(item.job_id, error_code=err_code, dead_letter=False)
            return None
        finally:
            self._current_job = None

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = self.process_one()
                if processed is None:
                    time.sleep(self.poll_interval)
            except Exception as exc:
                logger.error(f"[PipelineWorker] Error in worker loop: {exc}")
                time.sleep(self.poll_interval)

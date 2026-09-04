"""Background worker dedicated solely to delivering Prediction Result Batches from Outbox."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, TYPE_CHECKING

from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
    PredictionDeliveryService,
)
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    PredictionOutboxItem,
    now_utc_iso,
)

if TYPE_CHECKING:
    from systems.generator.app.runtime_pipeline.pipeline_repository import PipelineRepository

logger = logging.getLogger(__name__)


class PredictionDeliveryWorker:
    """Dedicated background worker polling Outbox and executing retries without re-running pipeline."""

    def __init__(
        self,
        service: PredictionDeliveryService,
        repository: Optional[PipelineRepository] = None,
        poll_interval: float = 0.5,
        max_attempts: int = 5,
    ) -> None:
        self.service = service
        self.repository = repository
        self.poll_interval = poll_interval
        self.max_attempts = max_attempts
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def recover_interrupted_items(self) -> int:
        """Startup recovery hook: recover any outbox items left in 'sending' state due to prior shutdown."""
        items = self.service.list_outbox_items(status="sending")
        recovered_count = 0
        now_str = datetime.now(timezone.utc).isoformat()

        for item in items:
            item.status = "retry_wait"
            item.last_error_code = "PIPELINE_DELIVERY_INTERRUPTED"
            item.last_error_message = "배치 전송 도중 시스템 재시작/종료로 인해 중단되어 자동 복구되었습니다."
            item.next_retry_at = now_str
            self.service.save_outbox_item(item)

            if self.repository is not None and item.run_id:
                try:
                    self.repository.update_prediction_event(
                        run_id=item.run_id,
                        event_id=item.event_id,
                        asset_id=item.asset_id,
                        status="retry_wait",
                        attempt=item.attempt,
                        max_attempts=item.max_attempts,
                        next_retry_at=item.next_retry_at,
                        last_error_code=item.last_error_code,
                        last_error_message=item.last_error_message,
                    )
                except Exception as r_exc:
                    logger.warning(f"[PredictionDeliveryWorker] Failed to sync recovered state for '{item.event_id}': {r_exc}")

            logger.info(
                f"[PredictionDeliveryWorker] Recovered interrupted outbox item '{item.event_id}' "
                f"(run_id='{item.run_id}', asset_id='{item.asset_id}') -> retry_wait"
            )
            recovered_count += 1

        return recovered_count

    def start(self) -> None:
        """Start the background delivery worker thread after running startup recovery."""
        from systems.generator.generator_config import PATHS
        if not PATHS.runtime_prediction_enabled:
            logger.info("[PredictionDeliveryWorker] Generator Runtime Prediction is disabled (GENERATOR_RUNTIME_PREDICTION_ENABLED=false). Skipping worker start.")
            return

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            recovered = self.recover_interrupted_items()
            if recovered > 0:
                logger.info(f"[PredictionDeliveryWorker] Recovered {recovered} interrupted 'sending' delivery item(s)")
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="PredictionDeliveryWorkerThread",
                daemon=True,
            )
            self._thread.start()
            logger.info("[PredictionDeliveryWorker] Background prediction delivery worker started")

    def stop(self, timeout: float = 10.0) -> None:
        """Signal stop and wait for thread to terminate."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            logger.info("[PredictionDeliveryWorker] Background prediction delivery worker stopped")

    def process_item(self, item: PredictionOutboxItem) -> bool:
        """Process a single outbox item through send_once and update outbox status & Run State."""
        logger.info(f"[PredictionDeliveryWorker] Delivering batch '{item.event_id}' (attempt={item.attempt + 1}/{item.max_attempts})")
        item.status = "sending"
        self.service.save_outbox_item(item)

        if self.repository is not None and item.run_id:
            try:
                self.repository.update_prediction_event(
                    run_id=item.run_id,
                    event_id=item.event_id,
                    asset_id=item.asset_id,
                    status="sending",
                    attempt=item.attempt,
                    max_attempts=item.max_attempts,
                    next_retry_at=None,
                    last_error_code=None,
                    last_error_message=None,
                )
            except Exception as exc:
                logger.warning(f"[PredictionDeliveryWorker] Failed to sync 'sending' state to repository: {exc}")

        try:
            self.service.send_once(item.payload)
            item.status = "sent"
            item.attempt += 1
            item.last_error_code = None
            item.last_error_message = None
            self.service.save_outbox_item(item)

            if self.repository is not None and item.run_id:
                try:
                    self.repository.update_prediction_event(
                        run_id=item.run_id,
                        event_id=item.event_id,
                        asset_id=item.asset_id,
                        status="sent",
                        attempt=item.attempt,
                        max_attempts=item.max_attempts,
                        next_retry_at=None,
                        last_error_code=None,
                        last_error_message=None,
                    )
                except Exception as exc:
                    logger.warning(f"[PredictionDeliveryWorker] Failed to sync 'sent' state to repository: {exc}")

            logger.info(f"[PredictionDeliveryWorker] Successfully delivered batch '{item.event_id}'")
            return True
        except Exception as exc:
            err_code = getattr(exc, "code", "PIPELINE_DELIVERY_FAILED")
            retryable = getattr(exc, "retryable", False)
            item.attempt += 1
            item.last_error_code = err_code
            item.last_error_message = str(exc)

            if retryable and item.attempt < item.max_attempts:
                backoff_seconds = float(2 ** (item.attempt - 1))  # 1s, 2s, 4s, 8s
                next_time = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
                item.status = "retry_wait"
                item.next_retry_at = next_time.isoformat()
                logger.warning(
                    f"[PredictionDeliveryWorker] Batch '{item.event_id}' delivery failed (retryable): {exc}. "
                    f"Scheduling retry in {backoff_seconds:.1f}s"
                )
            else:
                item.status = "failed"
                logger.error(
                    f"[PredictionDeliveryWorker] Batch '{item.event_id}' delivery failed permanently (retryable={retryable}, attempt={item.attempt}): {exc}"
                )

            self.service.save_outbox_item(item)

            if self.repository is not None and item.run_id:
                try:
                    self.repository.update_prediction_event(
                        run_id=item.run_id,
                        event_id=item.event_id,
                        asset_id=item.asset_id,
                        status=item.status,
                        attempt=item.attempt,
                        max_attempts=item.max_attempts,
                        next_retry_at=item.next_retry_at,
                        last_error_code=item.last_error_code,
                        last_error_message=item.last_error_message,
                    )
                except Exception as r_exc:
                    logger.warning(f"[PredictionDeliveryWorker] Failed to sync failure state to repository: {r_exc}")

            return False

    @staticmethod
    def _is_ready(item: PredictionOutboxItem, now_dt: datetime) -> bool:
        if item.status == "pending":
            return True
        if item.status != "retry_wait":
            return False
        if not item.next_retry_at:
            return True
        try:
            due_dt = datetime.fromisoformat(item.next_retry_at)
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=timezone.utc)
            return now_dt >= due_dt
        except (TypeError, ValueError):
            return True

    def _ordered_ready_items(
        self,
        items: list[PredictionOutboxItem],
        now_dt: datetime,
    ) -> tuple[list[PredictionOutboxItem], set[str]]:
        """Promote one ready result per not-yet-delivered maintenance event."""
        delivered_maintenance_events = {
            maintenance_event_id
            for item in items
            if item.status == "sent"
            if (
                maintenance_event_id := self.service.maintenance_event_id(item)
            ) is not None
        }
        ready = sorted(
            (item for item in items if self._is_ready(item, now_dt)),
            key=lambda item: (item.created_at, item.event_id),
        )
        promoted: list[PredictionOutboxItem] = []
        regular: list[PredictionOutboxItem] = []
        promoted_events: set[str] = set()
        for item in ready:
            maintenance_event_id = self.service.maintenance_event_id(item)
            if (
                maintenance_event_id is not None
                and maintenance_event_id not in delivered_maintenance_events
                and maintenance_event_id not in promoted_events
            ):
                promoted.append(item)
                promoted_events.add(maintenance_event_id)
            else:
                regular.append(item)
        return promoted + regular, delivered_maintenance_events

    def process_pending(self) -> int:
        """Process ready items while allowing first replay results to preempt backlog.

        Only one result per not-yet-delivered maintenance event is promoted.
        Subsequent snapshots preserve creation-order FIFO. A lightweight
        in-process signal interrupts a stale live backlog snapshot when a new
        maintenance event arrives, avoiding a full outbox rescan after every
        ordinary delivery.
        """
        from systems.generator.generator_config import PATHS
        if not PATHS.runtime_prediction_enabled:
            return 0
        # Clear signals for records already persisted before this snapshot.
        # Registrations racing after this point remain visible to the loop.
        self.service.consume_pending_maintenance_event_ids()
        items = self.service.list_outbox_items()
        ordered_items, delivered_maintenance_events = self._ordered_ready_items(
            items,
            datetime.now(timezone.utc),
        )
        processed_count = 0

        for item in ordered_items:
            delivered = self.process_item(item)
            processed_count += 1
            maintenance_event_id = self.service.maintenance_event_id(item)
            if delivered and maintenance_event_id is not None:
                delivered_maintenance_events.add(maintenance_event_id)

            newly_registered = self.service.consume_pending_maintenance_event_ids()
            if newly_registered - delivered_maintenance_events:
                logger.info(
                    "[PredictionDeliveryWorker] New maintenance replay result "
                    "registered; refreshing delivery order before draining the "
                    "remaining live backlog"
                )
                break

        return processed_count

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = self.process_pending()
                if processed == 0:
                    time.sleep(self.poll_interval)
            except Exception as exc:
                logger.error(f"[PredictionDeliveryWorker] Error in worker loop: {exc}")
                time.sleep(self.poll_interval)

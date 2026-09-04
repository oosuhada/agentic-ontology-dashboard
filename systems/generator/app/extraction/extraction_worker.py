"""Background Polling Worker discovering gen_data streams and driving incremental extraction."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from systems.generator.generator_config import PATHS
from systems.generator.app.extraction.extraction_exception import (
    ExtractionSourceTruncatedError,
)
from systems.generator.app.extraction.extraction_manager import (
    ExtractionManager,
    now_utc_iso,
)
from systems.generator.app.extraction.gen_data_source import (
    GenDataSensorStreamSource,
    discover_gen_data_sensor_streams,
)

logger = logging.getLogger(__name__)


class ExtractionWorker:
    """Asynchronous background worker polling gen_data sensor streams at fixed intervals."""

    def __init__(
        self,
        manager: ExtractionManager,
        poll_interval_seconds: Optional[float] = None,
        max_concurrency: Optional[int] = None,
    ) -> None:
        self.manager = manager
        self.poll_interval = (
            poll_interval_seconds
            if poll_interval_seconds is not None
            else PATHS.extraction_poll_interval_seconds
        )
        self.max_concurrency = max_concurrency or PATHS.extraction_max_concurrency

        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def start(self) -> None:
        """Start background polling loop."""
        if self._is_running:
            return
        self._stop_event.clear()
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"[ExtractionWorker] Polling loop started with interval={self.poll_interval}s")

    async def stop(self, timeout: float = 10.0) -> None:
        """Stop background polling loop gracefully."""
        if not self._is_running:
            return
        logger.info("[ExtractionWorker] Stopping polling worker...")
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning("[ExtractionWorker] Task timed out waiting for stop; cancelling task.")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
        self._is_running = False
        logger.info("[ExtractionWorker] Polling worker stopped.")

    async def run_single_cycle(self) -> None:
        """Execute a single scan and process cycle for all discovered sources."""
        cycle_id = f"extraction-cycle-{uuid4().hex[:12]}"
        now_start = now_utc_iso()
        self.manager._last_poll_started_at = now_start

        sensor_root = (
            PATHS.gen_data_sensor_root
            or (PATHS.gen_data_output_dir / "sensor" if PATHS.gen_data_output_dir else None)
        )
        if not sensor_root or not sensor_root.is_dir():
            logger.debug(f"[ExtractionWorker] Sensor root does not exist: '{sensor_root}'; cycle skipped.")
            self.manager._last_poll_completed_at = now_utc_iso()
            return

        try:
            discovered = discover_gen_data_sensor_streams(sensor_root)
        except Exception as exc:
            logger.error(f"[ExtractionWorker] Failed to discover sensor streams: {exc}")
            self.manager._last_poll_completed_at = now_utc_iso()
            return

        active_tasks = []
        for source in discovered:
            if self._stop_event.is_set():
                break

            source_key = source.source_uri
            state = self.manager._source_states.get(source_key)

            # Blocked sources or exhausted retries are skipped
            if state and state.status in ("blocked", "failed"):
                continue

            # Fast change detection
            try:
                file_size = source.source_path.stat().st_size
            except OSError as e:
                logger.warning(f"[ExtractionWorker] Cannot stat file '{source.source_path}': {e}")
                continue

            last_offset = state.last_committed_offset if state else 0

            # Check if file shrunk
            if file_size < last_offset:
                logger.error(
                    f"[ExtractionWorker] File '{source.source_uri}' was truncated (size {file_size} < offset {last_offset})."
                )
                if state:
                    state.status = "blocked"
                    state.error_code = "EXTRACTION_SOURCE_TRUNCATED"
                    state.error_message = f"File size ({file_size}) is smaller than committed offset ({last_offset})"
                    state.retryable = False
                continue

            # Check if new records available
            if file_size > last_offset:
                active_tasks.append(
                    self.manager.process_source_once(
                        source=source,
                        run_id=cycle_id,
                    )
                )

        if active_tasks:
            # Process with bounded concurrency
            await asyncio.gather(*active_tasks, return_exceptions=True)

        self.manager._last_poll_completed_at = now_utc_iso()

    async def _run_loop(self) -> None:
        """Main async loop."""
        try:
            while not self._stop_event.is_set():
                try:
                    await self.run_single_cycle()
                except Exception as exc:
                    logger.error(f"[ExtractionWorker] Unhandled cycle error: {exc}", exc_info=True)

                if self._stop_event.is_set():
                    break

                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            self._is_running = False

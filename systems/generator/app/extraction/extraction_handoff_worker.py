"""Background Worker polling and delivering pending extraction handoffs to the Runtime Prediction Queue."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from systems.generator.generator_config import PATHS
from systems.generator.app.extraction.extraction_handoff_repository import (
    ExtractionHandoffRepository,
)
from systems.generator.app.extraction.extraction_runtime_handoff_service import (
    ExtractionRuntimeHandoffService,
)

logger = logging.getLogger(__name__)


class ExtractionHandoffWorker:
    """Asynchronous background worker delivering pending extraction handoffs to Runtime Prediction Queue."""

    def __init__(
        self,
        service: Optional[ExtractionRuntimeHandoffService] = None,
        poll_interval_seconds: Optional[float] = None,
        max_concurrency: Optional[int] = None,
    ) -> None:
        self.service = service or ExtractionRuntimeHandoffService()
        self.poll_interval = (
            poll_interval_seconds
            if poll_interval_seconds is not None
            else PATHS.extraction_handoff_poll_interval_seconds
        )
        self.max_concurrency = (
            max_concurrency
            if max_concurrency is not None
            else PATHS.extraction_handoff_max_concurrency
        )
        self._semaphore = asyncio.Semaphore(self.max_concurrency)

        self._stop_event = asyncio.Event()
        self._task: Optional[asyncio.Task[None]] = None
        self._is_running = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    async def start(self) -> None:
        """Start background handoff polling loop."""
        if self._is_running:
            return
        self._stop_event.clear()
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"[ExtractionHandoffWorker] Handoff worker started with interval={self.poll_interval}s")

    async def stop(self, timeout: float = 10.0) -> None:
        """Stop background handoff polling loop gracefully."""
        if not self._is_running:
            return
        logger.info("[ExtractionHandoffWorker] Stopping handoff worker...")
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                logger.warning("[ExtractionHandoffWorker] Task timed out waiting for stop; cancelling task.")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
        self._is_running = False
        logger.info("[ExtractionHandoffWorker] Handoff worker stopped.")

    async def run_single_cycle(self) -> None:
        """Scan and deliver pending, runtime_disabled, and retry_wait handoffs."""
        repo = self.service.repository

        candidates = (
            repo.list_handoffs("pending")
            + repo.list_handoffs("runtime_disabled")
            + repo.list_handoffs("retry_wait")
        )

        if not candidates:
            return

        async def _deliver_one(h):
            async with self._semaphore:
                try:
                    self.service.process_handoff(h)
                except Exception as exc:
                    logger.error(f"[ExtractionHandoffWorker] Failed to process handoff {h.handoff_id}: {exc}")

        tasks = [
            _deliver_one(h)
            for h in candidates
            if not self._stop_event.is_set()
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_loop(self) -> None:
        """Main async loop."""
        try:
            while not self._stop_event.is_set():
                try:
                    await self.run_single_cycle()
                except Exception as exc:
                    logger.error(f"[ExtractionHandoffWorker] Unhandled cycle error: {exc}", exc_info=True)

                if self._stop_event.is_set():
                    break

                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            self._is_running = False

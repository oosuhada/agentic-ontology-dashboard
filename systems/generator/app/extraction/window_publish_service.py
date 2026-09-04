"""End-to-end Orchestrator for UTC Window Assembly, Atomic Publishing, and Lifecycle Management."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel

from systems.generator.generator_config import PROJECT_ROOT
from systems.generator.app.extraction.fragment_lifecycle import (
    GenDataFragmentLifecycleManager,
)
from systems.generator.app.extraction.gen_data_fragment import (
    GenDataFragmentRepository,
)
from systems.generator.app.extraction.window_assembler import (
    ExtractionWindowAssembler,
)
from systems.generator.app.extraction.window_publisher import (
    ExtractionWindowPublisher,
    PublishedObservationDataset,
)

logger = logging.getLogger(__name__)


class WindowPublishResult(BaseModel):
    """Execution summary of an extraction window publish cycle."""

    source_identity: str
    run_id: str
    watermark: Optional[str] = None

    published_datasets: list[PublishedObservationDataset]
    pending_window_ids: list[str]

    fully_consumed_fragment_ids: list[str]
    retained_fragment_ids: list[str]

    status: Literal["no_publishable_window", "published", "partially_published"]


class ExtractionWindowPublishService:
    """Discovers pending fragments, groups closed UTC windows, publishes immutable datasets, and cleans up fragments."""

    def __init__(
        self,
        assembler: Optional[ExtractionWindowAssembler] = None,
        publisher: Optional[ExtractionWindowPublisher] = None,
        lifecycle_mgr: Optional[GenDataFragmentLifecycleManager] = None,
        fragment_repo: Optional[GenDataFragmentRepository] = None,
        runs_root: Optional[Path] = None,
    ) -> None:
        from systems.generator.generator_config import PATHS

        self.fragment_repo = fragment_repo or GenDataFragmentRepository()
        self.assembler = assembler or ExtractionWindowAssembler(fragment_repo=self.fragment_repo)
        self.publisher = publisher or ExtractionWindowPublisher()
        self.lifecycle_mgr = lifecycle_mgr or GenDataFragmentLifecycleManager(fragment_repo=self.fragment_repo)
        self.runs_root = Path(
            runs_root or (PATHS.data_preprocessed / "extraction_runs")
        ).resolve()

    def discover_fragments_for_source(self, source_identity: str) -> list[Path]:
        """Find all available fragment directories belonging to source_identity that are not fully consumed."""
        matched: list[Path] = []
        if not self.runs_root.is_dir():
            return matched

        for manifest_file in self.runs_root.glob("*/fragments/*/fragment_manifest.json"):
            frag_dir = manifest_file.parent
            try:
                manifest = self.fragment_repo.verify_fragment(frag_dir)
                if manifest.source_identity == source_identity:
                    if self.lifecycle_mgr.is_fully_consumed(manifest.batch_id):
                        continue
                    matched.append(frag_dir)
            except Exception as exc:
                logger.warning(f"[PublishService] Skipping invalid fragment '{frag_dir}': {exc}")

        return sorted(matched)

    def publish_available_windows(
        self,
        *,
        source_identity: str,
        run_id: str,
        window_minutes: int = 60,
        flush_before: Optional[datetime] = None,
        last_published_window_end: Optional[datetime] = None,
    ) -> WindowPublishResult:
        """Collect and publish all closed UTC windows for the given source."""
        fragment_dirs = self.discover_fragments_for_source(source_identity)
        if not fragment_dirs:
            return WindowPublishResult(
                source_identity=source_identity,
                run_id=run_id,
                watermark=None,
                published_datasets=[],
                pending_window_ids=[],
                fully_consumed_fragment_ids=[],
                retained_fragment_ids=[],
                status="no_publishable_window",
            )

        assembled_windows = self.assembler.collect_publishable_windows(
            source_identity=source_identity,
            fragment_dirs=fragment_dirs,
            window_minutes=window_minutes,
            flush_before=flush_before,
            last_published_window_end=last_published_window_end,
            run_id=run_id,
        )

        if not assembled_windows:
            return WindowPublishResult(
                source_identity=source_identity,
                run_id=run_id,
                watermark=None,
                published_datasets=[],
                pending_window_ids=[],
                fully_consumed_fragment_ids=[],
                retained_fragment_ids=[d.name for d in fragment_dirs],
                status="no_publishable_window",
            )

        # 1. Publish each assembled window
        published_list: list[PublishedObservationDataset] = []
        for win in assembled_windows:
            pub_ds = self.publisher.publish_window_dataset(win, run_id=run_id)
            published_list.append(pub_ds)

            # Update fragment consumption records
            for frag_ref in win.source_fragment_refs:
                self.lifecycle_mgr.record_window_publication(
                    batch_id=frag_ref.batch_id,
                    fragment_manifest_sha256=frag_ref.fragment_manifest_sha256,
                    all_referenced_windows=[win.dataset_version],
                    published_window=win.dataset_version,
                )

        # 2. Cleanup fully consumed fragments
        fully_consumed: list[str] = []
        retained: list[str] = []

        for f_dir in fragment_dirs:
            batch_id = f_dir.name
            try:
                cleaned = self.lifecycle_mgr.safe_cleanup_fragment(
                    fragment_dir=f_dir,
                    batch_id=batch_id,
                )
                if cleaned:
                    fully_consumed.append(batch_id)
                else:
                    retained.append(batch_id)
            except Exception as exc:
                logger.warning(f"[PublishService] Cleanup skipped for '{batch_id}': {exc}")
                retained.append(batch_id)

        status_str = "published" if not retained else "partially_published"

        return WindowPublishResult(
            source_identity=source_identity,
            run_id=run_id,
            watermark=published_list[-1].window_end if published_list else None,
            published_datasets=published_list,
            pending_window_ids=[],
            fully_consumed_fragment_ids=fully_consumed,
            retained_fragment_ids=retained,
            status=status_str,
        )

"""UTC Window and Dataset Identity calculations for Canonical Observation publishing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from systems.generator.app.extraction.extraction_exception import (
    ExtractionWindowConfigInvalidError,
)
from systems.generator.app.extraction.gen_data_mapping import normalize_strict_iso_utc


@dataclass(frozen=True)
class ExtractionWindow:
    """Represents a discrete half-open UTC window [window_start, window_end)."""

    window_start: datetime
    window_end: datetime
    window_id: str

    @property
    def window_start_iso(self) -> str:
        return self.window_start.strftime("%Y-%m-%dT%H:%M:%SZ")

    @property
    def window_end_iso(self) -> str:
        return self.window_end.strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_utc_window(
    observed_at: str,
    *,
    window_minutes: int = 60,
) -> ExtractionWindow:
    """Resolve an observed_at timestamp into its enclosing UTC half-open window [start, end).

    Invariants:
    - window_minutes must be a positive integer (rejects bool, float, string, non-positive).
    - Window interval is [window_start, window_end).
    """
    if isinstance(window_minutes, bool) or not isinstance(window_minutes, int) or window_minutes <= 0:
        raise ExtractionWindowConfigInvalidError(
            f"Invalid window_minutes configuration: expected positive integer, got {window_minutes!r}"
        )

    # Normalize observed_at and parse to UTC datetime
    norm_iso = normalize_strict_iso_utc(observed_at)
    dt = datetime.fromisoformat(norm_iso.replace("Z", "+00:00")).astimezone(timezone.utc)

    # Calculate aligned window start based on epoch seconds
    total_seconds = int(dt.timestamp())
    window_seconds = window_minutes * 60
    start_seconds = (total_seconds // window_seconds) * window_seconds

    window_start = datetime.fromtimestamp(start_seconds, tz=timezone.utc)
    window_end = window_start + timedelta(minutes=window_minutes)
    window_id = window_start.strftime("%Y%m%dT%H%M%SZ")

    return ExtractionWindow(
        window_start=window_start,
        window_end=window_end,
        window_id=window_id,
    )


def compute_window_dataset_identity(
    *,
    site_id: str,
    cell_id: str,
    window_start: datetime,
    mapping_sha256: str,
) -> tuple[str, str]:
    """Compute dataset_id and dataset_version for a UTC extraction window."""
    clean_site = site_id.strip()
    clean_cell = cell_id.strip()
    dataset_id = f"gen-data-{clean_site}-{clean_cell}"

    compact_start = window_start.strftime("%Y%m%dT%H%M%SZ")
    prefix_map_sha = mapping_sha256[:8]
    dataset_version = f"window-{compact_start}-map-{prefix_map_sha}"

    return dataset_id, dataset_version

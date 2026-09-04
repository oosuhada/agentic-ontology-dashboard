"""Public live-ingestion application boundary owned by Dataset."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class LiveDatasetIngestionPort(Protocol):
    def prepare_batch(
        self, *, stream_root: str | Path, active_overlay_assets: set[str]
    ) -> dict[str, Any]: ...
    def persist_batch(self, batch: dict[str, Any]) -> int: ...


__all__ = ["LiveDatasetIngestionPort"]

"""Application service for live predictive-maintenance worker orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.dataset.ports import LiveDatasetIngestionPort
from app.diagnosis.ports import LiveDiagnosisApplicationPort
from app.maintenance.ports import LiveMaintenanceOverlayPort
from app.ontology.ports import LiveOntologyProjectionPort



class LivePredictiveMaintenanceService:
    """Coordinate owner-domain application ports for one live worker cycle."""

    def __init__(
        self,
        *,
        dataset: LiveDatasetIngestionPort,
        diagnosis: LiveDiagnosisApplicationPort,
        maintenance: LiveMaintenanceOverlayPort,
        ontology: LiveOntologyProjectionPort,
    ) -> None:
        self.dataset = dataset
        self.diagnosis = diagnosis
        self.maintenance = maintenance
        self.ontology = ontology

    def ingest_once(self, *, stream_root: str | Path) -> dict[str, Any]:
        active_assets = self.maintenance.active_asset_ids(stream_root=stream_root)
        batch = self.dataset.prepare_batch(
            stream_root=stream_root,
            active_overlay_assets=active_assets,
        )
        ticks = batch["ticks"]
        if not ticks:
            overlay = self.maintenance.process_available(batch)
            return {
                **batch["summary"],
                "new_ticks": 0,
                "inserted_rows": 0,
                "active_overlay_assets": sorted(active_assets),
                "runtime_overlay": overlay,
            }
        inserted = self.dataset.persist_batch(batch)
        runtime = self.diagnosis.materialize_live_results(batch)
        overlay = self.maintenance.process_available(batch)
        ontology = self.ontology.materialize_live_projection(batch)
        return {
            **batch["summary"],
            "new_ticks": len(ticks),
            "inserted_rows": inserted,
            "latest_observed_at": ticks[-1][0].isoformat(),
            "active_overlay_assets": sorted(active_assets),
            "runtime_overlay": overlay,
            "runtime": runtime,
            "ontology": ontology,
        }


__all__ = [
    "LivePredictiveMaintenanceService",
]

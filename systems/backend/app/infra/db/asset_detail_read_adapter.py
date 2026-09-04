"""PostgreSQL-backed read adapter for the MVP AssetDetailViewModel."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.diagnosis.evidence import validate_product_result_artifact
from app.infra.db.diagnosis_runtime_repository import (
    PredictiveMaintenanceRuntimeRepository,
)


class PostgreSQLAssetDetailReadAdapter:
    """Read only governed runtime facts; never fall back to demo fixtures."""

    def __init__(self, repository: PredictiveMaintenanceRuntimeRepository) -> None:
        self.repository = repository

    def _latest_row(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        asset_id: str,
        dataset_version_id: str | None,
        event_id: str | None = None,
    ) -> dict[str, Any] | None:
        if event_id:
            row = self.repository.result_artifact_row(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                artifact_id=event_id,
            )
            if row is None:
                return None
            if dataset_version_id and str(row["dataset_version_id"]) != dataset_version_id:
                return None
            if str(row["asset_id"]) != asset_id:
                return None
            return row
        context = self.repository.resolve_version(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=dataset_version_id,
        )
        source_contract, _total, rows = self.repository.latest_result_rows(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            dataset_version_id=str(context["id"]),
            asset_id=asset_id,
            site_id=None,
            cell_id=None,
            asset_type=None,
            status_grade=None,
            offset=0,
            limit=1,
        )
        if source_contract != "result_artifact" or not rows:
            return None
        return rows[0]

    def asset_summary(self, **query: Any) -> dict[str, Any] | None:
        row = self._latest_row(**query)
        if row is None:
            return None
        return {
            "asset_id": str(row["asset_id"]),
            "asset_type": str(row["asset_type"]),
            "display_name": f"{str(row['asset_type']).upper()} · {row['asset_id']}",
            "site_id": str(row["site_id"]),
            "cell_id": str(row["cell_id"]),
            "observed_at": row["observed_at"].isoformat(),
            # pm_assets does not yet own a governed criticality attribute. Do
            # not rebrand the current risk band as Equipment master data.
            "criticality": None,
            "criticality_basis": [],
            "criticality_source": "unknown",
            "maintenance_context": {
                "last_maintenance_days_ago": None,
                "similar_events_30d": None,
                "open_work_order_exists": None,
            },
        }

    def latest_result_artifact(self, **query: Any) -> dict[str, Any] | None:
        row = self._latest_row(**query)
        if row is None:
            return None
        payload = row.get("prediction_result_payload")
        if not isinstance(payload, dict):
            return None
        validate_product_result_artifact(payload)
        for field in ("artifact_id", "asset_id", "asset_type", "schema_version"):
            if str(payload.get(field)) != str(row[field]):
                raise ValueError(
                    f"stored Product Result Artifact {field} does not match runtime index"
                )
        provenance = payload.get("provenance") or {}
        if str(provenance.get("prediction_id")) != str(row["prediction_id"]):
            raise ValueError(
                "stored Product Result Artifact prediction_id does not match runtime index"
            )
        # source_sha256 is the persistence index checksum, not a producer fact.
        # Enrich a copy so the stale-view guard can compare the exact row.
        artifact = dict(payload)
        artifact["source_sha256"] = str(row["source_sha256"])
        return artifact

    def feature_series(self, **query: Any) -> dict[str, dict[str, Any]]:
        rows = self.repository.observation_rows(
            organization_id=query["organization_id"],
            project_id=query["project_id"],
            workspace_id=query["workspace_id"],
            dataset_version_id=str(query["dataset_version_id"]),
            start=query["start"],
            end=query["end"],
            asset_id=query["asset_id"],
            site_id=None,
            cell_id=None,
            asset_type=None,
            grain=query["grain"],
            derived_measures={"power_w", "temperature_gap_k", "overstrain_load"},
            limit=5000,
        )
        series: dict[str, dict[str, Any]] = {}
        for row in rows:
            measurements = row.get("measurements") or {}
            derived = row.get("derived_measures") or {}
            for key, value in {**measurements, **derived}.items():
                target = series.setdefault(
                    str(key),
                    {
                        "source_ref": (
                            f"observation-query://{query['dataset_version_id']}/"
                            f"{query['asset_id']}/{key}"
                        ),
                        "points": [],
                    },
                )
                target["points"].append(
                    {
                        "observed_at": row["observed_at"].isoformat(),
                        "value": value,
                        "quality_status": "good",
                    }
                )
        return series

    def runtime_prediction_history(self, **query: Any) -> list[dict[str, Any]]:
        rows = self.repository.result_history_rows(
            organization_id=query["organization_id"],
            project_id=query["project_id"],
            workspace_id=query["workspace_id"],
            dataset_version_id=str(query["dataset_version_id"]),
            asset_id=query["asset_id"],
            start=query["start"],
            end=query["end"],
            limit=5000,
        )
        return [
            {
                "observed_at": row["observed_at"].isoformat(),
                "failure_probability": float(row["failure_probability"]),
                "status_grade": str(row["status_grade"]),
                "prediction_id": str(row["prediction_id"]),
                "source_kind": "runtime_inference",
                "source_ref": f"prediction-results://{row['artifact_id']}",
            }
            for row in rows
        ]

    def equipment_history(self, **_query: Any) -> list[dict[str, Any]]:
        # Closed-loop history remains owned by Maintenance. Returning no rows
        # makes that missing source explicit in the ViewModel evidence gaps.
        return []

    def data_status(self, **query: Any) -> dict[str, Any] | None:
        row = self._latest_row(**query)
        if row is None:
            return None
        created_at = row.get("created_at") or row.get("prediction_result_created_at")
        now = datetime.now(timezone.utc)
        is_stale = not isinstance(created_at, datetime) or now - created_at > timedelta(
            minutes=15
        )
        return {
            "source": "canonical",
            "is_stale": is_stale,
            "is_data_quality_hold": str(row.get("status_grade"))
            == "data_quality_hold",
            "last_updated_at": row["observed_at"].isoformat(),
            "warnings": [],
        }


__all__ = ["PostgreSQLAssetDetailReadAdapter"]

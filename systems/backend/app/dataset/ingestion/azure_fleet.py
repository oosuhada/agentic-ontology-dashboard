from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .ingestion_schema import DatasetManifest, QuarantinedRecord


class AzureFleetMaintenanceAdapter:
    """Normalize the public Azure predictive-maintenance CSV family.

    The adapter accepts the common ``datetime``, ``machineID`` and telemetry or
    event columns used by telemetry, errors, failures, maintenance and machines
    files. Metrics are always recalculated from ingested records; no presentation
    number is embedded in the adapter.
    """

    code = "azure-fleet-maintenance"
    display_name = "Azure Fleet Maintenance"

    _timestamp_aliases = ("datetime", "timestamp", "observed_at")
    _machine_aliases = ("machineID", "machine_id", "equipment_id")

    def required_fields(self, manifest: DatasetManifest) -> set[str]:
        return set(manifest.schema_.required_fields)

    @staticmethod
    def _first(record: dict[str, str], aliases: tuple[str, ...]) -> str | None:
        for alias in aliases:
            value = record.get(alias)
            if value is not None and str(value).strip() != "":
                return str(value).strip()
        return None

    @staticmethod
    def _datetime(value: str) -> datetime:
        normalized = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _number(value: str | None) -> float | None:
        if value is None or str(value).strip() == "":
            return None
        return float(value)

    def normalize_record(
        self,
        record: dict[str, str],
        *,
        manifest: DatasetManifest,
        row_number: int,
    ) -> dict[str, Any] | QuarantinedRecord:
        timestamp = self._first(record, self._timestamp_aliases)
        machine_id = self._first(record, self._machine_aliases)
        if not timestamp or not machine_id:
            return QuarantinedRecord(
                source_row_number=row_number,
                error_code="azure.required_field_missing",
                error_message="datetime/timestamp and machineID are required",
                record=dict(record),
            )
        try:
            observed_at = self._datetime(timestamp)
            numeric = {
                field: self._number(record.get(field))
                for field in ("volt", "rotate", "pressure", "vibration", "age")
                if field in record
            }
        except (TypeError, ValueError) as exc:
            return QuarantinedRecord(
                source_row_number=row_number,
                error_code="azure.type_conversion_failed",
                error_message=str(exc),
                record=dict(record),
            )

        event_type = "telemetry"
        event_value: str | None = None
        for field, kind in (
            ("errorID", "error"),
            ("failure", "failure"),
            ("comp", "maintenance"),
            ("model", "machine"),
        ):
            value = record.get(field)
            if value is not None and str(value).strip() != "":
                event_type = kind
                event_value = str(value).strip()
                break
        return {
            "record_type": event_type,
            "machine_id": machine_id,
            "observed_at": observed_at.isoformat(),
            "event_value": event_value,
            "measurements": numeric,
            "source": {key: value for key, value in record.items() if value not in {None, ""}},
        }

    def derive_metrics(
        self,
        records: list[dict[str, Any]],
        *,
        manifest: DatasetManifest,
    ) -> dict[str, Any]:
        failures = [item for item in records if item["record_type"] == "failure"]
        errors = [item for item in records if item["record_type"] == "error"]
        maintenance = [item for item in records if item["record_type"] == "maintenance"]
        failure_times: dict[str, list[datetime]] = {}
        for item in failures:
            failure_times.setdefault(item["machine_id"], []).append(
                datetime.fromisoformat(item["observed_at"])
            )
        conversions: dict[str, dict[str, int]] = {}
        for item in errors:
            error_type = item.get("event_value") or "unknown"
            bucket = conversions.setdefault(error_type, {"errors": 0, "failure_within_24h": 0})
            bucket["errors"] += 1
            observed = datetime.fromisoformat(item["observed_at"])
            if any(
                observed <= failure_at <= observed + timedelta(hours=24)
                for failure_at in failure_times.get(item["machine_id"], [])
            ):
                bucket["failure_within_24h"] += 1
        conversion_rates = {
            error_type: {
                **counts,
                "conversion_rate": (
                    counts["failure_within_24h"] / counts["errors"] if counts["errors"] else 0.0
                ),
            }
            for error_type, counts in sorted(conversions.items())
        }
        return {
            "record_count": len(records),
            "failure_count": len(failures),
            "error_count": len(errors),
            "maintenance_count": len(maintenance),
            "error_to_failure_24h": conversion_rates,
            "dataset_version": manifest.dataset_version,
            "source_checksum": manifest.source.checksum_sha256,
        }

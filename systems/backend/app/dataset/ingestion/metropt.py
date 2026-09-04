from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from typing import Any

from .ingestion_schema import DatasetManifest, QuarantinedRecord


class MetroPTCompressorAdapter:
    code = "metropt-compressor-monitoring"
    display_name = "MetroPT Compressor Monitoring"

    _timestamp_aliases = ("timestamp", "datetime", "Timestamp")
    _numeric_fields = (
        "TP2",
        "TP3",
        "H1",
        "DV_pressure",
        "Reservoirs",
        "Oil_temperature",
        "Motor_current",
    )
    _state_fields = (
        "COMP",
        "DV_eletric",
        "Towers",
        "MPG",
        "LPS",
        "Pressure_switch",
        "Oil_level",
        "Caudal_impulses",
    )

    def required_fields(self, manifest: DatasetManifest) -> set[str]:
        return set(manifest.schema_.required_fields)

    @classmethod
    def _timestamp(cls, record: dict[str, str]) -> str | None:
        for field in cls._timestamp_aliases:
            value = record.get(field)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def normalize_record(
        self,
        record: dict[str, str],
        *,
        manifest: DatasetManifest,
        row_number: int,
    ) -> dict[str, Any] | QuarantinedRecord:
        timestamp = self._timestamp(record)
        if not timestamp:
            return QuarantinedRecord(
                source_row_number=row_number,
                error_code="metropt.timestamp_missing",
                error_message="timestamp is required",
                record=dict(record),
            )
        try:
            observed_at = self._parse_datetime(timestamp)
            measurements = {
                field: float(record[field])
                for field in self._numeric_fields
                if record.get(field) not in {None, ""}
            }
            states = {
                field: int(float(record[field]))
                for field in self._state_fields
                if record.get(field) not in {None, ""}
            }
        except (TypeError, ValueError) as exc:
            return QuarantinedRecord(
                source_row_number=row_number,
                error_code="metropt.type_conversion_failed",
                error_message=str(exc),
                record=dict(record),
            )
        if not measurements:
            return QuarantinedRecord(
                source_row_number=row_number,
                error_code="metropt.measurement_missing",
                error_message="at least one compressor measurement is required",
                record=dict(record),
            )
        return {
            "record_type": "compressor_telemetry",
            "equipment_id": "metropt-air-production-unit",
            "observed_at": observed_at.isoformat(),
            "measurements": measurements,
            "states": states,
            "source": {key: value for key, value in record.items() if value not in {None, ""}},
        }

    def derive_metrics(
        self,
        records: list[dict[str, Any]],
        *,
        manifest: DatasetManifest,
    ) -> dict[str, Any]:
        fields = sorted(
            {
                field
                for record in records
                for field in record.get("measurements", {})
            }
        )
        averages = {
            field: mean(
                record["measurements"][field]
                for record in records
                if field in record.get("measurements", {})
            )
            for field in fields
        }
        compressor_on = sum(
            1 for record in records if record.get("states", {}).get("COMP") == 1
        )
        return {
            "record_count": len(records),
            "measurement_averages": averages,
            "compressor_on_records": compressor_on,
            "compressor_on_ratio": compressor_on / len(records) if records else 0.0,
            "dataset_version": manifest.dataset_version,
            "source_checksum": manifest.source.checksum_sha256,
        }

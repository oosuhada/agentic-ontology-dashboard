from __future__ import annotations

from typing import Any

from .models import DatasetManifest, QuarantinedRecord


class GovernedTabularAdapter:
    """Generic CSV adapter for an approved Adaptive Modeling Manifest Draft.

    The adapter is intentionally schema-driven. It does not infer semantics or
    execute expressions during ingestion; it only emits the canonical fields
    explicitly selected and approved in the manifest.
    """

    code = "governed-tabular"
    display_name = "Governed Tabular Dataset"

    def required_fields(self, manifest: DatasetManifest) -> set[str]:
        return set(manifest.schema_.required_fields)

    def normalize_record(
        self,
        record: dict[str, str],
        *,
        manifest: DatasetManifest,
        row_number: int,
    ) -> dict[str, Any] | QuarantinedRecord:
        canonical_fields = list(manifest.schema_.field_aliases)
        if not canonical_fields:
            canonical_fields = list(manifest.schema_.required_fields)
        normalized = {field: record.get(field, "") for field in canonical_fields}
        normalized["_source_row_number"] = row_number
        return normalized

    def derive_metrics(
        self,
        records: list[dict[str, Any]],
        *,
        manifest: DatasetManifest,
    ) -> dict[str, Any]:
        return {
            "adapter": self.code,
            "governed_manifest": True,
            "accepted_field_count": len(manifest.schema_.field_aliases),
            "accepted_record_count": len(records),
            "primary_key": manifest.schema_.primary_key,
            "timestamp_field": manifest.schema_.timestamp_field,
            "semantic_inference_performed": False,
        }


__all__ = ["GovernedTabularAdapter"]

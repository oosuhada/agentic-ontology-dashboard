"""Streaming validator for the Predictive Maintenance Canonical v2 package."""

from __future__ import annotations

import csv
import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from .bundle_models import (
    BundleFileSchemaMetadata,
    BundleGenerationMetadata,
    BundleRoleValidationSummary,
    BundleValidationIssue,
    DatasetBundleFile,
    DatasetBundleManifestV2,
    PredictiveMaintenanceSourceContract,
    compute_bundle_checksum,
)
from .protocol import BundleContentValidation, ResolvedBundleFile


@dataclass(frozen=True)
class PredictiveMaintenanceRoleContract:
    format: Literal["csv", "jsonl"]
    media_type: str
    required_fields: tuple[str, ...]
    primary_key: tuple[str, ...]
    timestamp_field: str | None = None


ROLE_CONTRACTS: dict[str, PredictiveMaintenanceRoleContract] = {
    "asset_master": PredictiveMaintenanceRoleContract(
        format="csv",
        media_type="text/csv",
        required_fields=("asset_id", "asset_type", "site_id", "cell_id"),
        primary_key=("asset_id",),
    ),
    "asset_relation": PredictiveMaintenanceRoleContract(
        format="csv",
        media_type="text/csv",
        required_fields=("from_asset_id", "relation_type", "to_asset_id"),
        primary_key=("from_asset_id", "relation_type", "to_asset_id"),
    ),
    "compressor_sensor_observation": PredictiveMaintenanceRoleContract(
        format="csv",
        media_type="text/csv",
        required_fields=(
            "observed_at",
            "asset_id",
            "site_id",
            "cell_id",
            "is_operating",
            "operating_state",
            "voltage_raw",
            "rotation_raw",
            "pressure_raw",
            "vibration_raw",
            "relative_vibration_z",
            "relative_vibration_zone",
            "generator_version",
        ),
        primary_key=("asset_id", "observed_at"),
        timestamp_field="observed_at",
    ),
    "cnc_sensor_observation": PredictiveMaintenanceRoleContract(
        format="csv",
        media_type="text/csv",
        required_fields=(
            "observed_at",
            "asset_id",
            "site_id",
            "cell_id",
            "is_operating",
            "operating_state",
            "product_type",
            "air_temperature_k",
            "process_temperature_k",
            "rotational_speed_rpm",
            "torque_nm",
            "tool_wear_min",
            "generator_version",
        ),
        primary_key=("asset_id", "observed_at"),
        timestamp_field="observed_at",
    ),
    "cnc_production_cycle": PredictiveMaintenanceRoleContract(
        format="csv",
        media_type="text/csv",
        required_fields=(
            "product_id",
            "cnc_asset_id",
            "cycle_started_at",
            "cycle_completed_at",
            "product_type",
            "cutting_minutes",
            "tool_wear_increment_min",
        ),
        primary_key=("product_id",),
        timestamp_field="cycle_completed_at",
    ),
    "maintenance_event": PredictiveMaintenanceRoleContract(
        format="csv",
        media_type="text/csv",
        required_fields=(
            "maintenance_id",
            "asset_id",
            "maintenance_type",
            "started_at",
            "completed_at",
            "tool_replaced",
            "source_event_id",
        ),
        primary_key=("maintenance_id",),
        timestamp_field="started_at",
    ),
    "prediction_snapshot": PredictiveMaintenanceRoleContract(
        format="jsonl",
        media_type="application/x-ndjson",
        required_fields=(
            "prediction_id",
            "asset_id",
            "asset_type",
            "observed_at",
            "prediction_horizon_hours",
            "failure_probability",
            "predicted_failure_type",
            "confidence",
            "status",
            "model_version",
            "feature_scope",
        ),
        primary_key=("prediction_id",),
        timestamp_field="observed_at",
    ),
    "prediction_factor": PredictiveMaintenanceRoleContract(
        format="jsonl",
        media_type="application/x-ndjson",
        required_fields=(
            "prediction_id",
            "rank",
            "feature",
            "feature_value",
            "signed_contribution",
            "absolute_contribution",
            "direction",
            "explanation_method",
            "source_type",
        ),
        primary_key=("prediction_id", "rank"),
    ),
    "prediction_timeline": PredictiveMaintenanceRoleContract(
        format="jsonl",
        media_type="application/x-ndjson",
        required_fields=(
            "prediction_id",
            "asset_id",
            "asset_type",
            "observed_at",
            "prediction_horizon_hours",
            "failure_probability",
            "status",
            "top_factors",
            "model_version",
            "feature_scope",
            "source_type",
        ),
        primary_key=("prediction_id",),
        timestamp_field="observed_at",
    ),
}


ROLE_PATHS = {
    "asset_master": "canonical/dataset/asset_master.csv",
    "asset_relation": "canonical/dataset/asset_relation.csv",
    "compressor_sensor_observation": "canonical/dataset/compressor_sensor_observation.csv",
    "cnc_sensor_observation": "canonical/dataset/cnc_sensor_observation.csv",
    "cnc_production_cycle": "canonical/dataset/cnc_production_cycle.csv",
    "maintenance_event": "canonical/dataset/maintenance_event.csv",
    "prediction_snapshot": "canonical/model_outputs/prediction_snapshot.jsonl",
    "prediction_factor": "canonical/model_outputs/prediction_factor.jsonl",
    "prediction_timeline": "canonical/model_outputs/prediction_timeline.jsonl",
}


@dataclass
class _IssueCollector:
    limit: int
    samples: list[BundleValidationIssue]
    total: int = 0

    def add(
        self,
        summary: BundleRoleValidationSummary,
        *,
        code: str,
        message: str,
        row_number: int | None = None,
        record_identity: str | None = None,
    ) -> None:
        self.total += 1
        summary.issue_counts[code] = summary.issue_counts.get(code, 0) + 1
        if len(self.samples) < self.limit:
            self.samples.append(
                BundleValidationIssue(
                    role=summary.role,
                    code=code,
                    message=message,
                    row_number=row_number,
                    record_identity=record_identity,
                )
            )

    @property
    def truncated(self) -> bool:
        return self.total > len(self.samples)


RowError = tuple[str, str, str | None] | None


class PredictiveMaintenanceCanonicalV2Adapter:
    code = "predictive-maintenance-canonical-v2"
    display_name = "Predictive Maintenance Canonical v2 Bundle"
    required_roles = frozenset(ROLE_CONTRACTS)
    allowed_roles = required_roles
    bundle_schema_version = "predictive-maintenance-canonical-v2.bundle.v1"

    @classmethod
    def build_manifest(
        cls,
        package_root: str | Path,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        manifest_id: str = "predictive-maintenance-canonical-v2",
        dataset_name: str = "Predictive Maintenance Canonical v2",
    ) -> DatasetBundleManifestV2:
        root = Path(package_root).expanduser().resolve(strict=True)
        dataset_manifest_path = root / "canonical" / "dataset" / "dataset_manifest.json"
        model_contract_path = root / "canonical" / "model_outputs" / "model_contract.json"
        dataset_payload = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
        model_payload = json.loads(model_contract_path.read_text(encoding="utf-8"))

        canonical_checksums = dataset_payload.get("canonical_outputs", {})
        model_checksums = model_payload.get("output_sha256", {})
        if model_payload.get("dataset_version") != dataset_payload.get("dataset_version"):
            raise ValueError("model contract dataset_version does not match dataset manifest")
        if model_payload.get("canonical_input_sha256") != canonical_checksums:
            raise ValueError("model contract canonical checksums do not match dataset manifest")
        if model_payload.get("outputs_are_not_source_data") is not True:
            raise ValueError("model outputs must remain separate from canonical source data")

        files: list[DatasetBundleFile] = []
        for role in sorted(cls.required_roles):
            relative = ROLE_PATHS[role]
            path = (root / relative).resolve()
            contract = ROLE_CONTRACTS[role]
            filename = path.name
            checksum = (
                canonical_checksums.get(filename)
                if role in {
                    "asset_master",
                    "asset_relation",
                    "compressor_sensor_observation",
                    "cnc_sensor_observation",
                    "cnc_production_cycle",
                    "maintenance_event",
                }
                else model_checksums.get(filename)
            )
            if not isinstance(checksum, str):
                raise ValueError(f"checksum is missing from package contracts: {filename}")
            files.append(
                DatasetBundleFile(
                    role=role,
                    uri=path.as_uri(),
                    format=contract.format,
                    media_type=contract.media_type,
                    checksum_sha256=checksum,
                    size_bytes=path.stat().st_size if path.is_file() else 0,
                    schema=BundleFileSchemaMetadata(
                        schema_version=f"predictive-maintenance-canonical-v2.{role}.v1",
                        required_fields=list(contract.required_fields),
                        primary_key=list(contract.primary_key),
                        timestamp_field=contract.timestamp_field,
                        timezone="Asia/Seoul" if contract.timestamp_field else None,
                    ),
                )
            )

        generation = BundleGenerationMetadata(
            generator_version=str(dataset_payload["dataset_version"]),
            seed=int(dataset_payload["seed"]),
            period_start=datetime.fromisoformat(str(dataset_payload["start_at"])),
            period_end=datetime.fromisoformat(str(dataset_payload["end_at"])),
            observation_interval_minutes=int(dataset_payload["observation_interval_minutes"]),
            rate_profile=dataset_payload.get("rate_profile"),
        )
        source_contract = PredictiveMaintenanceSourceContract.model_validate(
            dataset_payload["source_contract"]
        )
        checksum = compute_bundle_checksum(
            dataset_version=str(dataset_payload["dataset_version"]),
            schema_version=cls.bundle_schema_version,
            generation=generation,
            source_contract=source_contract,
            files=files,
        )
        return DatasetBundleManifestV2(
            manifest_id=manifest_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            adapter_code=cls.code,
            dataset_name=dataset_name,
            dataset_version=str(dataset_payload["dataset_version"]),
            schema_version=cls.bundle_schema_version,
            bundle_checksum_sha256=checksum,
            generation=generation,
            source_contract=source_contract,
            files=files,
            created_at=datetime.fromisoformat(str(dataset_payload["created_at"])),
        )

    def validate_files(
        self,
        manifest: DatasetBundleManifestV2,
        files: dict[str, ResolvedBundleFile],
        *,
        issue_sample_limit: int,
    ) -> BundleContentValidation:
        summaries = {
            role: BundleRoleValidationSummary(
                role=role,
                uri=item.descriptor.uri,
                format=item.descriptor.format,
                media_type=item.descriptor.media_type,
                expected_checksum_sha256=item.descriptor.checksum_sha256,
                actual_checksum_sha256=item.actual_checksum_sha256,
                checksum_valid=item.actual_checksum_sha256
                == item.descriptor.checksum_sha256,
                required_fields=list(ROLE_CONTRACTS[role].required_fields),
            )
            for role, item in files.items()
        }
        collector = _IssueCollector(limit=issue_sample_limit, samples=[])

        for role, resolved in files.items():
            summary = summaries[role]
            contract = ROLE_CONTRACTS[role]
            declared_fields = set(resolved.descriptor.schema_.required_fields)
            missing_declared = sorted(set(contract.required_fields) - declared_fields)
            if resolved.descriptor.format != contract.format:
                collector.add(
                    summary,
                    code="format_mismatch",
                    message=f"role requires {contract.format}, got {resolved.descriptor.format}",
                )
            if resolved.descriptor.media_type != contract.media_type:
                collector.add(
                    summary,
                    code="media_type_mismatch",
                    message=(
                        f"role requires {contract.media_type}, "
                        f"got {resolved.descriptor.media_type}"
                    ),
                )
            if missing_declared:
                collector.add(
                    summary,
                    code="manifest_schema_incomplete",
                    message=f"manifest schema omits required fields: {', '.join(missing_declared)}",
                )

        asset_ids: set[str] = set()
        asset_types: dict[str, str] = {}
        prediction_ids: set[str] = set()
        timeline_ids: set[str] = set()

        self._validate_csv(
            manifest,
            files["asset_master"],
            summaries["asset_master"],
            collector,
            lambda row: self._validate_asset(row, asset_ids, asset_types),
        )
        self._validate_csv(
            manifest,
            files["asset_relation"],
            summaries["asset_relation"],
            collector,
            lambda row: self._validate_relation(row, asset_types),
        )
        self._validate_csv(
            manifest,
            files["compressor_sensor_observation"],
            summaries["compressor_sensor_observation"],
            collector,
            lambda row: self._validate_observation(
                row, manifest, asset_types, expected_asset_type="compressor"
            ),
        )
        self._validate_csv(
            manifest,
            files["cnc_sensor_observation"],
            summaries["cnc_sensor_observation"],
            collector,
            lambda row: self._validate_observation(
                row, manifest, asset_types, expected_asset_type="cnc"
            ),
        )
        self._validate_csv(
            manifest,
            files["cnc_production_cycle"],
            summaries["cnc_production_cycle"],
            collector,
            lambda row: self._validate_cycle(row, manifest, asset_types),
        )
        self._validate_csv(
            manifest,
            files["maintenance_event"],
            summaries["maintenance_event"],
            collector,
            lambda row: self._validate_maintenance(row, manifest, asset_ids),
        )
        self._validate_jsonl(
            manifest,
            files["prediction_snapshot"],
            summaries["prediction_snapshot"],
            collector,
            lambda row: self._validate_prediction_snapshot(
                row, manifest, asset_types, prediction_ids
            ),
        )
        self._validate_jsonl(
            manifest,
            files["prediction_factor"],
            summaries["prediction_factor"],
            collector,
            lambda row: self._validate_prediction_factor(row, prediction_ids),
        )
        self._validate_jsonl(
            manifest,
            files["prediction_timeline"],
            summaries["prediction_timeline"],
            collector,
            lambda row: self._validate_prediction_timeline(
                row, manifest, asset_types, timeline_ids
            ),
        )

        normalized = tuple(
            BundleRoleValidationSummary.model_validate(summary.model_dump(mode="python"))
            for summary in sorted(summaries.values(), key=lambda item: item.role)
        )
        return BundleContentValidation(
            roles=normalized,
            issues=tuple(collector.samples),
            issue_sample_truncated=collector.truncated,
        )

    def _validate_csv(
        self,
        manifest: DatasetBundleManifestV2,
        resolved: ResolvedBundleFile,
        summary: BundleRoleValidationSummary,
        collector: _IssueCollector,
        validator: Callable[[dict[str, str]], RowError],
    ) -> None:
        contract = ROLE_CONTRACTS[summary.role]
        with resolved.path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            summary.observed_fields = fields
            missing = sorted(set(contract.required_fields) - set(fields))
            if missing:
                collector.add(
                    summary,
                    code="missing_required_fields",
                    message=f"CSV header is missing: {', '.join(missing)}",
                )
                summary.status = "failed"
                return
            summary.schema_valid = True
            for row_number, raw in enumerate(reader, start=2):
                summary.source_record_count += 1
                row = {key: value or "" for key, value in raw.items() if key is not None}
                error = validator(row)
                if error is None:
                    summary.accepted_record_count += 1
                    self._record_role_timestamp(summary, contract, row)
                else:
                    code, message, identity = error
                    summary.quarantined_record_count += 1
                    collector.add(
                        summary,
                        code=code,
                        message=message,
                        row_number=row_number,
                        record_identity=identity,
                    )
            if summary.source_record_count == 0:
                collector.add(summary, code="empty_role", message="runtime role contains no rows")
            summary.status = "passed" if not summary.issue_counts else "failed"

    def _validate_jsonl(
        self,
        manifest: DatasetBundleManifestV2,
        resolved: ResolvedBundleFile,
        summary: BundleRoleValidationSummary,
        collector: _IssueCollector,
        validator: Callable[[dict[str, Any]], RowError],
    ) -> None:
        contract = ROLE_CONTRACTS[summary.role]
        observed_fields: set[str] = set()
        with resolved.path.open("r", encoding="utf-8") as handle:
            for row_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                summary.source_record_count += 1
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    summary.quarantined_record_count += 1
                    collector.add(
                        summary,
                        code="invalid_json",
                        message=str(exc),
                        row_number=row_number,
                    )
                    continue
                if not isinstance(row, dict):
                    summary.quarantined_record_count += 1
                    collector.add(
                        summary,
                        code="non_object_jsonl_row",
                        message="JSONL rows must be objects",
                        row_number=row_number,
                    )
                    continue
                observed_fields.update(str(key) for key in row)
                missing = sorted(set(contract.required_fields) - set(row))
                if missing:
                    summary.quarantined_record_count += 1
                    collector.add(
                        summary,
                        code="missing_required_fields",
                        message=f"JSON object is missing: {', '.join(missing)}",
                        row_number=row_number,
                        record_identity=str(row.get("prediction_id") or "") or None,
                    )
                    continue
                error = validator(row)
                if error is None:
                    summary.accepted_record_count += 1
                    self._record_role_timestamp(summary, contract, row)
                else:
                    code, message, identity = error
                    summary.quarantined_record_count += 1
                    collector.add(
                        summary,
                        code=code,
                        message=message,
                        row_number=row_number,
                        record_identity=identity,
                    )
        summary.observed_fields = sorted(observed_fields)
        summary.schema_valid = (
            set(contract.required_fields).issubset(observed_fields)
            and "missing_required_fields" not in summary.issue_counts
            and "invalid_json" not in summary.issue_counts
            and "non_object_jsonl_row" not in summary.issue_counts
        )
        if summary.source_record_count == 0:
            collector.add(summary, code="empty_role", message="runtime role contains no rows")
        summary.status = "passed" if not summary.issue_counts else "failed"

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return parsed

    @classmethod
    def _timestamp_in_period(
        cls,
        value: Any,
        manifest: DatasetBundleManifestV2,
    ) -> datetime:
        parsed = cls._parse_timestamp(value)
        if not (manifest.generation.period_start <= parsed <= manifest.generation.period_end):
            raise ValueError("timestamp is outside the Dataset generation period")
        return parsed

    @classmethod
    def _record_role_timestamp(
        cls,
        summary: BundleRoleValidationSummary,
        contract: PredictiveMaintenanceRoleContract,
        row: dict[str, Any],
    ) -> None:
        if contract.timestamp_field is None:
            return
        try:
            timestamp = cls._parse_timestamp(row[contract.timestamp_field])
        except (KeyError, TypeError, ValueError):
            return
        if summary.earliest_timestamp is None or timestamp < summary.earliest_timestamp:
            summary.earliest_timestamp = timestamp
        if summary.latest_timestamp is None or timestamp > summary.latest_timestamp:
            summary.latest_timestamp = timestamp

    @staticmethod
    def _validate_asset(
        row: dict[str, str],
        asset_ids: set[str],
        asset_types: dict[str, str],
    ) -> RowError:
        asset_id = row["asset_id"].strip()
        asset_type = row["asset_type"].strip()
        if not asset_id:
            return "missing_asset_id", "asset_id is required", None
        if asset_id in asset_ids:
            return "duplicate_asset_id", "asset_id must be unique", asset_id
        if asset_type not in {"compressor", "cnc"}:
            return "invalid_asset_type", "asset_type must be compressor or cnc", asset_id
        asset_ids.add(asset_id)
        asset_types[asset_id] = asset_type
        return None

    @staticmethod
    def _validate_relation(row: dict[str, str], asset_types: dict[str, str]) -> RowError:
        source = row["from_asset_id"].strip()
        target = row["to_asset_id"].strip()
        identity = f"{source}->{target}"
        if source not in asset_types or target not in asset_types:
            return "unknown_relation_asset", "relation references an unknown asset", identity
        if row["relation_type"] != "SUPPLIES_AIR_TO":
            return "invalid_relation_type", "relation_type must be SUPPLIES_AIR_TO", identity
        if asset_types[source] != "compressor" or asset_types[target] != "cnc":
            return "invalid_relation_endpoint_type", "relation must connect compressor to cnc", identity
        return None

    @classmethod
    def _validate_observation(
        cls,
        row: dict[str, str],
        manifest: DatasetBundleManifestV2,
        asset_types: dict[str, str],
        *,
        expected_asset_type: str,
    ) -> RowError:
        asset_id = row["asset_id"].strip()
        identity = f"{asset_id}#{row['observed_at']}"
        if asset_id not in asset_types:
            return "unknown_observation_asset", "observation references an unknown asset", identity
        if asset_types[asset_id] != expected_asset_type:
            return "observation_asset_type_mismatch", "observation role has the wrong asset type", identity
        try:
            cls._timestamp_in_period(row["observed_at"], manifest)
        except (TypeError, ValueError) as exc:
            return "invalid_observation_timestamp", str(exc), identity
        if row.get("generator_version") != manifest.generation.generator_version:
            return "generator_version_mismatch", "row generator_version differs from bundle", identity
        return None

    @classmethod
    def _validate_cycle(
        cls,
        row: dict[str, str],
        manifest: DatasetBundleManifestV2,
        asset_types: dict[str, str],
    ) -> RowError:
        asset_id = row["cnc_asset_id"].strip()
        identity = row["product_id"].strip() or None
        if asset_types.get(asset_id) != "cnc":
            return "unknown_cycle_asset", "production cycle references an unknown CNC asset", identity
        try:
            started = cls._timestamp_in_period(row["cycle_started_at"], manifest)
            completed = cls._timestamp_in_period(row["cycle_completed_at"], manifest)
        except (TypeError, ValueError) as exc:
            return "invalid_cycle_timestamp", str(exc), identity
        if completed <= started:
            return "invalid_cycle_duration", "cycle_completed_at must be after cycle_started_at", identity
        return None

    @classmethod
    def _validate_maintenance(
        cls,
        row: dict[str, str],
        manifest: DatasetBundleManifestV2,
        asset_ids: set[str],
    ) -> RowError:
        identity = row["maintenance_id"].strip() or None
        if row["asset_id"].strip() not in asset_ids:
            return "unknown_maintenance_asset", "maintenance references an unknown asset", identity
        try:
            started = cls._timestamp_in_period(row["started_at"], manifest)
            completed = cls._timestamp_in_period(row["completed_at"], manifest)
        except (TypeError, ValueError) as exc:
            return "invalid_maintenance_timestamp", str(exc), identity
        if completed <= started:
            return "invalid_maintenance_duration", "completed_at must be after started_at", identity
        return None

    @classmethod
    def _validate_prediction_snapshot(
        cls,
        row: dict[str, Any],
        manifest: DatasetBundleManifestV2,
        asset_types: dict[str, str],
        prediction_ids: set[str],
    ) -> RowError:
        prediction_id = str(row["prediction_id"])
        asset_id = str(row["asset_id"])
        if prediction_id in prediction_ids:
            return "duplicate_prediction_id", "prediction_id must be unique", prediction_id
        if asset_id not in asset_types:
            return "unknown_prediction_asset", "prediction references an unknown asset", prediction_id
        if str(row["asset_type"]) != asset_types[asset_id]:
            return "prediction_asset_type_mismatch", "prediction asset_type differs from asset master", prediction_id
        expected_identity = f"{asset_id}#{row['observed_at']}"
        if prediction_id != expected_identity:
            return "prediction_identity_mismatch", "prediction_id must be asset_id#observed_at", prediction_id
        try:
            cls._timestamp_in_period(row["observed_at"], manifest)
        except (TypeError, ValueError) as exc:
            return "invalid_prediction_timestamp", str(exc), prediction_id
        prediction_ids.add(prediction_id)
        return None

    @staticmethod
    def _validate_prediction_factor(
        row: dict[str, Any],
        prediction_ids: set[str],
    ) -> RowError:
        prediction_id = str(row["prediction_id"])
        if prediction_id not in prediction_ids:
            return "unknown_factor_prediction_id", "factor references an unknown snapshot prediction_id", prediction_id
        try:
            rank = int(row["rank"])
        except (TypeError, ValueError):
            return "invalid_factor_rank", "factor rank must be an integer", prediction_id
        if rank < 1:
            return "invalid_factor_rank", "factor rank must be positive", prediction_id
        return None

    @classmethod
    def _validate_prediction_timeline(
        cls,
        row: dict[str, Any],
        manifest: DatasetBundleManifestV2,
        asset_types: dict[str, str],
        timeline_ids: set[str],
    ) -> RowError:
        prediction_id = str(row["prediction_id"])
        asset_id = str(row["asset_id"])
        if prediction_id in timeline_ids:
            return "duplicate_timeline_prediction_id", "timeline prediction_id must be unique", prediction_id
        if asset_id not in asset_types:
            return "unknown_timeline_asset", "timeline prediction references an unknown asset", prediction_id
        if str(row["asset_type"]) != asset_types[asset_id]:
            return "timeline_asset_type_mismatch", "timeline asset_type differs from asset master", prediction_id
        expected_identity = f"{asset_id}#{row['observed_at']}"
        if prediction_id != expected_identity:
            return "timeline_identity_mismatch", "timeline prediction_id must be asset_id#observed_at", prediction_id
        try:
            cls._timestamp_in_period(row["observed_at"], manifest)
        except (TypeError, ValueError) as exc:
            return "invalid_timeline_timestamp", str(exc), prediction_id
        timeline_ids.add(prediction_id)
        return None


__all__ = [
    "PredictiveMaintenanceCanonicalV2Adapter",
    "PredictiveMaintenanceRoleContract",
    "ROLE_CONTRACTS",
    "ROLE_PATHS",
]

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from openpyxl import Workbook
from pydantic import ValidationError
from jsonschema import Draft202012Validator

from ontology_dashboard.adapters.file_adapter import FileAdapter
from ontology_dashboard.adapters.models import DatasetManifest, PredictionResult
from ontology_dashboard.adapters.prediction_repository import PredictionResultRepository
from ontology_dashboard.identity import IdentityService
from ontology_dashboard.migrations import migrate

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_for(
    path: Path,
    *,
    adapter_code: str,
    project_id: str,
    workspace_id: str,
    required_fields: list[str],
) -> DatasetManifest:
    return DatasetManifest.model_validate(
        {
            "manifest_version": "1.0",
            "manifest_id": f"manifest-{adapter_code}",
            "organization_id": "org-ontology-demo",
            "project_id": project_id,
            "workspace_id": workspace_id,
            "adapter_code": adapter_code,
            "dataset_name": adapter_code,
            "dataset_version": "fixture-v1",
            "source": {
                "uri": str(path),
                "media_type": "text/csv",
                "checksum_sha256": sha256(path),
                "size_bytes": path.stat().st_size,
                "encoding": "utf-8",
            },
            "schema": {
                "format": "csv",
                "required_fields": required_fields,
                "field_aliases": {},
                "primary_key": [],
                "timezone": "UTC",
            },
            "quality_rules": [],
            "created_at": "2026-08-01T00:00:00+00:00",
        }
    )


@pytest.fixture()
def adapter_database(tmp_path: Path) -> Path:
    database = tmp_path / "adapter.db"
    migrate(str(database))
    IdentityService(database, app_env="test", seed_demo=True)
    return database


def test_azure_file_adapter_quarantines_invalid_rows_and_recalculates_metrics(
    adapter_database: Path,
    tmp_path: Path,
) -> None:
    source = tmp_path / "azure.csv"
    source.write_text(
        "datetime,machineID,errorID,failure,volt\n"
        "2026-01-01T00:00:00Z,1,error1,,220\n"
        "2026-01-01T12:00:00Z,1,,comp1,221\n"
        "2026-01-02T00:00:00Z,,error2,,bad\n",
        encoding="utf-8",
    )
    manifest = manifest_for(
        source,
        adapter_code="azure-fleet-maintenance",
        project_id="azure-fleet-maintenance-project",
        workspace_id="azure-fleet-maintenance",
        required_fields=["datetime", "machineID"],
    )
    result = FileAdapter(adapter_database, allowed_roots=[tmp_path]).ingest(manifest)

    assert result.status == "completed_with_quarantine"
    assert result.source_record_count == 3
    assert result.accepted_record_count == 2
    assert result.quarantined_record_count == 1
    assert result.quarantined_records[0].error_code == "azure.required_field_missing"
    assert result.metrics["error_to_failure_24h"]["error1"] == {
        "errors": 1,
        "failure_within_24h": 1,
        "conversion_rate": 1.0,
    }
    assert result.metrics["source_checksum"] == manifest.source.checksum_sha256


def test_metropt_adapter_validates_second_project_abstraction(
    adapter_database: Path,
    tmp_path: Path,
) -> None:
    source = tmp_path / "metropt.csv"
    source.write_text(
        "timestamp,TP2,TP3,Motor_current,COMP\n"
        "2026-01-01T00:00:00Z,8.0,9.0,4.0,1\n"
        "2026-01-01T00:01:00Z,10.0,11.0,6.0,0\n",
        encoding="utf-8",
    )
    manifest = manifest_for(
        source,
        adapter_code="metropt-compressor-monitoring",
        project_id="metropt-compressor-project",
        workspace_id="metropt-compressor-monitoring",
        required_fields=["timestamp", "TP2"],
    )
    result = FileAdapter(adapter_database, allowed_roots=[tmp_path]).ingest(manifest)

    assert result.status == "completed"
    assert result.accepted_record_count == 2
    assert result.metrics["measurement_averages"]["TP2"] == 9.0
    assert result.metrics["compressor_on_ratio"] == 0.5


def prediction_payload(*, project_id: str, workspace_id: str) -> dict:
    return {
        "contract_version": "1.0",
        "prediction_id": "prediction-fixture-1",
        "organization_id": "org-ontology-demo",
        "project_id": project_id,
        "workspace_id": workspace_id,
        "subject": {
            "object_type": "equipment",
            "object_id": "machine-1",
            "observed_at": "2026-01-01T00:00:00Z",
        },
        "prediction": {
            "task": "classification",
            "status": "warning",
            "label": "failure-risk",
            "score": 0.8,
            "confidence": 0.9,
        },
        "evidence": [
            {
                "evidence_id": "evidence-1",
                "kind": "feature",
                "label": "vibration",
                "value": 2.1,
                "unit": "mm/s",
                "contribution": 0.7,
                "source": {
                    "system": "fixture",
                    "reference": "row:1",
                    "checksum": "a" * 64,
                },
            }
        ],
        "recommended_actions": [
            {
                "action_type": "inspect",
                "label": "Inspect equipment",
                "requires_approval": True,
                "parameters": {},
            }
        ],
        "model": {
            "provider": "fixture",
            "model_name": "risk-model",
            "model_version": "v1",
            "dataset_version": "fixture-v1",
        },
        "data_quality": {"status": "pass", "issues": []},
        "created_at": "2026-01-01T00:00:00Z",
    }


def test_prediction_contract_requires_evidence_and_project_scope(adapter_database: Path) -> None:
    payload = prediction_payload(
        project_id="azure-fleet-maintenance-project",
        workspace_id="azure-fleet-maintenance",
    )
    result = PredictionResult.model_validate(payload)
    repository = PredictionResultRepository(adapter_database)
    saved = repository.save(result)
    assert saved["project_id"] == "azure-fleet-maintenance-project"
    assert repository.list(
        organization_id="org-ontology-demo",
        project_id="manufacturing-demo-project",
    ) == []
    assert len(
        repository.list(
            organization_id="org-ontology-demo",
            project_id="azure-fleet-maintenance-project",
        )
    ) == 1

    invalid = dict(payload)
    invalid["prediction_id"] = "prediction-without-evidence"
    invalid["evidence"] = []
    with pytest.raises(ValidationError):
        PredictionResult.model_validate(invalid)


@pytest.mark.parametrize(
    ("manifest_name", "expected_adapter", "expected_count"),
    [
        ("azure-fleet-maintenance-manifest.json", "azure-fleet-maintenance", 4),
        ("metropt-compressor-manifest.json", "metropt-compressor-monitoring", 3),
    ],
)
def test_checked_in_adapter_manifests_are_checksum_reproducible(
    adapter_database: Path,
    manifest_name: str,
    expected_adapter: str,
    expected_count: int,
) -> None:
    manifest_path = ROOT / "data" / "fixtures" / "adapters" / manifest_name
    manifest = DatasetManifest.model_validate(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    result = FileAdapter(
        adapter_database,
        allowed_roots=[ROOT / "data" / "fixtures"],
    ).ingest(manifest)
    assert result.adapter_code == expected_adapter
    assert result.accepted_record_count == expected_count
    assert result.quarantined_record_count == 0
    assert result.metrics["source_checksum"] == manifest.source.checksum_sha256


def test_file_adapter_rejects_sources_outside_allowlisted_roots(
    adapter_database: Path,
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.csv"
    outside.write_text("datetime,machineID\n2026-01-01T00:00:00Z,1\n", encoding="utf-8")
    manifest = manifest_for(
        outside,
        adapter_code="azure-fleet-maintenance",
        project_id="azure-fleet-maintenance-project",
        workspace_id="azure-fleet-maintenance",
        required_fields=["datetime", "machineID"],
    )
    with pytest.raises(ValueError, match="outside the configured ingestion roots"):
        FileAdapter(adapter_database, allowed_roots=[allowed]).ingest(manifest)


def test_governed_tabular_adapter_honors_approved_csv_delimiter(
    adapter_database: Path,
    tmp_path: Path,
) -> None:
    source = tmp_path / "governed-semicolon.csv"
    source.write_text(
        "machine_id;timestamp;voltage\n"
        "M-1;2026-01-01T00:00:00Z;220.5\n"
        "M-2;2026-01-01T00:01:00Z;221.0\n",
        encoding="utf-8",
    )
    manifest = DatasetManifest.model_validate(
        {
            "manifest_id": "manifest-governed-semicolon",
            "organization_id": "org-ontology-demo",
            "project_id": "manufacturing-demo-project",
            "workspace_id": "manufacturing-demo",
            "adapter_code": "governed-tabular",
            "dataset_name": "Governed semicolon CSV",
            "dataset_version": "v1",
            "source": {
                "uri": str(source),
                "media_type": "text/csv",
                "checksum_sha256": sha256(source),
                "size_bytes": source.stat().st_size,
                "encoding": "utf-8",
            },
            "schema": {
                "format": "csv",
                "delimiter": ";",
                "required_fields": ["equipment_id", "observed_at"],
                "field_aliases": {
                    "equipment_id": ["machine_id"],
                    "observed_at": ["timestamp"],
                    "voltage_v": ["voltage"],
                },
                "primary_key": ["equipment_id", "observed_at"],
                "timestamp_field": "observed_at",
                "timezone": "UTC",
            },
            "quality_rules": [
                {"code": "required-equipment", "field": "equipment_id", "rule": "required"},
                {"code": "timestamp", "field": "observed_at", "rule": "datetime"},
                {"code": "voltage", "field": "voltage_v", "rule": "number"},
            ],
        }
    )
    result = FileAdapter(adapter_database, allowed_roots=[tmp_path]).ingest(manifest)
    assert result.status == "completed"
    assert result.accepted_record_count == 2
    assert result.accepted_records[0]["equipment_id"] == "M-1"
    assert result.accepted_records[0]["voltage_v"] == "220.5"
    assert result.metrics["semantic_inference_performed"] is False


def test_governed_tabular_adapter_ingests_selected_xlsx_sheet(
    adapter_database: Path,
    tmp_path: Path,
) -> None:
    source = tmp_path / "governed.xlsx"
    workbook = Workbook()
    ignored = workbook.active
    ignored.title = "README"
    ignored.append(["note"])
    ignored.append(["not data"])
    data = workbook.create_sheet("Telemetry")
    data.append(["machine_id", "timestamp", "voltage"])
    data.append(["M-1", "2026-01-01T00:00:00Z", 220.5])
    data.append(["M-2", "2026-01-01T00:01:00Z", 221.0])
    workbook.save(source)
    manifest = DatasetManifest.model_validate(
        {
            "manifest_id": "manifest-governed-xlsx",
            "organization_id": "org-ontology-demo",
            "project_id": "manufacturing-demo-project",
            "workspace_id": "manufacturing-demo",
            "adapter_code": "governed-tabular",
            "dataset_name": "Governed XLSX",
            "dataset_version": "v1",
            "source": {
                "uri": str(source),
                "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "checksum_sha256": sha256(source),
                "size_bytes": source.stat().st_size,
                "encoding": "utf-8",
            },
            "schema": {
                "format": "xlsx",
                "sheet": "Telemetry",
                "required_fields": ["equipment_id", "observed_at"],
                "field_aliases": {
                    "equipment_id": ["machine_id"],
                    "observed_at": ["timestamp"],
                    "voltage_v": ["voltage"],
                },
                "primary_key": ["equipment_id", "observed_at"],
                "timestamp_field": "observed_at",
                "timezone": "UTC",
            },
            "quality_rules": [
                {"code": "required-equipment", "field": "equipment_id", "rule": "required"},
                {"code": "timestamp", "field": "observed_at", "rule": "datetime"},
                {"code": "voltage", "field": "voltage_v", "rule": "number"},
            ],
        }
    )
    result = FileAdapter(adapter_database, allowed_roots=[tmp_path]).ingest(manifest)
    assert result.status == "completed"
    assert result.accepted_record_count == 2
    assert result.accepted_records[1]["equipment_id"] == "M-2"
    assert result.accepted_records[1]["voltage_v"] == "221"
    schema = json.loads(
        (ROOT / "schemas" / "dataset-manifest.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(
        schema,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )
    assert list(validator.iter_errors(manifest.model_dump(mode="json", by_alias=True))) == []

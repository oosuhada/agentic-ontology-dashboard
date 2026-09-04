from __future__ import annotations

from datetime import UTC, datetime

from app.dataset.dataset_schema import (
    DatasetFileRecord,
    DatasetVersionRecord,
    AdapterIngestionRunRecord,
    ProjectionRecord,
)


def test_dataset_catalog_accepts_published_bundle_versions_and_ingestion_file_metadata() -> None:
    now = datetime.now(UTC)
    version = DatasetVersionRecord.model_validate(
        {
            "id": "dsv-v3",
            "organization_id": "org-test",
            "project_id": "project-test",
            "workspace_id": "workspace-test",
            "dataset_id": "dataset-test",
            "version_number": 1,
            "version_label": "canonical-ai4i-physics-v3.1",
            "source_version": "canonical-ai4i-physics-v3.1",
            "manifest_id": "manifest-v3",
            "checksum_sha256": "a" * 64,
            "schema": {},
            "profile": {},
            "record_count": 672_553,
            "status": "published",
            "created_by": "bootstrap",
            "created_at": now,
        }
    )
    file_record = DatasetFileRecord.model_validate(
        {
            "id": "file-v3",
            "organization_id": "org-test",
            "project_id": "project-test",
            "workspace_id": "workspace-test",
            "dataset_id": "dataset-test",
            "dataset_version_id": "dsv-v3",
            "uri": "file:///canonical/result_artifact.jsonl",
            "media_type": "application/x-ndjson",
            "checksum_sha256": "b" * 64,
            "size_bytes": 100,
            "role": "result_artifact",
            "format": "jsonl",
            "schema_json": {"contract": "result-artifact-v1.0"},
            "created_at": now,
        }
    )
    projection = ProjectionRecord.model_validate(
        {
            "id": "projection-v3",
            "organization_id": "org-test",
            "project_id": "project-test",
            "workspace_id": "workspace-test",
            "dataset_id": "dataset-test",
            "dataset_version_id": "dsv-v3",
            "store_kind": "graph",
            "status": "pending",
            "object_namespace": "predictive-maintenance",
            "source_version": "canonical-ai4i-physics-v3.1",
            "record_count": 0,
            "attempt_count": 0,
            "last_error": None,
            "provider_run_id": None,
            "provider_metadata_json": {},
            "started_at": None,
            "completed_at": None,
            "updated_at": now,
        }
    )
    ingestion = AdapterIngestionRunRecord.model_validate(
        {
            "id": "ingestion-v3",
            "organization_id": "org-test",
            "project_id": "project-test",
            "workspace_id": "workspace-test",
            "manifest_id": "manifest-v3",
            "adapter_code": "predictive-maintenance-v3.1",
            "status": "completed",
            "source_record_count": 672_553,
            "accepted_record_count": 672_553,
            "quarantined_record_count": 0,
            "dataset_id": "dataset-test",
            "dataset_version_id": "dsv-v3",
            "bundle_checksum_sha256": "a" * 64,
            "validation_checksum_sha256": "c" * 64,
            "metrics_json": {"idempotent": True},
            "error_message": None,
            "started_at": now,
            "completed_at": now,
        }
    )

    assert version.status == "published"
    assert file_record.role == "result_artifact"
    assert file_record.file_schema == {"contract": "result-artifact-v1.0"}
    assert projection.provider_metadata_json == {}
    assert ingestion.metrics_json == {"idempotent": True}

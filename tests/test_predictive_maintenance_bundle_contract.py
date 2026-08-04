from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from ontology_dashboard.adapters.bundle_models import (
    BundleFileSchemaMetadata,
    BundleGenerationMetadata,
    DatasetBundleFile,
    DatasetBundleManifestV2,
    DatasetSourceReference,
    Neo4jProjectionIdentity,
    PostgreSQLObjectIdentity,
    PredictiveMaintenanceSourceContract,
    compute_bundle_checksum,
)
from ontology_dashboard.integrations.project3 import (
    Project3GraphProjectionRequest,
    Project3GraphProjectionResponse,
    Project3ProjectionError,
    Project3ProjectionIdentity,
    Project3ProjectionNode,
)


ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def load_schema(name: str) -> dict:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def source_contract() -> PredictiveMaintenanceSourceContract:
    return PredictiveMaintenanceSourceContract(
        compressor_and_cnc_independent=True,
        topology_relation_is_not_causal_truth=True,
        upstream_features_in_source=False,
        synthetic_effect_columns_in_source=False,
        prediction_outputs_in_source=False,
        evaluation_truth_separate=True,
    )


def generation(**updates: object) -> BundleGenerationMetadata:
    payload = {
        "generator_version": "canonical-independent-v1.0",
        "seed": 42,
        "period_start": datetime(2026, 8, 1, tzinfo=timezone.utc),
        "period_end": datetime(2026, 8, 31, tzinfo=timezone.utc),
        "observation_interval_minutes": 10,
        "rate_profile": "balanced_demo",
    }
    payload.update(updates)
    return BundleGenerationMetadata.model_validate(payload)


def bundle_file(
    role: str,
    checksum: str,
    uri: str,
    *,
    schema_version: str = "pm-canonical-v2.1",
) -> DatasetBundleFile:
    file_format = "jsonl" if role.startswith("prediction_") else "csv"
    media_type = "application/x-ndjson" if file_format == "jsonl" else "text/csv"
    return DatasetBundleFile(
        role=role,
        uri=uri,
        format=file_format,
        media_type=media_type,
        checksum_sha256=checksum,
        size_bytes=1024,
        schema=BundleFileSchemaMetadata(
            schema_version=schema_version,
            required_fields=["asset_id"],
            primary_key=["asset_id"],
            timestamp_field="observed_at" if "observation" in role else None,
            timezone="UTC",
        ),
    )


def runtime_files(root: str = "/private/tmp/package") -> list[DatasetBundleFile]:
    return [
        bundle_file("asset_master", SHA_A, f"file://{root}/canonical/dataset/asset_master.csv"),
        bundle_file(
            "prediction_snapshot",
            SHA_B,
            f"file://{root}/canonical/model_outputs/prediction_snapshot.jsonl",
        ),
    ]


def checksum_for(
    *,
    files: list[DatasetBundleFile] | None = None,
    generation_metadata: BundleGenerationMetadata | None = None,
    schema_version: str = "pm-bundle-v2.0",
) -> str:
    return compute_bundle_checksum(
        dataset_version="canonical-independent-v1.0",
        schema_version=schema_version,
        generation=generation_metadata or generation(),
        source_contract=source_contract(),
        files=files or runtime_files(),
    )


def valid_manifest(files: list[DatasetBundleFile] | None = None) -> DatasetBundleManifestV2:
    selected_files = files or runtime_files()
    return DatasetBundleManifestV2(
        manifest_id="pm-canonical-v2-20260804",
        organization_id="org-ontology-demo",
        project_id="predictive-maintenance-v2",
        workspace_id="predictive-maintenance-main",
        adapter_code="predictive-maintenance-canonical-v2",
        dataset_name="Predictive Maintenance Canonical v2",
        dataset_version="canonical-independent-v1.0",
        schema_version="pm-bundle-v2.0",
        bundle_checksum_sha256=checksum_for(files=selected_files),
        generation=generation(),
        source_contract=source_contract(),
        files=selected_files,
        created_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )


def test_new_and_existing_json_schemas_parse_and_are_valid() -> None:
    schema_names = [
        "dataset-manifest.schema.json",
        "prediction-result.schema.json",
        "dataset-bundle-manifest.schema.json",
        "project3-graph-projection.schema.json",
    ]
    for name in schema_names:
        Draft202012Validator.check_schema(load_schema(name))


def test_bundle_manifest_validates_with_pydantic_and_json_schema() -> None:
    manifest = valid_manifest()
    payload = manifest.model_dump(mode="json", by_alias=True)
    errors = list(
        Draft202012Validator(
            load_schema("dataset-bundle-manifest.schema.json"),
            format_checker=FormatChecker(),
        ).iter_errors(payload)
    )
    assert errors == []


def test_bundle_checksum_ignores_file_order_and_local_absolute_path() -> None:
    first = runtime_files("/Users/alice/project/package")
    second = list(reversed(runtime_files("/mnt/ci/build/package")))

    assert checksum_for(files=first) == checksum_for(files=second)


def test_bundle_checksum_changes_for_content_seed_period_or_schema() -> None:
    baseline = checksum_for()

    changed_checksum_files = runtime_files()
    changed_checksum_files[0] = changed_checksum_files[0].model_copy(
        update={"checksum_sha256": SHA_C}
    )
    changed_seed = generation(seed=43)
    changed_period = generation(
        period_end=datetime(2026, 9, 1, tzinfo=timezone.utc)
    )

    assert checksum_for(files=changed_checksum_files) != baseline
    assert checksum_for(generation_metadata=changed_seed) != baseline
    assert checksum_for(generation_metadata=changed_period) != baseline
    assert checksum_for(schema_version="pm-bundle-v2.1") != baseline


def test_manifest_rejects_checksum_that_does_not_match_canonical_content() -> None:
    payload = valid_manifest().model_dump(mode="python", by_alias=True)
    payload["bundle_checksum_sha256"] = SHA_C

    with pytest.raises(ValidationError, match="does not match canonical bundle content"):
        DatasetBundleManifestV2.model_validate(payload)


@pytest.mark.parametrize(
    ("role", "uri"),
    [
        ("failure_schedule", "file:///package/canonical/dataset/failure_schedule.csv"),
        ("asset_master", "file:///package/canonical/evaluation_truth/asset_master.csv"),
    ],
)
def test_evaluation_truth_cannot_enter_runtime_manifest(role: str, uri: str) -> None:
    with pytest.raises(ValidationError, match="evaluation truth|evaluation_truth"):
        bundle_file(role, SHA_A, uri)


def test_json_schema_rejects_evaluation_truth_runtime_uri() -> None:
    payload = valid_manifest().model_dump(mode="json", by_alias=True)
    payload["files"][0]["uri"] = (
        "file:///package/canonical/evaluation_truth/asset_master.csv"
    )
    errors = list(
        Draft202012Validator(load_schema("dataset-bundle-manifest.schema.json")).iter_errors(
            payload
        )
    )
    assert errors


def test_identity_and_source_reference_formats_are_stable() -> None:
    postgres = PostgreSQLObjectIdentity(
        organization_id="org-ontology-demo",
        project_id="predictive-maintenance-v2",
        workspace_id="predictive-maintenance-main",
        dataset_id="pm-canonical",
        dataset_version_id="dsv-001",
        object_type="equipment",
        source_identity="CNC-001",
    )
    neo4j = Neo4jProjectionIdentity(
        organization_id="org-ontology-demo",
        project_id="predictive-maintenance-v2",
        dataset_id="pm-canonical",
        dataset_version_id="dsv-001",
        object_type="equipment",
        source_identity="CNC-001",
    )
    reference = DatasetSourceReference(
        dataset_id="pm-canonical",
        dataset_version_id="dsv-001",
        role="cnc_sensor_observation",
        checksum_sha256=SHA_A,
        object_type="equipment",
        source_identity="CNC-001",
        window_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
        window_end=datetime(2026, 8, 1, 1, tzinfo=timezone.utc),
    )

    assert postgres.canonical_key() == (
        "org:org-ontology-demo:project:predictive-maintenance-v2:"
        "workspace:predictive-maintenance-main:dataset:pm-canonical:"
        "version:dsv-001:object:equipment:CNC-001"
    )
    assert neo4j.canonical_key() == (
        "org:org-ontology-demo:project:predictive-maintenance-v2:"
        "dataset:pm-canonical:version:dsv-001:object:equipment:CNC-001"
    )
    assert reference.render() == (
        f"dataset:pm-canonical:version:dsv-001:role:cnc_sensor_observation:sha256:{SHA_A}:"
        "object:equipment:CNC-001:window:2026-08-01T00:00:00Z/2026-08-01T01:00:00Z"
    )


def test_project3_graph_projection_draft_validates_status_and_scope() -> None:
    identity = Project3ProjectionIdentity(
        organization_id="org-ontology-demo",
        project_id="predictive-maintenance-v2",
        dataset_id="pm-canonical",
        dataset_version_id="dsv-001",
        object_type="equipment",
        source_identity="CNC-001",
    )
    request = Project3GraphProjectionRequest(
        projection_id="projection-001",
        idempotency_key=f"graph-projection:predictive-maintenance-v2:dsv-001:mapping-v1:{SHA_A}",
        organization_id="org-ontology-demo",
        project_id="predictive-maintenance-v2",
        workspace_id="predictive-maintenance-main",
        dataset_id="pm-canonical",
        dataset_version_id="dsv-001",
        bundle_checksum_sha256=SHA_A,
        mapping_version="mapping-v1",
        nodes=[
            Project3ProjectionNode(
                identity=identity,
                properties={"asset_type": "cnc"},
                source_reference=(
                    f"dataset:pm-canonical:version:dsv-001:role:asset_master:sha256:{SHA_A}:"
                    "object:equipment:CNC-001"
                ),
                source_sha256=SHA_A,
            )
        ],
        relationships=[],
        requested_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )
    response = Project3GraphProjectionResponse(
        projection_id="projection-001",
        status="blocked",
        error=Project3ProjectionError(
            code="project_not_ready",
            message="mapping approval is required",
            retryable=True,
            details={"mapping_version": "mapping-v1"},
        ),
        updated_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
    )

    schema = load_schema("project3-graph-projection.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert list(validator.iter_errors(request.model_dump(mode="json"))) == []
    assert list(validator.iter_errors(response.model_dump(mode="json"))) == []

    with pytest.raises(ValidationError, match="require an error"):
        Project3GraphProjectionResponse(
            projection_id="projection-001",
            status="failed",
            updated_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        )

    wrong_scope = identity.model_copy(update={"dataset_version_id": "dsv-002"})
    with pytest.raises(ValidationError, match="scope must match request envelope"):
        Project3GraphProjectionRequest(
            projection_id="projection-002",
            idempotency_key="projection-key",
            organization_id="org-ontology-demo",
            project_id="predictive-maintenance-v2",
            workspace_id="predictive-maintenance-main",
            dataset_id="pm-canonical",
            dataset_version_id="dsv-001",
            bundle_checksum_sha256=SHA_A,
            mapping_version="mapping-v1",
            nodes=[
                Project3ProjectionNode(
                    identity=wrong_scope,
                    properties={},
                    source_reference="dataset:pm-canonical:version:dsv-002",
                    source_sha256=SHA_A,
                )
            ],
            relationships=[],
            requested_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        )

from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from systems.generator.app.extraction.extraction_schema import (
    ExtractionReplayRequest,
    ExtractionRequest,
)
from systems.generator.app.extraction.mapping_repository import MappingRepository
from systems.generator.app.model_artifacts.model_artifact_service import (
    ModelArtifactCatalogService,
)
from systems.generator.app.main import create_app


def test_model_artifact_catalog_surfaces_invalid_versions_without_hiding_them(tmp_path):
    root = tmp_path / "artifacts"
    artifact = root / "cnc-risk" / "v1"
    artifact.mkdir(parents=True)
    (artifact / "manifest.json").write_text("{}", encoding="utf-8")
    (root / "cnc-risk" / "latest.json").write_text(
        json.dumps({"model_id": "cnc-risk", "model_version": "v1"}),
        encoding="utf-8",
    )

    service = ModelArtifactCatalogService(root)
    models = service.list_models()
    assert models == [
        {
            "model_id": "cnc-risk",
            "version_count": 1,
            "latest": "v1",
            "latest_valid": False,
        }
    ]
    version = service.inspect("cnc-risk", "v1")
    assert version["valid"] is False
    assert version["artifact_uri"] == "models_store/artifacts/cnc-risk/v1"
    assert version["validation_error"]
    assert str(tmp_path) not in json.dumps(version, ensure_ascii=False)


def test_mapping_catalog_is_versioned_deduplicated_and_content_addressed(tmp_path):
    root = tmp_path / "mappings"
    (root / "first").mkdir(parents=True)
    mapping = {
        "mapping_id": "cnc-protocol",
        "mapping_version": "2026-09-09",
        "status": "approved",
        "source_schema_fingerprint": "sha256:source-v1",
        "protocol_type": "sensor-jsonl",
        "fields": [],
    }
    raw = json.dumps(mapping, sort_keys=True).encode("utf-8")
    (root / "first" / "mapping.json").write_bytes(raw)
    (root / "duplicate.json").write_bytes(raw)

    repository = MappingRepository(search_roots=[root])
    items = repository.list_mappings()
    assert len(items) == 1
    assert items[0]["mapping_id"] == "cnc-protocol"
    assert items[0]["mapping_version"] == "2026-09-09"
    assert items[0]["status"] == "approved"
    assert items[0]["sha256"] == hashlib.sha256(raw).hexdigest()


def test_mapping_replay_requires_a_new_immutable_dataset_version():
    source = ExtractionRequest(
        request_id="request-1",
        idempotency_key="replay-key-1",
        run_id="replay-run-1",
        source_uri="data/source/input.jsonl",
        source_sha256="a" * 64,
        source_direction="received",
        source_run_manifest_uri="data/source/run-manifest.json",
        source_run_manifest_sha256="b" * 64,
        source_schema_version="v1",
        protocol_version="v1",
        mapping_id="cnc-protocol",
        mapping_version="2026-09-09",
        mapping_sha256="c" * 64,
        dataset_id="cnc-observations",
        dataset_version="window-20260909-map-new",
    )
    replay = ExtractionReplayRequest(
        replay_of_dataset_version="window-20260908-map-old",
        extraction=source,
    )
    assert replay.extraction.dataset_version == "window-20260909-map-new"

    with pytest.raises(ValidationError):
        ExtractionReplayRequest(
            replay_of_dataset_version="window-20260909-map-new",
            extraction=source,
        )


def test_generator_health_and_metrics_expose_bounded_runtime_state(monkeypatch):
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_BUILD_SHA", "a" * 40)
    client = TestClient(create_app())
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["build_sha"] == "a" * 40

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert f'generator_build_info{{sha="{"a" * 40}"}} 1' in metrics.text
    assert "generator_runtime_queue_depth" in metrics.text
    assert "generator_handoff_state" in metrics.text

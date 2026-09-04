"""Unit tests for Extraction Runtime Handoff Repository and Identity computation."""

import json
from pathlib import Path
import pytest

from systems.generator.generator_config import PATHS
from systems.generator.app.extraction.extraction_exception import (
    ExtractionHandoffIdentityConflictError,
)
from systems.generator.app.extraction.extraction_handoff_repository import (
    ExtractionHandoffRepository,
    compute_handoff_id,
    compute_runtime_job_id,
)
from systems.generator.app.extraction.extraction_schema import (
    ExtractionRuntimeHandoff,
    ExtractionRuntimeHandoffDataset,
    ExtractionRuntimeHandoffDelivery,
    ExtractionRuntimeHandoffLineage,
    ExtractionRuntimeHandoffRuntimeInput,
    ExtractionRuntimeHandoffSource,
)


@pytest.fixture
def sample_handoff():
    h_id = compute_handoff_id(
        dataset_id="gen-data-S01-L01",
        dataset_version="window-20260828T130000Z-map-d545f01d",
        observations_uri="data/observations/gen-data-S01-L01/window-20260828T130000Z-map-d545f01d/observations.jsonl",
        observations_sha256="a" * 64,
        source_kind="live_sensor",
        source_contract_version="generator-dataset-input-v1",
        source_schema_version="canonical-observation-v1",
        pipeline_contract_version="generator-prediction-result-v1",
    )
    return ExtractionRuntimeHandoff(
        handoff_schema_version="generator-extraction-runtime-handoff-v1",
        handoff_id=h_id,
        status="pending",
        created_at="2026-08-28T14:00:00Z",
        updated_at="2026-08-28T14:00:00Z",
        dataset=ExtractionRuntimeHandoffDataset(
            dataset_id="gen-data-S01-L01",
            dataset_version="window-20260828T130000Z-map-d545f01d",
            manifest_uri="data/observations/gen-data-S01-L01/window-20260828T130000Z-map-d545f01d/dataset_manifest.json",
            observations_uri="data/observations/gen-data-S01-L01/window-20260828T130000Z-map-d545f01d/observations.jsonl",
            observations_sha256="a" * 64,
            observations_size_bytes=2048,
        ),
        runtime_input=ExtractionRuntimeHandoffRuntimeInput(
            dataset_id="gen-data-S01-L01",
            dataset_version="window-20260828T130000Z-map-d545f01d",
            source=ExtractionRuntimeHandoffSource(
                source_uri="data/observations/gen-data-S01-L01/window-20260828T130000Z-map-d545f01d/observations.jsonl",
                source_checksum="a" * 64,
                source_kind="live_sensor",
                source_contract_version="generator-dataset-input-v1",
                source_schema_version="canonical-observation-v1",
                pipeline_contract_version="generator-prediction-result-v1",
                lineage=ExtractionRuntimeHandoffLineage(),
            ),
        ),
        delivery=ExtractionRuntimeHandoffDelivery(
            attempt_count=0,
            runtime_job_id=None,
            queue_item_id=None,
            last_error_code=None,
            last_error_message=None,
            next_retry_at=None,
        ),
    )


def test_compute_handoff_id_deterministic():
    id1 = compute_handoff_id(
        dataset_id="ds-1",
        dataset_version="v1",
        observations_uri="data/obs.jsonl",
        observations_sha256="0" * 64,
    )
    id2 = compute_handoff_id(
        dataset_id="ds-1",
        dataset_version="v1",
        observations_uri="data/obs.jsonl",
        observations_sha256="0" * 64,
    )
    assert id1 == id2
    assert len(id1) == 64


def test_compute_runtime_job_id_format():
    h_id = "f" * 64
    job_id = compute_runtime_job_id(h_id)
    assert job_id == f"extraction-runtime-{'f' * 24}"


def test_save_and_find_handoff(tmp_path, sample_handoff):
    repo = ExtractionHandoffRepository(root_dir=tmp_path / "handoffs")
    saved_path = repo.save_handoff(sample_handoff)
    assert saved_path.is_file()
    assert saved_path.parent.name == "pending"

    found, found_path = repo.find_handoff_by_id(sample_handoff.handoff_id)
    assert found is not None
    assert found.handoff_id == sample_handoff.handoff_id
    assert found.status == "pending"
    assert found_path == saved_path


def test_handoff_state_transition(tmp_path, sample_handoff):
    repo = ExtractionHandoffRepository(root_dir=tmp_path / "handoffs")
    repo.save_handoff(sample_handoff)

    # Transition to enqueueing
    sample_handoff.status = "enqueueing"
    repo.save_handoff(sample_handoff)

    found, found_path = repo.find_handoff_by_id(sample_handoff.handoff_id)
    assert found is not None
    assert found.status == "enqueueing"
    assert found_path.parent.name == "enqueueing"
    assert not (tmp_path / "handoffs" / "pending" / f"{sample_handoff.handoff_id}.json").exists()

    # Transition to enqueued
    sample_handoff.status = "enqueued"
    sample_handoff.delivery.runtime_job_id = "extraction-runtime-job1"
    repo.save_handoff(sample_handoff)

    found2, found2_path = repo.find_handoff_by_id(sample_handoff.handoff_id)
    assert found2 is not None
    assert found2.status == "enqueued"
    assert found2.delivery.runtime_job_id == "extraction-runtime-job1"
    assert found2_path.parent.name == "enqueued"


def test_handoff_identity_conflict_raises(tmp_path, sample_handoff):
    repo = ExtractionHandoffRepository(root_dir=tmp_path / "handoffs")
    repo.save_handoff(sample_handoff)

    # Modify dataset checksum under same handoff ID
    conflict = sample_handoff.model_copy(deep=True)
    conflict.dataset.observations_sha256 = "b" * 64

    with pytest.raises(ExtractionHandoffIdentityConflictError):
        repo.save_handoff(conflict)


def test_count_by_status(tmp_path, sample_handoff):
    repo = ExtractionHandoffRepository(root_dir=tmp_path / "handoffs")
    repo.save_handoff(sample_handoff)

    counts = repo.count_by_status()
    assert counts["pending"] == 1
    assert counts["enqueued"] == 0
    assert counts["blocked"] == 0


def test_compute_handoff_id_default_contract_version_matches_explicit():
    """Verify that default source_contract_version matches explicit 'generator-dataset-input-v1'."""
    id_default = compute_handoff_id(
        dataset_id="gen-data-S01-L01",
        dataset_version="window-20260828T130000Z-map-d545f01d",
        observations_uri="data/observations/gen-data-S01-L01/window-20260828T130000Z-map-d545f01d/observations.jsonl",
        observations_sha256="a" * 64,
    )
    id_explicit = compute_handoff_id(
        dataset_id="gen-data-S01-L01",
        dataset_version="window-20260828T130000Z-map-d545f01d",
        observations_uri="data/observations/gen-data-S01-L01/window-20260828T130000Z-map-d545f01d/observations.jsonl",
        observations_sha256="a" * 64,
        source_contract_version="generator-dataset-input-v1",
    )
    assert id_default == id_explicit


def test_manifest_version_recorded_as_handoff_source_contract_version(tmp_path):
    """Verify that manifest_version read from dataset_manifest.json is recorded as source_contract_version."""
    from systems.generator.app.extraction.extraction_runtime_handoff_service import ExtractionRuntimeHandoffService

    man_path = tmp_path / "dataset_manifest.json"
    obs_path = tmp_path / "observations.jsonl"
    obs_content = b'{"val": 1.0}\n'
    obs_path.write_bytes(obs_content)
    import hashlib
    obs_sha = hashlib.sha256(obs_content).hexdigest()

    manifest = {
        "manifest_version": "generator-dataset-input-v1",
        "dataset_type": "observation",
        "dataset_id": "test-dataset",
        "dataset_version": "v1.0",
        "schema_version": "canonical-observation-v1",
        "created_at": "2026-08-28T14:00:00Z",
        "files": [
            {
                "role": "observations",
                "path": "observations.jsonl",
                "media_type": "application/x-ndjson",
                "sha256": obs_sha,
                "size_bytes": len(obs_content),
            }
        ],
    }
    man_path.write_text(json.dumps(manifest), encoding="utf-8")

    service = ExtractionRuntimeHandoffService(
        repository=ExtractionHandoffRepository(root_dir=tmp_path / "handoffs"),
    )
    handoff = service.create_or_get_handoff(man_path)
    assert handoff.runtime_input.source.source_contract_version == "generator-dataset-input-v1"
    assert handoff.handoff_id == compute_handoff_id(
        dataset_id="test-dataset",
        dataset_version="v1.0",
        observations_uri=handoff.dataset.observations_uri,
        observations_sha256=obs_sha,
        source_contract_version="generator-dataset-input-v1",
    )

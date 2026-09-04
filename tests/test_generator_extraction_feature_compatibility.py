"""Regression test verifying that datasets published by Extraction are strictly resolvable by FeatureInputResolver."""

import hashlib
import json
from pathlib import Path
import pytest

from systems.generator.file_integrity import compute_file_sha256
from systems.generator.generator_config import PATHS
from systems.generator.app.feature.feature_input_resolver import (
    FeatureInputResolver,
    ResolvedFeatureInput,
)
from systems.generator.app.feature.feature_repository import (
    FeatureRepository,
)


def test_feature_input_resolver_consumes_extraction_published_dataset(tmp_path, monkeypatch):
    """FeatureInputResolver successfully resolves and validates an extraction-published dataset directory."""
    dataset_id = "gen-data-S01-L01"
    dataset_version = "window-testcompat-20260828T130000Z"

    obs_root = tmp_path / "data" / "observations" / dataset_id / dataset_version
    obs_root.mkdir(parents=True, exist_ok=True)

    obs_file = obs_root / "observations.jsonl"
    obs_bytes = b'{"asset_id":"CNC-01","observed_at":"2026-08-28T13:10:00Z","measurements":{"torque_nm":40.0}}\n'
    obs_file.write_bytes(obs_bytes)
    obs_sha = compute_file_sha256(obs_file)

    prov_file = obs_root / "provenance.jsonl"
    prov_bytes = b'{"asset_id":"CNC-01","observed_at":"2026-08-28T13:10:00Z","measurement_key":"torque_nm","source_observation_id":"s-01","source_sequence":1,"source_direction":"forward","mapping_id":"m1","mapping_version":"v1","mapping_sha256":"0000000000000000000000000000000000000000000000000000000000000000","extraction_run_id":"r1"}\n'
    prov_file.write_bytes(prov_bytes)
    prov_sha = compute_file_sha256(prov_file)

    rej_file = obs_root / "rejected.jsonl"
    rej_file.write_bytes(b"")
    rej_sha = compute_file_sha256(rej_file)

    manifest = {
        "manifest_version": "generator-dataset-input-v1",
        "dataset_type": "observation",
        "dataset_id": dataset_id,
        "dataset_version": dataset_version,
        "schema_version": "canonical-observation-v1",
        "created_at": "2026-08-28T13:00:00Z",
        "files": [
            {
                "role": "observations",
                "path": "observations.jsonl",
                "media_type": "application/x-ndjson",
                "sha256": obs_sha,
                "size_bytes": len(obs_bytes),
            }
        ],
        "auxiliary_files": [
            {
                "role": "provenance",
                "path": "provenance.jsonl",
                "media_type": "application/x-ndjson",
                "sha256": prov_sha,
                "size_bytes": len(prov_bytes),
            },
            {
                "role": "rejected",
                "path": "rejected.jsonl",
                "media_type": "application/x-ndjson",
                "sha256": rej_sha,
                "size_bytes": 0,
            }
        ],
    }

    manifest_file = obs_root / "dataset_manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    monkeypatch.setattr(PATHS, "data_dir", tmp_path / "data")
    monkeypatch.setattr(PATHS, "observations_root", tmp_path / "data" / "observations")

    resolver = FeatureInputResolver()
    resolved: ResolvedFeatureInput = resolver.resolve_dataset("observation", dataset_id, dataset_version)

    assert resolved.dataset_id == dataset_id
    assert resolved.dataset_version == dataset_version
    assert resolved.schema_version == "canonical-observation-v1"
    assert resolved.payload_path == obs_file
    assert resolved.payload_sha256 == obs_sha
    assert resolved.manifest_path == manifest_file

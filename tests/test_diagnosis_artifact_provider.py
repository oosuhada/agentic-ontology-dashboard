from __future__ import annotations

import hashlib
import json

from systems.backend.app.diagnosis.artifact_provider import LocalModelArtifactProvider


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def test_legacy_repository_qualified_runtime_alias_is_read_compatible(
    tmp_path,
    monkeypatch,
) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    model_payload = b"legacy-model"
    schema_payload = json.dumps({"features": []}).encode("utf-8")
    (artifact / "model.joblib").write_bytes(model_payload)
    (artifact / "feature_schema.json").write_bytes(schema_payload)
    (artifact / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_type": "predictive_maintenance_model",
                "artifact_schema_version": "model-artifact-v1.0",
                "model_id": "legacy-runtime-model",
                "model_version": "v1",
                "dataset_version": "dataset-v1",
                "feature_schema_version": "feature-v1",
                "created_at": "2026-09-02T00:00:00Z",
                "training_config": {},
                "metrics": {},
                "checksum": "manifest-checksum-not-used-for-file-validation",
                "provenance": {},
                "compatibility": {
                    "runtime": "ontology_dashboard.systems.backend.diagnosis"
                },
                "artifact_files": [
                    {
                        "role": "model",
                        "path": "model.joblib",
                        "sha256": _sha256(model_payload),
                    },
                    {
                        "role": "feature_schema",
                        "path": "feature_schema.json",
                        "sha256": _sha256(schema_payload),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    sentinel_model = object()
    monkeypatch.setattr(
        "systems.backend.app.diagnosis.artifact_provider.joblib.load",
        lambda _path: sentinel_model,
    )

    loaded = LocalModelArtifactProvider(artifact).load()

    assert loaded.model is sentinel_model
    assert loaded.manifest["compatibility"]["runtime"] == (
        "ontology_dashboard.systems.backend.diagnosis"
    )

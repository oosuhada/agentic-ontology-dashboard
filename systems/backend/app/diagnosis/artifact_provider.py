"""Injected Model Artifact provider for product runtime diagnosis."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib


ARTIFACT_TYPE = "predictive_maintenance_model"
ARTIFACT_SCHEMA_VERSION = "model-artifact-v1.0"
# Older published artifacts used the repository-qualified diagnosis namespace.
# It denotes the same runtime boundary as the current stable manifest value and
# remains read-compatible; do not accept arbitrary runtime strings here.
COMPATIBLE_DIAGNOSIS_RUNTIMES = {
    None,
    "app.diagnosis",
    "ontology_dashboard.systems.backend.diagnosis",
}
REQUIRED_MANIFEST_FIELDS = {
    "artifact_type",
    "artifact_schema_version",
    "model_id",
    "model_version",
    "dataset_version",
    "feature_schema_version",
    "created_at",
    "training_config",
    "metrics",
    "checksum",
    "provenance",
    "compatibility",
    "artifact_files",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_path(uri: str | Path) -> Path:
    text = str(uri)
    if text.startswith("file://"):
        return Path(text[7:]).expanduser().resolve()
    if "://" in text:
        raise ValueError(
            "unsupported MODEL_ARTIFACT_URI scheme; inject an object-storage/registry provider "
            "instead of coupling backend to generator storage"
        )
    return Path(text).expanduser().resolve()


@dataclass(frozen=True)
class LoadedModelArtifact:
    manifest: dict[str, Any]
    model: Any
    feature_schema: dict[str, Any]
    history_requirement: dict[str, Any]


class LocalModelArtifactProvider:
    """Read an immutable Model Artifact from an injected local/file URI."""

    def __init__(self, artifact_uri: str | Path) -> None:
        self.artifact_path = _local_path(artifact_uri)

    def _manifest_path(self) -> Path:
        if self.artifact_path.is_file():
            if self.artifact_path.name != "manifest.json":
                raise ValueError("MODEL_ARTIFACT_URI file must point to manifest.json")
            return self.artifact_path
        return self.artifact_path / "manifest.json"

    def load(self) -> LoadedModelArtifact:
        manifest_path = self._manifest_path()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        missing = sorted(REQUIRED_MANIFEST_FIELDS - manifest.keys())
        if missing:
            raise ValueError(f"Model Artifact manifest is missing fields: {missing}")
        if manifest["artifact_type"] != ARTIFACT_TYPE:
            raise ValueError("unexpected Model Artifact type")
        if manifest["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION:
            raise ValueError("unsupported Model Artifact schema version")

        compatibility = manifest.get("compatibility") or {}
        runtime = compatibility.get("runtime")
        if runtime not in COMPATIBLE_DIAGNOSIS_RUNTIMES:
            raise ValueError(f"Model Artifact is incompatible with diagnosis runtime: {runtime}")

        root = manifest_path.parent
        declared = {item["role"]: item for item in manifest["artifact_files"]}
        for required_role in ("model", "feature_schema"):
            if required_role not in declared:
                raise ValueError(f"Model Artifact is missing required file role: {required_role}")
        for item in manifest["artifact_files"]:
            path = root / item["path"]
            if not path.is_file():
                raise ValueError(f"Model Artifact file does not exist: {item['path']}")
            actual = _sha256(path)
            if actual != item["sha256"]:
                raise ValueError(f"Model Artifact checksum mismatch: {item['path']}")

        model_path = root / declared["model"]["path"]
        feature_schema_path = root / declared["feature_schema"]["path"]
        history_requirement = {}
        if "history_requirement" in declared:
            history_requirement_path = root / declared["history_requirement"]["path"]
            history_requirement = json.loads(history_requirement_path.read_text(encoding="utf-8"))
        return LoadedModelArtifact(
            manifest=manifest,
            model=joblib.load(model_path),
            feature_schema=json.loads(feature_schema_path.read_text(encoding="utf-8")),
            history_requirement=history_requirement,
        )

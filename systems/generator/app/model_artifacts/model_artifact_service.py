"""Read-only Model Artifact catalog and integrity inspection service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from systems.generator.generator_config import PATHS
from systems.generator.model.publisher import validate_model_artifact


class ModelArtifactCatalogService:
    def __init__(self, artifacts_root: Path | None = None) -> None:
        self.artifacts_root = (artifacts_root or (PATHS.models_store / "artifacts")).resolve()

    @staticmethod
    def _safe_identifier(value: str, field: str) -> str:
        cleaned = value.strip()
        if not cleaned or ".." in cleaned or "/" in cleaned or "\\" in cleaned:
            raise ValueError(f"invalid {field}")
        return cleaned

    def _model_dir(self, model_id: str) -> Path:
        return self.artifacts_root / self._safe_identifier(model_id, "model_id")

    def _artifact_dir(self, model_id: str, model_version: str) -> Path:
        return self._model_dir(model_id) / self._safe_identifier(model_version, "model_version")

    def list_models(self) -> list[dict[str, Any]]:
        if not self.artifacts_root.is_dir():
            return []
        items: list[dict[str, Any]] = []
        for model_dir in sorted(path for path in self.artifacts_root.iterdir() if path.is_dir()):
            versions = self.list_versions(model_dir.name)
            latest = self.latest(model_dir.name, required=False)
            items.append(
                {
                    "model_id": model_dir.name,
                    "version_count": len(versions),
                    "latest": None if latest is None else latest["model_version"],
                    "latest_valid": None if latest is None else latest["valid"],
                }
            )
        return items

    def list_versions(self, model_id: str) -> list[dict[str, Any]]:
        model_dir = self._model_dir(model_id)
        if not model_dir.is_dir():
            return []
        latest_version = None
        pointer = model_dir / "latest.json"
        if pointer.is_file():
            try:
                latest_version = str(json.loads(pointer.read_text(encoding="utf-8")).get("model_version") or "") or None
            except (json.JSONDecodeError, OSError):
                latest_version = None
        items: list[dict[str, Any]] = []
        for artifact_dir in sorted(
            (path for path in model_dir.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        ):
            inspected = self.inspect(model_id, artifact_dir.name)
            items.append(
                {
                    "model_id": model_id,
                    "model_version": artifact_dir.name,
                    "is_latest": artifact_dir.name == latest_version,
                    "valid": inspected["valid"],
                    "manifest_sha256": inspected.get("manifest_sha256"),
                    "created_at": inspected.get("created_at"),
                    "metrics": inspected.get("metrics") or {},
                    "validation_error": inspected.get("validation_error"),
                }
            )
        return items

    def latest(self, model_id: str, *, required: bool = True) -> dict[str, Any] | None:
        model_dir = self._model_dir(model_id)
        pointer = model_dir / "latest.json"
        if not pointer.is_file():
            if required:
                raise KeyError(f"latest pointer not found for model {model_id}")
            return None
        try:
            payload = json.loads(pointer.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"invalid latest pointer for model {model_id}: {exc}") from exc
        model_version = str(payload.get("model_version") or payload.get("active_version") or "").strip()
        if not model_version:
            raise ValueError(f"latest pointer has no model_version for model {model_id}")
        inspected = self.inspect(model_id, model_version)
        return {
            **inspected,
            "pointer": payload,
        }

    def inspect(self, model_id: str, model_version: str) -> dict[str, Any]:
        artifact_dir = self._artifact_dir(model_id, model_version)
        if not artifact_dir.is_dir():
            raise KeyError(f"model artifact not found: {model_id}/{model_version}")
        try:
            validated = validate_model_artifact(
                artifact_dir,
                expected_model_id=model_id,
                expected_model_version=model_version,
                load_model=False,
                artifacts_root=self.artifacts_root,
            )
            manifest = dict(validated.manifest)
            return {
                "model_id": model_id,
                "model_version": model_version,
                "artifact_uri": f"models_store/artifacts/{model_id}/{model_version}",
                "valid": True,
                "manifest_sha256": validated.manifest_checksum,
                "created_at": manifest.get("created_at") or manifest.get("published_at"),
                "manifest": manifest,
                "metrics": dict(validated.metrics),
                "feature_schema": dict(validated.feature_schema),
                "label_schema": dict(validated.label_schema),
                "history_requirement": dict(validated.history_requirement),
                "validation_error": None,
            }
        except Exception as exc:
            manifest: dict[str, Any] = {}
            metrics: dict[str, Any] = {}
            for name, target in (("manifest.json", manifest), ("metrics.json", metrics)):
                path = artifact_dir / name
                if path.is_file():
                    try:
                        target.update(json.loads(path.read_text(encoding="utf-8")))
                    except (json.JSONDecodeError, OSError, TypeError):
                        pass
            return {
                "model_id": model_id,
                "model_version": model_version,
                "artifact_uri": f"models_store/artifacts/{model_id}/{model_version}",
                "valid": False,
                "manifest_sha256": None,
                "created_at": manifest.get("created_at") or manifest.get("published_at"),
                "manifest": manifest,
                "metrics": metrics,
                "feature_schema": {},
                "label_schema": {},
                "history_requirement": {},
                "validation_error": str(exc),
            }


__all__ = ["ModelArtifactCatalogService"]

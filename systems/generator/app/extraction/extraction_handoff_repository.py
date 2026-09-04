"""Repository managing persistent Extraction-to-Runtime Handoff records."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import jsonschema

from systems.generator.generator_config import PATHS, PROJECT_ROOT
from systems.generator.app.extraction.extraction_exception import (
    ExtractionHandoffIdentityConflictError,
    ExtractionHandoffStatePersistFailedError,
)
from systems.generator.app.extraction.extraction_schema import (
    ExtractionRuntimeHandoff,
)

logger = logging.getLogger(__name__)

STATUS_SUBDIRS = [
    "pending",
    "runtime_disabled",
    "enqueueing",
    "enqueued",
    "retry_wait",
    "blocked",
    "retry_exhausted",
]

HANDOFF_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "schemas" / "generator-extraction-runtime-handoff.schema.json"


def compute_handoff_id(
    *,
    dataset_id: str,
    dataset_version: str,
    observations_uri: str,
    observations_sha256: str,
    source_kind: str = "live_sensor",
    source_contract_version: str = "generator-dataset-input-v1",
    source_schema_version: str = "canonical-observation-v1",
    pipeline_contract_version: str = "generator-prediction-result-v1",
) -> str:
    """Compute deterministic SHA-256 handoff ID from canonical dataset and contract properties."""
    canonical_payload = {
        "dataset_id": dataset_id.strip(),
        "dataset_version": dataset_version.strip(),
        "observations_sha256": observations_sha256.strip().lower(),
        "observations_uri": observations_uri.strip().replace("\\", "/"),
        "pipeline_contract_version": pipeline_contract_version.strip(),
        "source_contract_version": source_contract_version.strip(),
        "source_kind": source_kind.strip(),
        "source_schema_version": source_schema_version.strip(),
    }
    raw_bytes = json.dumps(
        canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(raw_bytes).hexdigest()


def compute_runtime_job_id(handoff_id: str) -> str:
    """Compute deterministic runtime job ID from handoff ID prefix."""
    clean_id = handoff_id.strip().lower()
    return f"extraction-runtime-{clean_id[:24]}"


class ExtractionHandoffRepository:
    """Persistent storage for Extraction -> Runtime Prediction Handoff records."""

    def __init__(self, root_dir: Optional[Path] = None) -> None:
        self.root_dir = root_dir or PATHS.extraction_handoffs_root
        self._schema_validator: Optional[jsonschema.Draft202012Validator] = None
        self.ensure_directories()

    def ensure_directories(self) -> None:
        """Create root and all status subdirectories."""
        self.root_dir.mkdir(parents=True, exist_ok=True)
        for s in STATUS_SUBDIRS:
            (self.root_dir / s).mkdir(parents=True, exist_ok=True)

    def _get_validator(self) -> jsonschema.Draft202012Validator:
        if self._schema_validator is None:
            if HANDOFF_SCHEMA_PATH.is_file():
                schema = json.loads(HANDOFF_SCHEMA_PATH.read_text(encoding="utf-8"))
            else:
                schema_path = Path.cwd() / HANDOFF_SCHEMA_PATH
                schema = json.loads(schema_path.read_text(encoding="utf-8"))
            self._schema_validator = jsonschema.Draft202012Validator(
                schema, format_checker=jsonschema.FormatChecker()
            )
        return self._schema_validator

    def find_handoff_by_id(
        self, handoff_id: str
    ) -> tuple[Optional[ExtractionRuntimeHandoff], Optional[Path]]:
        """Locate handoff record by handoff_id across all status subdirectories."""
        clean_id = handoff_id.strip().lower()
        for s in STATUS_SUBDIRS:
            candidate = self.root_dir / s / f"{clean_id}.json"
            if candidate.is_file():
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    handoff = ExtractionRuntimeHandoff.model_validate(data)
                    return handoff, candidate
                except Exception as exc:
                    logger.error(f"[ExtractionHandoffRepository] Failed to read handoff at {candidate}: {exc}")
        return None, None

    def save_handoff(
        self,
        handoff: ExtractionRuntimeHandoff,
    ) -> Path:
        """Atomically persist or transition handoff record to its target status directory."""
        self.ensure_directories()
        data = handoff.model_dump(mode="json")

        # Validate against JSON schema
        try:
            self._get_validator().validate(data)
        except jsonschema.ValidationError as e:
            raise ExtractionHandoffStatePersistFailedError(
                f"Handoff record failed JSON schema validation: {e.message}"
            ) from e

        # Check existing records for payload identity conflict
        existing, old_path = self.find_handoff_by_id(handoff.handoff_id)
        if existing is not None:
            if (
                existing.dataset.dataset_id != handoff.dataset.dataset_id
                or existing.dataset.dataset_version != handoff.dataset.dataset_version
                or existing.dataset.observations_sha256 != handoff.dataset.observations_sha256
            ):
                raise ExtractionHandoffIdentityConflictError(
                    f"Existing handoff ID '{handoff.handoff_id}' has conflicting dataset identity."
                )

        target_dir = self.root_dir / handoff.status
        target_file = target_dir / f"{handoff.handoff_id}.json"

        # Staging temporary file
        temp_file = target_dir / f".tmp_{uuid4().hex[:8]}_{handoff.handoff_id}.json"
        raw_json = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)

        try:
            temp_file.write_text(raw_json + "\n", encoding="utf-8")

            # Remove old file if moving across status directories
            if old_path is not None and old_path != target_file and old_path.is_file():
                try:
                    old_path.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning(f"[ExtractionHandoffRepository] Could not remove old handoff {old_path}: {e}")

            try:
                os.replace(temp_file, target_file)
            except OSError:
                if target_file.is_file():
                    target_file.unlink(missing_ok=True)
                shutil.move(str(temp_file), str(target_file))

            return target_file
        except Exception as exc:
            if temp_file.is_file():
                temp_file.unlink(missing_ok=True)
            if isinstance(exc, (ExtractionHandoffIdentityConflictError, ExtractionHandoffStatePersistFailedError)):
                raise
            raise ExtractionHandoffStatePersistFailedError(
                f"Failed to atomically write handoff record '{target_file}': {exc}"
            ) from exc

    def list_handoffs(
        self, status: Optional[str] = None
    ) -> list[ExtractionRuntimeHandoff]:
        """List handoff records filtered by status."""
        self.ensure_directories()
        results: list[ExtractionRuntimeHandoff] = []

        subdirs = [status] if status else STATUS_SUBDIRS
        for s in subdirs:
            s_dir = self.root_dir / s
            if not s_dir.is_dir():
                continue
            for jfile in sorted(s_dir.glob("*.json")):
                if jfile.name.startswith("."):
                    continue
                try:
                    data = json.loads(jfile.read_text(encoding="utf-8"))
                    results.append(ExtractionRuntimeHandoff.model_validate(data))
                except Exception as exc:
                    logger.warning(f"[ExtractionHandoffRepository] Skipping invalid handoff file {jfile}: {exc}")
        return results

    def count_by_status(self) -> dict[str, int]:
        """Count handoff files grouped by status."""
        self.ensure_directories()
        counts: dict[str, int] = {}
        for s in STATUS_SUBDIRS:
            s_dir = self.root_dir / s
            if s_dir.is_dir():
                counts[s] = sum(
                    1 for f in s_dir.glob("*.json") if not f.name.startswith(".")
                )
            else:
                counts[s] = 0
        return counts

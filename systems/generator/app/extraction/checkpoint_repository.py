"""Mutable run state, atomic checkpoint, and fragment storage repository for extraction runs."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from systems.generator.generator_config import PATHS

logger = logging.getLogger(__name__)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write_json(file_path: Path, data: dict[str, Any]) -> None:
    """Atomically write JSON data using a temporary file with flush/fsync and os.replace."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_name(f".tmp_{file_path.name}_{os.getpid()}_{time.time_ns()}")
    content = json.dumps(data, indent=2, ensure_ascii=False)
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        for attempt in range(5):
            try:
                os.replace(str(temp_path), str(file_path))
                return
            except (PermissionError, OSError):
                if attempt < 4:
                    time.sleep(0.01)
                else:
                    raise
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


class CheckpointRepository:
    """Manages mutable extraction run state, step checkpoints, and batch fragments atomically."""

    def __init__(self, runs_root: Optional[Path] = None) -> None:
        self.runs_root = runs_root or (PATHS.data_preprocessed / "extraction_runs")

    def _get_run_dir(self, run_id: str) -> Path:
        p = self.runs_root / run_id
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save_run_state(
        self,
        run_id: str,
        status: str,
        stage: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Path:
        """Persist high-level run state (e.g. running, staging, succeeded, failed)."""
        run_dir = self._get_run_dir(run_id)
        state_file = run_dir / "run_state.json"
        payload = {
            "run_id": run_id,
            "status": status,
            "stage": stage,
            "updated_at": now_utc_iso(),
            "metadata": metadata or {},
        }
        _atomic_write_json(state_file, payload)
        return state_file

    def get_run_state(self, run_id: str) -> Optional[dict[str, Any]]:
        """Load run state if exists."""
        state_file = self._get_run_dir(run_id) / "run_state.json"
        if not state_file.is_file():
            return None
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_checkpoint(
        self,
        run_id: str,
        source_identity: str,
        source_offset: int,
        last_sequence: Optional[int] = None,
        last_committed_batch_id: Optional[str] = None,
        processed_count: int = 0,
        rejected_count: int = 0,
        duplicate_count: int = 0,
    ) -> Path:
        """Advance checkpoint only after observations and dedup are committed."""
        run_dir = self._get_run_dir(run_id)
        chk_file = run_dir / "checkpoint.json"
        payload = {
            "run_id": run_id,
            "source_identity": source_identity,
            "source_offset": source_offset,
            "last_sequence": last_sequence,
            "last_committed_batch_id": last_committed_batch_id,
            "processed_count": processed_count,
            "rejected_count": rejected_count,
            "duplicate_count": duplicate_count,
            "updated_at": now_utc_iso(),
        }
        _atomic_write_json(chk_file, payload)
        return chk_file

    def get_checkpoint(self, run_id: str) -> Optional[dict[str, Any]]:
        """Load checkpoint if exists."""
        chk_file = self._get_run_dir(run_id) / "checkpoint.json"
        if not chk_file.is_file():
            return None
        try:
            return json.loads(chk_file.read_text(encoding="utf-8"))
        except Exception:
            return None

    # --- Batch Fragment Storage ---

    def write_batch_fragment(
        self,
        run_id: str,
        batch_id: str,
        obs_records: list[dict[str, Any]],
        prov_records: list[dict[str, Any]],
        rej_records: list[dict[str, Any]],
    ) -> tuple[str, str, str]:
        """Write batch fragments to committed_fragments directory with flush and fsync."""
        frag_dir = self._get_run_dir(run_id) / "committed_fragments"
        frag_dir.mkdir(parents=True, exist_ok=True)

        def _write_records(filename: str, records: list[dict[str, Any]]) -> str:
            target = frag_dir / filename
            lines = [json.dumps(r, ensure_ascii=False) for r in records]
            content = ("\n".join(lines) + "\n").encode("utf-8") if lines else b""
            with open(target, "wb") as f:
                f.write(content)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            return hashlib.sha256(content).hexdigest()

        obs_sha = _write_records(f"{batch_id}.observations.jsonl", obs_records)
        prov_sha = _write_records(f"{batch_id}.provenance.jsonl", prov_records)
        rej_sha = _write_records(f"{batch_id}.rejected.jsonl", rej_records)
        return obs_sha, prov_sha, rej_sha

    def load_committed_fragments(
        self,
        run_id: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        """Load all committed fragments for run in order."""
        frag_dir = self._get_run_dir(run_id) / "committed_fragments"
        if not frag_dir.is_dir():
            return [], [], []

        all_obs: list[dict[str, Any]] = []
        all_prov: list[dict[str, Any]] = []
        all_rej: list[dict[str, Any]] = []

        for f in sorted(frag_dir.glob("*.observations.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    all_obs.append(json.loads(line))

        for f in sorted(frag_dir.glob("*.provenance.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    all_prov.append(json.loads(line))

        for f in sorted(frag_dir.glob("*.rejected.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    all_rej.append(json.loads(line))

        return all_obs, all_prov, all_rej


# =============================================================================
# GenData Streaming Append Checkpoint Management
# =============================================================================

from typing import Literal
from uuid import uuid4
import jsonschema
from pydantic import BaseModel, Field
from systems.generator.app.extraction.extraction_exception import (
    ExtractionCheckpointInvalidError,
    ExtractionCheckpointMappingMigrationRequiredError,
    ExtractionCheckpointReadFailedError,
    ExtractionCheckpointScopeConflictError,
    ExtractionCheckpointVerifyFailedError,
    ExtractionCheckpointWriteFailedError,
    ExtractionRequestInvalidError,
)
from systems.generator.app.extraction.gen_data_source import GenDataSensorStreamSource


class PendingExtractionBatch(BaseModel):
    """Metadata for an intermediate fragment awaiting commit."""

    batch_id: str
    run_id: str
    source_start_offset: int
    source_end_offset: int
    source_start_line: int
    source_end_line: int
    record_count: int
    observation_count: int
    rejected_count: int
    mapping_id: str
    mapping_version: str
    mapping_sha256: str
    fragment_manifest_uri: str
    fragment_manifest_sha256: str
    staged_at: str


class GenDataExtractionCheckpoint(BaseModel):
    """Durable state tracking byte offset, verified prefix, and staged batches per append stream source."""

    checkpoint_schema_version: Literal["generator-gen-data-extraction-checkpoint-v1"] = (
        "generator-gen-data-extraction-checkpoint-v1"
    )
    source_identity: str
    source_uri: str
    source_format: Literal["gen_data_sensor_stream"] = "gen_data_sensor_stream"
    site_id: str
    cell_id: str

    mapping_id: str
    mapping_version: str
    mapping_sha256: str

    last_committed_offset: int
    last_committed_line: int
    last_observed_at: Optional[str] = None

    verified_prefix_length: int
    verified_prefix_sha256: str

    last_committed_batch_id: Optional[str] = None
    committed_batch_ids: list[str] = Field(default_factory=list)

    pending_batch: Optional[PendingExtractionBatch] = None

    status: Literal["idle", "processing", "fragment_staged", "failed"] = "idle"

    created_at: str
    updated_at: str


class GenDataExtractionCheckpointRepository:
    """Manages persistent JSON checkpoints and atomic state transitions for gen_data streams."""

    def __init__(
        self,
        checkpoints_root: Optional[Path] = None,
        schema_path: Optional[Path] = None,
    ) -> None:
        from systems.generator.generator_config import PATHS, PROJECT_ROOT

        self.checkpoints_root = Path(
            checkpoints_root or (PATHS.data_preprocessed / "extraction_state" / "gen_data" / "checkpoints")
        ).resolve()
        self.schema_path = Path(
            schema_path
            or (
                PROJECT_ROOT
                / "contracts"
                / "schemas"
                / "generator-gen-data-extraction-checkpoint.schema.json"
            )
        ).resolve()
        self._schema_cache: Optional[dict[str, Any]] = None

    def _get_schema(self) -> dict[str, Any]:
        if self._schema_cache is None:
            if not self.schema_path.is_file():
                raise ExtractionRequestInvalidError(f"Checkpoint schema file not found: {self.schema_path}")
            try:
                self._schema_cache = json.loads(self.schema_path.read_text(encoding="utf-8"))
            except Exception as e:
                raise ExtractionRequestInvalidError(f"Failed to parse checkpoint schema: {e}") from e
        return self._schema_cache

    def validate_checkpoint_dict(self, data: dict[str, Any]) -> None:
        """Validate raw dictionary against official JSON Schema."""
        schema = self._get_schema()
        try:
            validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
            validator.validate(data)
        except jsonschema.ValidationError as exc:
            raise ExtractionCheckpointInvalidError(
                f"Checkpoint schema validation failed: {exc.message}",
                details=[{"path": list(exc.path), "error": exc.message}],
            ) from exc

    def load_checkpoint(self, source_identity: str) -> Optional[GenDataExtractionCheckpoint]:
        """Load checkpoint for given source_identity if exists."""
        chk_path = self.checkpoints_root / f"{source_identity}.json"
        if not chk_path.is_file():
            return None

        try:
            raw_bytes = chk_path.read_bytes()
        except OSError as exc:
            raise ExtractionCheckpointReadFailedError(
                f"Failed to read checkpoint for source '{source_identity}': {exc}"
            ) from exc

        try:
            raw_data = json.loads(raw_bytes.decode("utf-8"))

            # Check legacy checkpoint missing mapping identity before full schema validation
            if (
                not raw_data.get("mapping_id")
                or not raw_data.get("mapping_version")
                or not raw_data.get("mapping_sha256")
            ):
                raise ExtractionCheckpointMappingMigrationRequiredError(
                    f"Checkpoint for source '{source_identity}' is missing mapping identity and requires migration."
                )

            self.validate_checkpoint_dict(raw_data)
            checkpoint = GenDataExtractionCheckpoint.model_validate(raw_data)
            if checkpoint.source_identity != source_identity:
                raise ExtractionCheckpointInvalidError(
                    f"Checkpoint filename identity '{source_identity}' does not match payload source_identity '{checkpoint.source_identity}'.",
                    details=[{
                        "checkpoint_file_identity": source_identity,
                        "payload_source_identity": checkpoint.source_identity,
                    }],
                )
            return checkpoint
        except Exception as exc:
            if isinstance(exc, (
                ExtractionCheckpointInvalidError,
                ExtractionCheckpointMappingMigrationRequiredError,
                ExtractionCheckpointReadFailedError,
                ExtractionCheckpointScopeConflictError,
            )):
                raise
            raise ExtractionCheckpointInvalidError(
                f"Failed to read checkpoint for source '{source_identity}': {exc}"
            ) from exc

    def find_checkpoint_by_source(
        self,
        source: Any,
    ) -> Optional[GenDataExtractionCheckpoint]:
        """Find checkpoint matching source_uri and scope (used when source_identity cannot be derived)."""
        if not self.checkpoints_root.is_dir():
            return None

        source_uri = getattr(source, "source_uri", None)
        site_id = getattr(source, "site_id", None)
        cell_id = getattr(source, "cell_id", None)

        if not source_uri or not site_id or not cell_id:
            return None

        matching_checkpoints: list[GenDataExtractionCheckpoint] = []

        for chk_file in sorted(self.checkpoints_root.glob("*.json")):
            if chk_file.name.startswith(".tmp_"):
                continue

            try:
                raw_bytes = chk_file.read_bytes()
            except OSError as exc:
                raise ExtractionCheckpointReadFailedError(
                    f"Failed to read checkpoint file '{chk_file.name}' from storage: {exc}"
                ) from exc

            try:
                raw_data = json.loads(raw_bytes.decode("utf-8"))
            except Exception as exc:
                raise ExtractionCheckpointInvalidError(
                    f"Checkpoint file '{chk_file.name}' contains invalid JSON: {exc}"
                ) from exc

            if not isinstance(raw_data, dict):
                raise ExtractionCheckpointInvalidError(
                    f"Checkpoint file '{chk_file.name}' must contain a JSON object."
                )

            file_source_uri = raw_data.get("source_uri")
            file_site_id = raw_data.get("site_id")
            file_cell_id = raw_data.get("cell_id")

            # Exact scope matching (no None wildcard allowed)
            if (
                file_source_uri == source_uri
                and file_site_id == site_id
                and file_cell_id == cell_id
            ):
                chk = self.load_checkpoint(chk_file.stem)
                if chk is not None:
                    matching_checkpoints.append(chk)

        if len(matching_checkpoints) == 0:
            return None
        if len(matching_checkpoints) == 1:
            return matching_checkpoints[0]

        matched_ids = [c.source_identity for c in matching_checkpoints]
        raise ExtractionCheckpointScopeConflictError(
            f"Multiple checkpoints found matching scope ({source_uri}, {site_id}, {cell_id}): {matched_ids}",
            details=[{
                "scope": {"source_uri": source_uri, "site_id": site_id, "cell_id": cell_id},
                "matching_identities": matched_ids,
            }],
        )


    def save_checkpoint_atomic(
        self,
        checkpoint: GenDataExtractionCheckpoint,
        failure_injector: Optional[Any] = None,
    ) -> Path:
        """Atomically persist checkpoint with flush/fsync and immediate read-back verification."""
        self.checkpoints_root.mkdir(parents=True, exist_ok=True)
        target_file = self.checkpoints_root / f"{checkpoint.source_identity}.json"
        temp_file = self.checkpoints_root / f".tmp_{uuid4().hex}_{checkpoint.source_identity}.json"

        checkpoint_dict = checkpoint.model_dump()
        self.validate_checkpoint_dict(checkpoint_dict)

        content = json.dumps(checkpoint_dict, indent=2, ensure_ascii=False) + "\n"

        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass

            if failure_injector:
                if checkpoint.status == "processing":
                    failure_injector("after_processing_checkpoint")
                elif checkpoint.status == "fragment_staged":
                    failure_injector("after_pending_checkpoint_written")
                elif checkpoint.status == "idle":
                    failure_injector("after_committed_checkpoint_written")

            try:
                os.replace(str(temp_file), str(target_file))
            except OSError as exc:
                raise ExtractionCheckpointWriteFailedError(
                    f"Failed to atomically persist checkpoint '{target_file}': {exc}"
                ) from exc

            # Read-back verification
            read_back_bytes = target_file.read_bytes()
            read_back_dict = json.loads(read_back_bytes.decode("utf-8"))
            self.validate_checkpoint_dict(read_back_dict)
            read_back_model = GenDataExtractionCheckpoint.model_validate(read_back_dict)

            # Compare core invariant fields
            if (
                read_back_model.source_identity != checkpoint.source_identity
                or read_back_model.last_committed_offset != checkpoint.last_committed_offset
                or read_back_model.status != checkpoint.status
                or read_back_model.last_committed_batch_id != checkpoint.last_committed_batch_id
            ):
                raise ExtractionCheckpointVerifyFailedError(
                    f"Read-back checkpoint verification failed for '{checkpoint.source_identity}'"
                )

            return target_file

        except Exception as exc:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
            if isinstance(exc, (ExtractionCheckpointInvalidError, ExtractionCheckpointVerifyFailedError)):
                raise
            raise ExtractionCheckpointWriteFailedError(
                f"Failed to atomically write checkpoint '{target_file}': {exc}"
            ) from exc

    def validate_checkpoint_source(
        self,
        checkpoint: GenDataExtractionCheckpoint,
        source: GenDataSensorStreamSource,
    ) -> None:
        """Cross-validate checkpoint identity and logical scope against source stream."""
        if checkpoint.source_uri != source.source_uri:
            raise ExtractionCheckpointInvalidError(
                f"Checkpoint source_uri mismatch: checkpoint='{checkpoint.source_uri}', source='{source.source_uri}'"
            )
        if checkpoint.site_id != source.site_id or checkpoint.cell_id != source.cell_id:
            raise ExtractionCheckpointInvalidError(
                f"Checkpoint scope mismatch: ({checkpoint.site_id}, {checkpoint.cell_id}) vs ({source.site_id}, {source.cell_id})"
            )

    def cleanup_orphan_tmp_files(self, retention_seconds: int = 3600) -> int:
        """Remove orphan temporary checkpoint files older than retention_seconds."""
        if not self.checkpoints_root.is_dir():
            return 0

        now = time.time()
        removed = 0
        for tmp_path in self.checkpoints_root.glob(".tmp_*"):
            try:
                if tmp_path.is_file() and (now - tmp_path.stat().st_mtime) > retention_seconds:
                    tmp_path.unlink()
                    removed += 1
            except Exception as exc:
                logger.warning(f"[CheckpointRepo] Failed to remove orphan tmp file '{tmp_path}': {exc}")
        return removed

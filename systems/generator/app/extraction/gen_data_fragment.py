"""Intermediate fragment storage and manifest management for append extraction."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional, Sequence, Union
from uuid import uuid4

import jsonschema
from pydantic import BaseModel, Field

from systems.generator.generator_config import PROJECT_ROOT
from systems.generator.app.extraction.extraction_exception import (
    ExtractionError,
    ExtractionFragmentConflictError,
    ExtractionFragmentVerifyFailedError,
    ExtractionFragmentWriteFailedError,
    ExtractionRequestInvalidError,
)
from systems.generator.app.extraction.gen_data_mapping import (
    CanonicalObservationCandidate,
    RejectedMappingRecord,
)
from systems.generator.app.extraction.parsers.gen_data_sensor_stream_parser import (
    RejectedGenDataRecord,
)

logger = logging.getLogger(__name__)


class FragmentFileDescriptor(BaseModel):
    """File metadata within a fragment manifest."""

    role: Literal["observations", "provenance", "rejected"]
    path: str
    sha256: str
    size_bytes: int


class ExtractionFragmentManifest(BaseModel):
    """Manifest describing an atomic batch extraction fragment."""

    fragment_schema_version: Literal["generator-extraction-fragment-v1"] = "generator-extraction-fragment-v1"
    batch_id: str
    run_id: str
    source_identity: str
    source_uri: str
    source_start_offset: int
    source_end_offset: int
    source_start_line: int
    source_end_line: int
    mapping_id: str
    mapping_version: str
    mapping_sha256: str
    record_count: int
    observation_count: int
    rejected_count: int
    files: list[FragmentFileDescriptor]
    created_at: str


class GenDataFragmentRepository:
    """Manages atomic creation, verification, and idempotent reuse of extraction fragments."""

    def __init__(
        self,
        base_runs_dir: Optional[Path] = None,
        schema_path: Optional[Path] = None,
    ) -> None:
        from systems.generator.generator_config import PATHS

        self.base_runs_dir = Path(base_runs_dir or PATHS.data_preprocessed / "extraction_runs").resolve()
        self.schema_path = Path(
            schema_path
            or (PROJECT_ROOT / "contracts" / "schemas" / "generator-extraction-fragment-manifest.schema.json")
        ).resolve()
        self._schema_cache: Optional[dict[str, Any]] = None

    def _get_schema(self) -> dict[str, Any]:
        if self._schema_cache is None:
            if not self.schema_path.is_file():
                raise ExtractionRequestInvalidError(f"Fragment manifest schema file not found: {self.schema_path}")
            try:
                self._schema_cache = json.loads(self.schema_path.read_text(encoding="utf-8"))
            except Exception as e:
                raise ExtractionRequestInvalidError(f"Failed to parse fragment manifest schema: {e}") from e
        return self._schema_cache

    def validate_manifest(self, manifest_dict: dict[str, Any]) -> None:
        """Validate fragment manifest dictionary against official JSON Schema."""
        schema = self._get_schema()
        try:
            validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
            validator.validate(manifest_dict)
        except jsonschema.ValidationError as exc:
            raise ExtractionFragmentVerifyFailedError(
                f"Fragment manifest schema validation failed: {exc.message}",
                details=[{"path": list(exc.path), "error": exc.message}],
            ) from exc

    def find_fragment_by_batch_id(
        self,
        *,
        batch_id: str,
        source_identity: str,
        source_start_offset: int,
        source_end_offset: int,
        mapping_id: str,
        mapping_version: str,
        mapping_sha256: str,
    ) -> Optional[tuple[Path, ExtractionFragmentManifest, str]]:
        """Search all run directories for an existing valid fragment matching the deterministic batch_id.

        Returns:
            tuple[Path, ExtractionFragmentManifest, str]: (fragment_dir, manifest, manifest_sha256) if exactly one valid match exists.
            None: If no candidate fragment exists.

        Raises:
            ExtractionFragmentConflictError: If multiple candidate directories exist, or if metadata/content conflicts.
            ExtractionFragmentVerifyFailedError: If a candidate directory exists but is corrupted or invalid.
        """
        if not self.base_runs_dir.is_dir():
            return None

        candidates: list[tuple[Path, ExtractionFragmentManifest, str]] = []

        for manifest_file in self.base_runs_dir.glob(f"*/fragments/{batch_id}/fragment_manifest.json"):
            frag_dir = manifest_file.parent
            if not frag_dir.is_dir():
                continue

            try:
                manifest_bytes = manifest_file.read_bytes()
            except OSError as exc:
                raise ExtractionFragmentWriteFailedError(
                    f"Failed to read existing extraction fragment '{batch_id}': {exc}"
                ) from exc
            manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

            # Verify manifest and files
            manifest = self.verify_fragment(frag_dir, expected_manifest_sha256=manifest_sha256)

            # Strict identity and scope check
            if (
                manifest.batch_id != batch_id
                or manifest.source_identity != source_identity
                or manifest.source_start_offset != source_start_offset
                or manifest.source_end_offset != source_end_offset
                or manifest.mapping_id != mapping_id
                or manifest.mapping_version != mapping_version
                or manifest.mapping_sha256 != mapping_sha256
            ):
                raise ExtractionFragmentConflictError(
                    f"Candidate fragment at '{frag_dir}' has conflicting identity or scope for batch_id '{batch_id}'."
                )

            candidates.append((frag_dir, manifest, manifest_sha256))

        if len(candidates) == 0:
            return None
        elif len(candidates) == 1:
            return candidates[0]
        else:
            raise ExtractionFragmentConflictError(
                f"Multiple duplicate fragments for batch_id '{batch_id}' found in runs: "
                f"{[str(c[0]) for c in candidates]}"
            )

    def save_fragment_atomic(
        self,
        *,
        run_id: str,
        batch_id: str,
        source_identity: str,
        source_uri: str,
        source_start_offset: int,
        source_end_offset: int,
        source_start_line: int,
        source_end_line: int,
        mapping_id: str,
        mapping_version: str,
        mapping_sha256: str,
        observations: Sequence[CanonicalObservationCandidate],
        rejected_records: Sequence[Union[RejectedMappingRecord, RejectedGenDataRecord]],
        failure_injector: Optional[Any] = None,
    ) -> tuple[Path, ExtractionFragmentManifest, str]:
        """Atomically stage and commit an extraction fragment in a dedicated directory.

        Returns (final_batch_dir, manifest, manifest_sha256).
        """
        fragments_root = self.base_runs_dir / run_id / "fragments"
        try:
            fragments_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ExtractionFragmentWriteFailedError(
                f"Failed to create fragment storage directory '{fragments_root}': {exc}"
            ) from exc
        final_batch_dir = fragments_root / batch_id

        # 1. Idempotency check: if final_batch_dir exists, verify exact match
        if final_batch_dir.is_dir():
            manifest_file = final_batch_dir / "fragment_manifest.json"
            if manifest_file.is_file():
                try:
                    manifest_raw = json.loads(manifest_file.read_text(encoding="utf-8"))
                    self.validate_manifest(manifest_raw)
                    existing_manifest = ExtractionFragmentManifest.model_validate(manifest_raw)
                    manifest_sha = hashlib.sha256(manifest_file.read_bytes()).hexdigest()

                    # Check batch_id and source_identity
                    if (
                        existing_manifest.batch_id == batch_id
                        and existing_manifest.source_identity == source_identity
                        and existing_manifest.source_start_offset == source_start_offset
                        and existing_manifest.source_end_offset == source_end_offset
                        and existing_manifest.mapping_sha256 == mapping_sha256
                    ):
                        logger.info(f"[FragmentRepo] Reusing existing identical fragment '{batch_id}'")
                        return final_batch_dir, existing_manifest, manifest_sha
                    else:
                        raise ExtractionFragmentConflictError(
                            f"Fragment directory '{final_batch_dir}' exists with conflicting metadata."
                        )
                except ExtractionFragmentConflictError:
                    raise
                except OSError as exc:
                    raise ExtractionFragmentWriteFailedError(
                        f"Failed to read existing extraction fragment '{batch_id}': {exc}"
                    ) from exc
                except Exception as exc:
                    raise ExtractionFragmentConflictError(
                        f"Fragment directory '{final_batch_dir}' exists but is corrupt: {exc}"
                    ) from exc
            else:
                raise ExtractionFragmentConflictError(
                    f"Fragment directory '{final_batch_dir}' exists without manifest."
                )

        temp_dir = fragments_root / f".tmp_{uuid4().hex}_{batch_id}"
        try:
            temp_dir.mkdir(parents=True, exist_ok=True)
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            # 2. Write observations.jsonl
            obs_file = temp_dir / "observations.jsonl"
            obs_lines = []
            for obs in observations:
                line_str = json.dumps(obs.to_observation_dict(), ensure_ascii=False) + "\n"
                obs_lines.append(line_str.encode("utf-8"))
            obs_bytes = b"".join(obs_lines)
            obs_file.write_bytes(obs_bytes)
            obs_sha256 = hashlib.sha256(obs_bytes).hexdigest()
            obs_size = len(obs_bytes)

            # 3. Write provenance.jsonl
            prov_file = temp_dir / "provenance.jsonl"
            prov_lines = []
            for obs in observations:
                prov_dict = obs.to_provenance_dict(extraction_run_id=run_id)
                prov_dict["batch_id"] = batch_id
                line_str = json.dumps(prov_dict, ensure_ascii=False) + "\n"
                prov_lines.append(line_str.encode("utf-8"))
            prov_bytes = b"".join(prov_lines)
            prov_file.write_bytes(prov_bytes)
            prov_sha256 = hashlib.sha256(prov_bytes).hexdigest()
            prov_size = len(prov_bytes)

            # 4. Write rejected.jsonl
            rej_file = temp_dir / "rejected.jsonl"
            rej_lines = []
            for rej in rejected_records:
                if isinstance(rej, RejectedMappingRecord):
                    rej_dict = {
                        "source_uri": rej.source_uri,
                        "source_byte_start": rej.source_byte_start,
                        "source_byte_end": rej.source_byte_end,
                        "source_line_number": rej.source_line_number,
                        "raw_sha256": rej.raw_sha256,
                        "error_stage": "mapping",
                        "error_code": rej.error_code,
                        "error_message": rej.error_message,
                        "mapping_id": rej.mapping_id,
                        "mapping_version": rej.mapping_version,
                        "rejected_at": now_iso,
                    }
                else:
                    rej_dict = {
                        "source_uri": source_uri,
                        "source_byte_start": rej.byte_start,
                        "source_byte_end": rej.byte_end,
                        "source_line_number": rej.line_number,
                        "raw_sha256": rej.raw_sha256,
                        "error_stage": "parse",
                        "error_code": rej.error_code,
                        "error_message": rej.error_message,
                        "mapping_id": mapping_id,
                        "mapping_version": mapping_version,
                        "rejected_at": now_iso,
                    }
                line_str = json.dumps(rej_dict, ensure_ascii=False) + "\n"
                rej_lines.append(line_str.encode("utf-8"))
            rej_bytes = b"".join(rej_lines)
            rej_file.write_bytes(rej_bytes)
            rej_sha256 = hashlib.sha256(rej_bytes).hexdigest()
            rej_size = len(rej_bytes)

            if failure_injector:
                failure_injector("after_fragment_files_written")

            # 5. Build and write manifest
            file_descriptors = [
                FragmentFileDescriptor(role="observations", path="observations.jsonl", sha256=obs_sha256, size_bytes=obs_size),
                FragmentFileDescriptor(role="provenance", path="provenance.jsonl", sha256=prov_sha256, size_bytes=prov_size),
                FragmentFileDescriptor(role="rejected", path="rejected.jsonl", sha256=rej_sha256, size_bytes=rej_size),
            ]

            manifest = ExtractionFragmentManifest(
                fragment_schema_version="generator-extraction-fragment-v1",
                batch_id=batch_id,
                run_id=run_id,
                source_identity=source_identity,
                source_uri=source_uri,
                source_start_offset=source_start_offset,
                source_end_offset=source_end_offset,
                source_start_line=source_start_line,
                source_end_line=source_end_line,
                mapping_id=mapping_id,
                mapping_version=mapping_version,
                mapping_sha256=mapping_sha256,
                record_count=len(observations) + len(rejected_records),
                observation_count=len(observations),
                rejected_count=len(rejected_records),
                files=file_descriptors,
                created_at=now_iso,
            )

            manifest_dict = manifest.model_dump()
            self.validate_manifest(manifest_dict)

            manifest_bytes = (json.dumps(manifest_dict, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            manifest_file = temp_dir / "fragment_manifest.json"
            manifest_file.write_bytes(manifest_bytes)
            manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

            if failure_injector:
                failure_injector("after_fragment_manifest_written")

            # 6. Atomic directory move / rename (NEVER delete final_batch_dir)
            try:
                os.replace(temp_dir, final_batch_dir)
            except OSError:
                if final_batch_dir.exists():
                    manifest_file = final_batch_dir / "fragment_manifest.json"
                    if manifest_file.is_file():
                        try:
                            m_bytes = manifest_file.read_bytes()
                            m_sha = hashlib.sha256(m_bytes).hexdigest()
                            existing_manifest = self.verify_fragment(final_batch_dir, expected_manifest_sha256=m_sha)
                            if (
                                existing_manifest.batch_id == batch_id
                                and existing_manifest.source_identity == source_identity
                                and existing_manifest.source_start_offset == source_start_offset
                                and existing_manifest.source_end_offset == source_end_offset
                                and existing_manifest.mapping_sha256 == mapping_sha256
                            ):
                                logger.info(f"[FragmentRepo] Atomic rename encountered identical existing fragment '{batch_id}'; reusing.")
                                return final_batch_dir, existing_manifest, m_sha
                        except ExtractionFragmentWriteFailedError:
                            raise
                        except Exception as exc:
                            raise ExtractionFragmentConflictError(
                                f"Fragment directory '{final_batch_dir}' exists but is corrupt: {exc}"
                            ) from exc
                    raise ExtractionFragmentConflictError(
                        f"Fragment directory '{final_batch_dir}' exists with conflicting content."
                    )
                raise ExtractionFragmentWriteFailedError(
                    f"Failed to atomically rename temporary fragment directory '{temp_dir}' to '{final_batch_dir}'"
                )

            if failure_injector:
                failure_injector("after_fragment_renamed")

            # 7. Final read-back verification
            self.verify_fragment(final_batch_dir, manifest_sha256)

            return final_batch_dir, manifest, manifest_sha256

        except ExtractionError:
            raise
        except OSError as exc:
            raise ExtractionFragmentWriteFailedError(
                f"Failed to write extraction fragment '{batch_id}': {exc}"
            ) from exc
        except Exception as exc:
            raise ExtractionFragmentWriteFailedError(
                f"Unexpected fragment publication failure for '{batch_id}': {exc}"
            ) from exc
        finally:
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except OSError:
                    logger.warning(
                        "[FragmentRepo] Failed to clean temporary fragment directory '%s'",
                        temp_dir,
                        exc_info=True,
                    )

    def verify_fragment(self, fragment_dir: Path, expected_manifest_sha256: Optional[str] = None) -> ExtractionFragmentManifest:
        """Read and strictly verify manifest and all file checksums in a fragment directory."""
        path = Path(fragment_dir).resolve()
        manifest_file = path / "fragment_manifest.json"
        if not manifest_file.is_file():
            raise ExtractionFragmentVerifyFailedError(f"Fragment manifest missing at '{manifest_file}'")

        try:
            manifest_bytes = manifest_file.read_bytes()
        except OSError as exc:
            raise ExtractionFragmentWriteFailedError(
                f"Failed to read fragment manifest '{manifest_file}': {exc}"
            ) from exc
        actual_manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()

        if expected_manifest_sha256 and actual_manifest_sha != expected_manifest_sha256:
            raise ExtractionFragmentVerifyFailedError(
                f"Fragment manifest checksum mismatch: expected {expected_manifest_sha256}, got {actual_manifest_sha}"
            )

        try:
            manifest_raw = json.loads(manifest_bytes.decode("utf-8"))
            self.validate_manifest(manifest_raw)
            manifest = ExtractionFragmentManifest.model_validate(manifest_raw)
        except Exception as exc:
            raise ExtractionFragmentVerifyFailedError(f"Failed to load fragment manifest: {exc}") from exc

        for fd in manifest.files:
            file_path = path / fd.path
            if not file_path.is_file():
                raise ExtractionFragmentVerifyFailedError(f"Fragment file '{fd.path}' missing at '{file_path}'")
            try:
                file_bytes = file_path.read_bytes()
            except OSError as exc:
                raise ExtractionFragmentWriteFailedError(
                    f"Failed to read fragment file '{file_path}': {exc}"
                ) from exc
            if len(file_bytes) != fd.size_bytes:
                raise ExtractionFragmentVerifyFailedError(
                    f"Fragment file '{fd.path}' size mismatch: expected {fd.size_bytes}, got {len(file_bytes)}"
                )
            calc_sha = hashlib.sha256(file_bytes).hexdigest()
            if calc_sha != fd.sha256:
                raise ExtractionFragmentVerifyFailedError(
                    f"Fragment file '{fd.path}' SHA-256 mismatch: expected {fd.sha256}, got {calc_sha}"
                )

        return manifest

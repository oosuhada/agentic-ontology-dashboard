"""Orchestration service for protocol extraction, parsing, dedup, and atomic publishing."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional, Protocol

import jsonschema

from systems.generator.generator_config import PATHS, PROJECT_ROOT
from systems.generator.file_integrity import compute_file_sha256
from systems.generator.app.extraction.extraction_exception import (
    ExtractionSourceNotFoundError,
    ExtractionSourcePathUnsupportedError,
    ExtractionSourceManifestRequiredError,
    ExtractionSourceManifestInvalidError,
    ExtractionSourceNotFinalizedError,
    ExtractionSourceDescriptorMismatchError,
    ExtractionSourceChecksumMismatchError,
    ExtractionProtocolUnsupportedError,
    ExtractionIdempotencyConflictError,
    ExtractionRequestInProgressError,
    ExtractionRequestInvalidError,
    ExtractionNoValidObservationsError,
    ExtractionError,
)
from systems.generator.app.extraction.extraction_schema import (
    ExtractionRequest,
    ExtractionResponse,
    ExtractionResultPayload,
    ExtractionTimeRange,
)
from systems.generator.app.extraction.mapping_repository import MappingRepository
from systems.generator.app.extraction.mapping_validator import (
    MappingValidator,
    compute_source_schema_fingerprint,
)
from systems.generator.app.extraction.parsers.sensor_record_parser import SensorRecordParser
from systems.generator.app.extraction.dedup_repository import DedupRepository
from systems.generator.app.extraction.checkpoint_repository import CheckpointRepository
from systems.generator.app.extraction.extraction_repository import ExtractionRepository

logger = logging.getLogger(__name__)


class ExtractionFailureInjector(Protocol):
    """Protocol for test-only fault injection hooks."""

    def hit(self, point: str) -> None:
        ...


class NoOpFailureInjector:
    """Default failure injector that performs no action."""

    def hit(self, point: str) -> None:
        pass


def compute_extraction_operation_sha256(
    request: ExtractionRequest,
    *,
    source_identity: str,
) -> str:
    """Compute canonical hash of business extraction operation excluding run IDs and request IDs."""
    payload = {
        "source_identity": source_identity,
        "source_direction": request.source_direction,
        "protocol_version": request.protocol_version,
        "source_schema_version": request.source_schema_version,
        "mapping_id": request.mapping_id,
        "mapping_version": request.mapping_version,
        "mapping_sha256": request.mapping_sha256,
        "dataset_id": request.dataset_id,
        "dataset_version": request.dataset_version,
    }
    canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class ExtractionService:
    """End-to-end orchestration service for gen_data protocol extraction."""

    def __init__(
        self,
        mapping_repo: Optional[MappingRepository] = None,
        mapping_validator: Optional[MappingValidator] = None,
        parser: Optional[SensorRecordParser] = None,
        dedup_repo: Optional[DedupRepository] = None,
        checkpoint_repo: Optional[CheckpointRepository] = None,
        extraction_repo: Optional[ExtractionRepository] = None,
        allowed_roots: Optional[list[Path]] = None,
        protocol_schema_path: Optional[Path] = None,
        run_manifest_schema_path: Optional[Path] = None,
        batch_size: int = 1000,
        lock_lease_seconds: float = 300.0,
        failure_injector: Optional[ExtractionFailureInjector] = None,
    ) -> None:
        self.mapping_repo = mapping_repo or MappingRepository(mapping_root=PATHS.mapping_root)
        self.mapping_validator = mapping_validator or MappingValidator()
        self.parser = parser or SensorRecordParser(mapping_validator=self.mapping_validator)
        self.dedup_repo = dedup_repo or DedupRepository(state_root=PATHS.extraction_state_root)
        self.checkpoint_repo = checkpoint_repo or CheckpointRepository(runs_root=PATHS.extraction_runs_root)
        self.extraction_repo = extraction_repo or ExtractionRepository(
            observations_root=PATHS.observations_root,
            runs_root=PATHS.extraction_runs_root,
        )
        self.allowed_roots = allowed_roots or [r.resolve() for r in PATHS.extraction_input_roots]
        self.protocol_schema_path = protocol_schema_path or (
            PROJECT_ROOT / "contracts" / "schemas" / "generator-protocol-record.schema.json"
        )
        self.run_manifest_schema_path = run_manifest_schema_path or (
            PROJECT_ROOT / "contracts" / "schemas" / "generator-protocol-run-manifest.schema.json"
        )
        self.batch_size = batch_size
        self.lock_lease_seconds = lock_lease_seconds
        self.failure_injector: ExtractionFailureInjector = failure_injector or NoOpFailureInjector()
        self._protocol_schema_cache: Optional[dict[str, Any]] = None
        self._run_manifest_schema_cache: Optional[dict[str, Any]] = None

    def _get_protocol_schema(self) -> dict[str, Any]:
        if self._protocol_schema_cache is None:
            if not self.protocol_schema_path.is_file():
                raise ExtractionRequestInvalidError(f"Protocol record schema missing: {self.protocol_schema_path}")
            self._protocol_schema_cache = json.loads(self.protocol_schema_path.read_text(encoding="utf-8"))
        return self._protocol_schema_cache

    def _get_run_manifest_schema(self) -> dict[str, Any]:
        if self._run_manifest_schema_cache is None:
            if not self.run_manifest_schema_path.is_file():
                raise ExtractionRequestInvalidError(f"Run manifest schema missing: {self.run_manifest_schema_path}")
            self._run_manifest_schema_cache = json.loads(self.run_manifest_schema_path.read_text(encoding="utf-8"))
        return self._run_manifest_schema_cache

    def _hit_failure_injector(self, point: str) -> None:
        """Invoke failure injector hook if configured."""
        if self.failure_injector is not None:
            self.failure_injector.hit(point)

    def _resolve_source_path(self, source_uri: str) -> Path:
        """Resolve and validate source URI strictly within allowed extraction input roots."""
        clean_uri = str(source_uri).strip().replace("\\", "/")
        if not clean_uri:
            raise ExtractionSourcePathUnsupportedError("source_uri가 비어 있습니다.")

        p = Path(clean_uri)
        if ".." in p.parts:
            raise ExtractionSourcePathUnsupportedError(
                f"source_uri에 상위 디렉터리 탐색(..)이 포함되어 있습니다: '{clean_uri}'"
            )

        resolved: Optional[Path] = None
        if p.is_absolute():
            resolved = p.resolve()
        else:
            candidates = [root / p for root in self.allowed_roots] + [PROJECT_ROOT / p]
            for c in candidates:
                if c.exists():
                    resolved = c.resolve()
                    break
            if resolved is None:
                resolved = (self.allowed_roots[0] / p).resolve()

        # Security check: must reside within one of the allowed_roots
        is_allowed = False
        for root in self.allowed_roots:
            try:
                resolved.relative_to(root.resolve())
                is_allowed = True
                break
            except ValueError:
                continue

        if not is_allowed:
            raise ExtractionSourcePathUnsupportedError(
                f"source_uri가 허용된 데이터 루트를 벗어났습니다: '{clean_uri}'",
                details=[{"source_uri": clean_uri, "resolved": str(resolved)}],
            )

        if not resolved.exists() or not resolved.is_file():
            raise ExtractionSourceNotFoundError(
                f"소스 파일을 찾을 수 없습니다: '{clean_uri}'",
                details=[{"source_uri": clean_uri, "resolved": str(resolved)}],
            )

        return resolved

    def _verify_source_finalization(
        self,
        request: ExtractionRequest,
    ) -> tuple[dict[str, Any], dict[str, Any], Path, str]:
        """Fail-closed validation of upstream source run manifest and descriptor."""
        if not request.source_run_manifest_uri:
            raise ExtractionSourceManifestRequiredError("source_run_manifest_uri가 누락되었습니다.")

        manifest_path = self._resolve_source_path(request.source_run_manifest_uri)
        actual_manifest_sha = compute_file_sha256(manifest_path)
        if actual_manifest_sha != request.source_run_manifest_sha256:
            raise ExtractionSourceChecksumMismatchError(
                f"source_run_manifest SHA-256 불일치: 요청={request.source_run_manifest_sha256}, 실제={actual_manifest_sha}",
                details=[{"expected": request.source_run_manifest_sha256, "actual": actual_manifest_sha}],
            )

        try:
            manifest_dict = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ExtractionSourceManifestInvalidError(
                f"source_run_manifest JSON 파싱 실패: {exc}",
                details=[{"manifest_uri": request.source_run_manifest_uri}],
            ) from exc

        # JSON Schema validation
        schema = self._get_run_manifest_schema()
        try:
            validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
            validator.validate(manifest_dict)
        except jsonschema.ValidationError as exc:
            raise ExtractionSourceManifestInvalidError(
                f"source_run_manifest 스키마 검증 실패: {exc.message}",
                details=[{"error": exc.message, "path": list(exc.path)}],
            ) from exc

        # Status check
        status = manifest_dict.get("status")
        if status not in ("completed", "finalized", "succeeded"):
            raise ExtractionSourceNotFinalizedError(
                f"상위 프로토콜 실행이 아직 완료되지 않았습니다: status='{status}'",
                details=[{"manifest_uri": request.source_run_manifest_uri, "status": status}],
            )

        # Version checks
        if manifest_dict.get("protocol_version") != request.protocol_version:
            raise ExtractionProtocolUnsupportedError(
                f"매니페스트 protocol_version('{manifest_dict.get('protocol_version')}')과 요청('{request.protocol_version}') 불일치"
            )
        if manifest_dict.get("source_schema_version") != request.source_schema_version:
            raise ExtractionProtocolUnsupportedError(
                f"매니페스트 source_schema_version('{manifest_dict.get('source_schema_version')}')과 요청('{request.source_schema_version}') 불일치"
            )

        # Resolve source file
        source_path = self._resolve_source_path(request.source_uri)
        actual_source_sha256 = compute_file_sha256(source_path)
        if actual_source_sha256 != request.source_sha256:
            raise ExtractionSourceChecksumMismatchError(
                f"소스 파일 SHA-256 체크섬 불일치: 요청={request.source_sha256}, 실제={actual_source_sha256}",
                details=[{"expected": request.source_sha256, "actual": actual_source_sha256}],
            )

        actual_source_size = source_path.stat().st_size

        # Find matching descriptor in manifest files
        manifest_files = manifest_dict.get("files", [])
        matched_descriptor: Optional[dict[str, Any]] = None
        for f_desc in manifest_files:
            desc_path = str(f_desc.get("path", "")).strip().replace("\\", "/")
            req_path = str(request.source_uri).strip().replace("\\", "/")
            if desc_path == req_path or Path(desc_path).name == Path(req_path).name or desc_path.endswith(req_path) or req_path.endswith(desc_path):
                matched_descriptor = f_desc
                break

        if matched_descriptor is None:
            raise ExtractionSourceDescriptorMismatchError(
                f"source_uri('{request.source_uri}')가 run manifest 선언 파일 목록에 없습니다.",
                details=[{"source_uri": request.source_uri, "manifest_files": manifest_files}],
            )

        if matched_descriptor.get("sha256") != actual_source_sha256:
            raise ExtractionSourceDescriptorMismatchError(
                f"매니페스트 파일 SHA-256('{matched_descriptor.get('sha256')}')과 실제 소스 파일 SHA-256('{actual_source_sha256}')이 일치하지 않습니다.",
                details=[{"declared_sha": matched_descriptor.get("sha256"), "actual_sha": actual_source_sha256}],
            )

        declared_size = matched_descriptor.get("size_bytes")
        if declared_size is not None and declared_size != actual_source_size:
            raise ExtractionSourceDescriptorMismatchError(
                f"매니페스트 파일 크기({declared_size} bytes)와 실제 소스 크기({actual_source_size} bytes)가 일치하지 않습니다."
            )

        return manifest_dict, matched_descriptor, source_path, actual_source_sha256

    def execute_extraction(self, request: ExtractionRequest) -> ExtractionResponse:
        """Execute full extraction workflow with validation, dedup, staging, and atomic publishing."""
        current_stage = "source_validation"

        try:
            # 1. Verify upstream source finalization & resolve source file
            manifest_dict, source_descriptor, source_path, actual_source_sha = self._verify_source_finalization(request)

            # Canonical Source Identity (independent of path URI representation)
            source_identity_payload = {
                "source_run_id": manifest_dict["run_id"],
                "source_file_role": source_descriptor.get("role", "protocol_log"),
                "source_sha256": actual_source_sha,
                "source_schema_version": request.source_schema_version,
                "protocol_version": request.protocol_version,
                "source_direction": request.source_direction,
            }
            source_identity = hashlib.sha256(
                json.dumps(source_identity_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            ).hexdigest()

            # Operation digest
            op_sha256 = compute_extraction_operation_sha256(request, source_identity=source_identity)

            # 2. Validate Mapping Table and Schema Fingerprint
            current_stage = "mapping_validation"
            mapping_data, _ = self.mapping_repo.load_mapping(
                request.mapping_id,
                request.mapping_version,
            )

            proto_schema = self._get_protocol_schema()
            actual_schema_fp = compute_source_schema_fingerprint(
                proto_schema,
                algorithm_version=mapping_data.get("fingerprint_algorithm_version", "v1"),
            )

            self.mapping_validator.validate_mapping(
                mapping_data=mapping_data,
                expected_mapping_id=request.mapping_id,
                expected_mapping_version=request.mapping_version,
                expected_mapping_sha256=request.mapping_sha256,
                expected_source_schema_fingerprint=actual_schema_fp,
            )

            # 3. Reserve Idempotency Key Atomically
            existing_response_dict = self.dedup_repo.reserve_idempotency_key(
                idempotency_key=request.idempotency_key,
                request_sha256=op_sha256,
                run_id=request.run_id,
            )
            if existing_response_dict is not None:
                # Validate existing dataset on disk before returning cached response
                target_dir = self.extraction_repo.get_target_dir(request.dataset_id, request.dataset_version)
                if (target_dir / "observations.jsonl").is_file():
                    logger.info(f"[ExtractionService] Returning cached idempotent response for key '{request.idempotency_key}'")
                    return ExtractionResponse.model_validate(existing_response_dict)

            self._hit_failure_injector("after_idempotency_reserved")

            # 4. Acquire Single-writer Lock Lease
            self.dedup_repo.acquire_lock(
                dataset_id=request.dataset_id,
                dataset_version=request.dataset_version,
                run_id=request.run_id,
                timeout_seconds=self.lock_lease_seconds,
            )
            self._hit_failure_injector("after_lock_acquired")

            current_stage = "parsing"
            self.checkpoint_repo.save_run_state(
                run_id=request.run_id,
                status="running",
                stage=current_stage,
                metadata={"request": request.model_dump()},
            )

            # 5. Checkpoint & Streaming Batch Processing Loop
            chk = self.checkpoint_repo.get_checkpoint(request.run_id)
            start_offset = 0
            if chk and chk.get("source_identity") == source_identity:
                start_offset = chk.get("source_offset", 0)

            # Parse records starting from start_offset
            observations, provenance_records, rejected_records, processed_source_records, stats = self.parser.parse_file(
                source_path=source_path,
                mapping_data=mapping_data,
                extraction_run_id=request.run_id,
                source_direction=request.source_direction,
                dedup_checker=self.dedup_repo,
                source_identity=source_identity,
                is_source_finalized=True,
                start_offset=start_offset,
            )

            # Load previously committed fragments if resuming from checkpoint
            committed_obs, committed_prov, committed_rej = self.checkpoint_repo.load_committed_fragments(request.run_id)
            if committed_obs:
                observations = committed_obs + observations
                provenance_records = committed_prov + provenance_records
                rejected_records = committed_rej + rejected_records

            if not observations:
                raise ExtractionNoValidObservationsError(
                    "유효한 Canonical Observation이 없어 Dataset을 발행할 수 없습니다.",
                    details=[{
                        "processed": stats["parsed_records"],
                        "rejected": stats["rejected_records"],
                    }],
                )

            # Process batch if new records were parsed
            end_offset = stats.get("end_byte_offset", stats["total_records"])
            if stats["parsed_records"] > 0 or not committed_obs:
                batch_id = hashlib.sha256(
                    f"{source_identity}:{start_offset}:{end_offset}".encode("utf-8")
                ).hexdigest()

                # Record batch pending
                current_stage = "batch_commit"
                self.dedup_repo.create_batch(
                    batch_id=batch_id,
                    run_id=request.run_id,
                    source_identity=source_identity,
                    source_start_offset=start_offset,
                    source_end_offset=end_offset,
                    record_count=stats["parsed_records"],
                    dataset_id=request.dataset_id,
                    dataset_version=request.dataset_version,
                )
                self._hit_failure_injector("after_batch_pending")

                # Write batch fragment
                new_obs = observations if not committed_obs else observations[len(committed_obs):]
                new_prov = provenance_records if not committed_prov else provenance_records[len(committed_prov):]
                new_rej = rejected_records if not committed_rej else rejected_records[len(committed_rej):]

                obs_sha, prov_sha, rej_sha = self.checkpoint_repo.write_batch_fragment(
                    run_id=request.run_id,
                    batch_id=batch_id,
                    obs_records=new_obs,
                    prov_records=new_prov,
                    rej_records=new_rej,
                )
                self._hit_failure_injector("after_fragment_written")

                # Mark batch staged
                self.dedup_repo.mark_batch_staged(
                    batch_id=batch_id,
                    dataset_id=request.dataset_id,
                    dataset_version=request.dataset_version,
                    obs_sha256=obs_sha,
                    prov_sha256=prov_sha,
                    rej_sha256=rej_sha,
                )
                self._hit_failure_injector("after_batch_staged")

                # Commit to dedup ledger
                processed_obs_ids = [r["observation_id"] for r in processed_source_records]
                self.dedup_repo.record_processed_batch(
                    source_identity=source_identity,
                    source_record_ids=processed_obs_ids,
                    dataset_id=request.dataset_id,
                    dataset_version=request.dataset_version,
                )

                # Advance checkpoint
                self.checkpoint_repo.save_checkpoint(
                    run_id=request.run_id,
                    source_identity=source_identity,
                    source_offset=end_offset,
                    last_sequence=None,
                    last_committed_batch_id=batch_id,
                    processed_count=stats["parsed_records"],
                    rejected_count=stats["rejected_records"],
                    duplicate_count=0,
                )
                self._hit_failure_injector("after_checkpoint_written")

                # Mark batch committed
                self.dedup_repo.mark_batch_committed(
                    batch_id=batch_id,
                    dataset_id=request.dataset_id,
                    dataset_version=request.dataset_version,
                )
                self._hit_failure_injector("after_dedup_committed")

            # 6. Final Assembly & Directory Atomic Publishing
            current_stage = "final_assembly"
            self.dedup_repo.heartbeat_lock(
                dataset_id=request.dataset_id,
                dataset_version=request.dataset_version,
                run_id=request.run_id,
                lease_seconds=self.lock_lease_seconds,
            )

            current_stage = "publishing"
            published_dir, manifest_payload = self.extraction_repo.stage_and_publish_dataset(
                run_id=request.run_id,
                dataset_id=request.dataset_id,
                dataset_version=request.dataset_version,
                observations=observations,
                provenance_records=provenance_records,
                rejected_records=rejected_records,
                schema_version="canonical-observation-v1",
            )
            self._hit_failure_injector("after_dataset_published")

            # 7. Construct Response Payload
            obs_entry = next((f for f in manifest_payload.get("files", []) if f.get("role") == "observations"), {})
            aux_files = manifest_payload.get("auxiliary_files", [])
            prov_entry = next((f for f in aux_files if f.get("role") == "provenance"), {})
            rej_entry = next((f for f in aux_files if f.get("role") == "rejected"), {})

            manifest_file = published_dir / "dataset_manifest.json"
            manifest_sha = compute_file_sha256(manifest_file)

            time_range = None
            if stats.get("min_time") and stats.get("max_time"):
                time_range = ExtractionTimeRange(
                    min_time=stats["min_time"],
                    max_time=stats["max_time"],
                )

            result_payload = ExtractionResultPayload(
                dataset_id=request.dataset_id,
                dataset_version=request.dataset_version,
                manifest_uri=f"data/observations/{request.dataset_id}/{request.dataset_version}/dataset_manifest.json",
                manifest_sha256=manifest_sha,
                observations_uri=f"data/observations/{request.dataset_id}/{request.dataset_version}/observations.jsonl",
                observations_sha256=obs_entry.get("sha256", ""),
                provenance_uri=f"data/observations/{request.dataset_id}/{request.dataset_version}/provenance.jsonl",
                provenance_sha256=prov_entry.get("sha256", ""),
                rejected_uri=f"data/observations/{request.dataset_id}/{request.dataset_version}/rejected.jsonl",
                rejected_sha256=rej_entry.get("sha256", ""),
                total_records_processed=stats["parsed_records"],
                observations_count=stats["observations_count"],
                rejected_count=stats["rejected_records"],
                asset_ids=stats["asset_ids"],
                time_range=time_range,
            )

            response = ExtractionResponse(
                request_id=request.request_id,
                idempotency_key=request.idempotency_key,
                run_id=request.run_id,
                status="succeeded",
                dataset_id=request.dataset_id,
                dataset_version=request.dataset_version,
                result=result_payload,
            )

            self._hit_failure_injector("before_idempotency_succeeded")

            # 8. Mark Idempotency Succeeded and Save Run State
            self.dedup_repo.mark_idempotency_succeeded(
                idempotency_key=request.idempotency_key,
                request_sha256=op_sha256,
                response_dict=response.model_dump(),
            )

            self.checkpoint_repo.save_run_state(
                run_id=request.run_id,
                status="succeeded",
                stage="completed",
                metadata={"response": response.model_dump()},
            )

            return response

        except ExtractionError as exc:
            self.checkpoint_repo.save_run_state(
                run_id=request.run_id,
                status="failed",
                stage=current_stage,
                metadata={"error_code": exc.code, "message": exc.message, "retryable": exc.retryable},
            )
            self.dedup_repo.mark_idempotency_failed(request.idempotency_key, error_code=exc.code)
            raise
        except Exception as exc:
            self.checkpoint_repo.save_run_state(
                run_id=request.run_id,
                status="failed",
                stage=current_stage,
                metadata={"error_code": "EXTRACTION_UNEXPECTED_ERROR", "message": str(exc), "retryable": False},
            )
            self.dedup_repo.mark_idempotency_failed(request.idempotency_key, error_code="EXTRACTION_UNEXPECTED_ERROR")
            raise
        finally:
            self.dedup_repo.release_lock(
                dataset_id=request.dataset_id,
                dataset_version=request.dataset_version,
                run_id=request.run_id,
            )

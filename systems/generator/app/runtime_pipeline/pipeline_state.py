from __future__ import annotations

import json
import logging
from typing import Any, Literal, Optional

from systems.generator.app.runtime_pipeline.pipeline_exception import (
    PipelineStateTransitionInvalidError,
)
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    ArtifactReference,
    InternalModelPredictionResult,
    PipelineCheckpoint,
    PipelineError,
    PipelineRunState,
    RuntimeInputIdentity,
    StageState,
    now_utc_iso,
)

logger = logging.getLogger(__name__)


class PipelineStateManager:
    """Manages state transitions and output file references for an individual run."""

    def __init__(self, run_state: PipelineRunState) -> None:
        self.state = run_state

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        job_id: str,
        source_ref: ArtifactReference,
        source_context: Optional[Any] = None,
    ) -> PipelineStateManager:
        """Create a fresh PipelineRunState instance."""
        state = PipelineRunState(
            run_id=run_id,
            job_id=job_id,
            status="pending",
            current_stage=None,
            source_ref=source_ref,
            source_context=source_context,
            stages={},
            prediction_results=[],
            prediction_delivery_status=None,
            prediction_event_ids=[],
            prediction_events=[],
            started_at=None,
            finished_at=None,
            errors=[],
            last_completed_stage=None,
            next_stage="preprocessing",
            resume_count=0,
            resumed_from_stage=None,
            checkpoint_status="resumable",
            cleanup_status="not_started",
            intermediate_outputs=[],
            checkpoint=None,
        )
        return cls(state)

    def start_run(self) -> None:
        if self.state.status != "pending":
            raise PipelineStateTransitionInvalidError(
                f"Cannot start pipeline run from status '{self.state.status}'",
                details=[{"run_id": self.state.run_id, "status": self.state.status}],
            )
        self.state.status = "running"
        self.state.started_at = now_utc_iso()

    def start_stage(
        self,
        stage_name: str,
        input_refs: Optional[list[ArtifactReference]] = None,
    ) -> StageState:
        """Transition a stage to running."""
        now = now_utc_iso()
        stage = self.state.stages.get(stage_name)
        if stage is None:
            stage = StageState(
                stage_name=stage_name,
                status="running",
                attempt=1,
                started_at=now,
                input_refs=input_refs or [],
                output_refs=[],
            )
            self.state.stages[stage_name] = stage
        else:
            if stage.status == "running":
                raise PipelineStateTransitionInvalidError(
                    f"Stage '{stage_name}' is already running",
                    details=[{"run_id": self.state.run_id, "stage": stage_name}],
                )
            stage.status = "running"
            stage.attempt += 1
            stage.started_at = now
            if input_refs:
                stage.input_refs = input_refs

        self.state.current_stage = stage_name
        return stage

    def succeed_stage(
        self,
        stage_name: str,
        output_refs: list[ArtifactReference],
    ) -> StageState:
        """Mark a stage succeeded ONLY after output files are validated and published."""
        stage = self.state.stages.get(stage_name)
        if stage is None or stage.status != "running":
            raise PipelineStateTransitionInvalidError(
                f"Cannot succeed stage '{stage_name}' because it is not running",
                details=[{"run_id": self.state.run_id, "stage": stage_name}],
            )
        stage.status = "succeeded"
        stage.finished_at = now_utc_iso()
        stage.output_refs = output_refs
        return stage

    def fail_stage(
        self,
        stage_name: str,
        error_code: str,
        error_message: str,
        *,
        retryable: bool = False,
        details: Optional[list[dict[str, Any]]] = None,
    ) -> StageState:
        """Mark a stage failed and append to run error list."""
        now = now_utc_iso()
        stage = self.state.stages.get(stage_name)
        if stage is None:
            stage = StageState(
                stage_name=stage_name,
                status="failed",
                attempt=1,
                started_at=now,
            )
            self.state.stages[stage_name] = stage

        stage.status = "failed"
        stage.finished_at = now
        stage.error_code = error_code
        stage.error_message = error_message
        stage.retryable = retryable

        err = PipelineError(
            code=error_code,
            message=error_message,
            stage=stage_name,
            details=details or [],
            retryable=retryable,
            attempt=stage.attempt,
            occurred_at=now,
        )
        self.state.errors.append(err)
        return stage

    def record_checkpoint(
        self,
        *,
        stage_name: str,
        source_identity: str,
        runtime_input: RuntimeInputIdentity,
        model_set_id: str,
        model_set_version: str,
        model_set_payload_sha256: str,
        next_stage: Optional[str] = None,
        stage_outputs: Optional[list[ArtifactReference]] = None,
        model_stage_outputs: Optional[dict[str, dict[str, Any]]] = None,
        delivery_outputs: Optional[dict[str, dict[str, Any]]] = None,
        batch_manifest_ref: Optional[ArtifactReference] = None,
        model_snapshot: Optional[dict[str, Any]] = None,
        snapshot_validation_status: Optional[Literal["valid", "incompatible", "partially_invalid", "unvalidated"]] = "valid",
        status: Literal["resumable", "debug_only", "cleanup_pending", "completed", "invalidated"] = "resumable",
    ) -> PipelineCheckpoint:
        """Atomically construct and bind a verified stage checkpoint with canonical RuntimeInputIdentity & Model Set snapshots."""
        if not source_identity or not str(source_identity).strip():
            raise ValueError("source_identity must not be empty when recording a checkpoint")

        if not isinstance(runtime_input, RuntimeInputIdentity):
            raise TypeError(f"runtime_input must be an instance of RuntimeInputIdentity, got {type(runtime_input)}")

        if not model_set_id or not str(model_set_id).strip():
            raise ValueError("model_set_id must not be empty when recording a checkpoint")

        if not model_set_version or not str(model_set_version).strip():
            raise ValueError("model_set_version must not be empty when recording a checkpoint")

        if not model_set_payload_sha256 or not str(model_set_payload_sha256).strip():
            raise ValueError("model_set_payload_sha256 must not be empty when recording a checkpoint")

        now = now_utc_iso()
        existing_outputs = dict(self.state.checkpoint.stage_outputs) if self.state.checkpoint else {}
        if stage_outputs is not None:
            existing_outputs[stage_name] = stage_outputs

        existing_model_stage_outputs = dict(self.state.checkpoint.model_stage_outputs) if self.state.checkpoint else {}
        if model_stage_outputs is not None:
            for k, v in model_stage_outputs.items():
                existing_model_stage_outputs.setdefault(k, {}).update(v)

        existing_delivery_outputs = dict(self.state.checkpoint.delivery_outputs) if self.state.checkpoint else {}
        if delivery_outputs is not None:
            existing_delivery_outputs.update(delivery_outputs)

        existing_snapshot = dict(self.state.checkpoint.model_snapshot) if self.state.checkpoint else {}
        if model_snapshot is not None:
            existing_snapshot.update(model_snapshot)

        b_manifest = batch_manifest_ref or (self.state.checkpoint.batch_manifest_ref if self.state.checkpoint else None)
        lineage_json_str = json.dumps(runtime_input.source.lineage.model_dump(mode="json"), ensure_ascii=False)

        chk = PipelineCheckpoint(
            checkpoint_version="generator-runtime-checkpoint-v1",
            run_id=self.state.run_id,
            job_id=self.state.job_id,
            source_identity=source_identity,
            source_uri=runtime_input.source.source_uri,
            source_checksum=runtime_input.source.source_checksum,
            source_size_bytes=self.state.source_ref.size_bytes,
            dataset_id=runtime_input.dataset_id,
            dataset_version=runtime_input.dataset_version,
            model_set_id=model_set_id,
            model_set_version=model_set_version,
            model_set_payload_sha256=model_set_payload_sha256,
            pipeline_contract_version=runtime_input.source.pipeline_contract_version,
            source_kind=runtime_input.source.source_kind,
            source_contract_version=runtime_input.source.source_contract_version,
            source_schema_version=runtime_input.source.source_schema_version,
            lineage_json=lineage_json_str,
            source_context=runtime_input.source,
            last_completed_stage=stage_name,  # type: ignore
            next_stage=next_stage,  # type: ignore
            status=status,
            created_at=self.state.checkpoint.created_at if self.state.checkpoint else now,
            updated_at=now,
            stage_outputs=existing_outputs,
            model_stage_outputs=existing_model_stage_outputs,
            delivery_outputs=existing_delivery_outputs,
            batch_manifest_ref=b_manifest,
            model_snapshot=existing_snapshot,
            snapshot_validation_status=snapshot_validation_status,
            errors=list(self.state.errors),
        )
        self.state.checkpoint = chk
        self.state.last_completed_stage = stage_name
        self.state.next_stage = next_stage
        self.state.checkpoint_status = status
        self.state.model_stage_outputs = existing_model_stage_outputs
        self.state.delivery_outputs = existing_delivery_outputs
        self.state.batch_manifest_ref = b_manifest
        return chk


    def mark_resumed(self, from_stage: str) -> None:
        """Record resumption state."""
        self.state.resume_count += 1
        self.state.resumed_from_stage = from_stage
        self.state.status = "running"
        logger.info(f"[PipelineStateManager] Run '{self.state.run_id}' resumed from stage '{from_stage}' (resume_count={self.state.resume_count})")

    def register_intermediate_outputs(self, refs: list[ArtifactReference]) -> None:
        """Register run-dedicated intermediate artifacts for lifecycle tracking & cleanup."""
        existing_uris = {r.uri for r in self.state.intermediate_outputs}
        for ref in refs:
            if ref.uri not in existing_uris:
                self.state.intermediate_outputs.append(ref)
                existing_uris.add(ref.uri)

    def mark_cleanup_pending(self) -> None:
        self.state.cleanup_status = "cleanup_pending"

    def mark_cleaned(self) -> None:
        self.state.cleanup_status = "cleaned"

    def mark_cleanup_failed(self, error_code: str, error_message: str) -> None:
        self.state.cleanup_status = "cleanup_failed"
        err = PipelineError(
            code=error_code,
            message=error_message,
            stage="intermediate_cleanup",
            details=[],
            retryable=False,
            attempt=1,
            occurred_at=now_utc_iso(),
        )
        self.state.errors.append(err)

    def record_predictions(
        self,
        results: list[InternalModelPredictionResult],
    ) -> None:
        self.state.prediction_results = results

    def record_prediction_delivery(self, status: Literal["not_required", "pending", "sent", "failed"]) -> None:
        self.state.prediction_delivery_status = status

    def finish_run(
        self,
        final_status: Literal["succeeded", "succeeded_with_cleanup_warning", "partially_succeeded", "failed"],
    ) -> None:
        self.state.status = final_status
        self.state.current_stage = None
        self.state.finished_at = now_utc_iso()

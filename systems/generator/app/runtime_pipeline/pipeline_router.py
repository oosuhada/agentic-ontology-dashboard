"""FastAPI router for runtime pipeline inspection and internal enqueueing."""

from __future__ import annotations

from typing import Any, Literal, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from systems.generator.app.runtime_pipeline.pipeline_manager import PipelineManager
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    SHA256_PATTERN,
    PipelineQueueItem,
    PipelineRunState,
    PredictionResultLineage,
    RuntimeInputIdentity,
    RuntimeSourceContext,
)

from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineBaseError

router = APIRouter(tags=["Runtime Pipeline"])


class EnqueueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(..., min_length=1, description="Unique job identifier")
    source_uri: str = Field(..., min_length=1, description="Path or URI of completed observation file")
    source_checksum: str = Field(..., pattern=SHA256_PATTERN, description="SHA-256 checksum of source file")
    source_kind: Literal["live_sensor", "simulation_overlay", "maintenance_replay_overlay"] = Field(
        ..., description="Source kind"
    )
    source_contract_version: str = Field(..., min_length=1, description="Source contract version")
    source_schema_version: str = Field(..., min_length=1, description="Source schema version")
    pipeline_contract_version: str = Field(..., min_length=1, description="Pipeline contract version")
    dataset_id: str = Field(..., min_length=1, description="Dataset identifier")
    dataset_version: str = Field(..., min_length=1, description="Dataset version")
    size_bytes: Optional[int] = Field(None, ge=0, description="Optional source file size in bytes")
    lineage: PredictionResultLineage = Field(default_factory=PredictionResultLineage, description="Overlay lineage metadata")

    @field_validator("source_checksum")
    @classmethod
    def validate_non_zero_checksum(cls, v: str) -> str:
        if v == "0" * 64:
            raise ValueError("source_checksum cannot be all zeros.")
        return v

    @model_validator(mode="after")
    def validate_overlay_lineage(self) -> EnqueueRequest:
        if self.source_kind == "maintenance_replay_overlay":
            lin = self.lineage
            if (
                not lin
                or not (lin.simulation_session_id and str(lin.simulation_session_id).strip())
                or not (lin.overlay_branch_id and str(lin.overlay_branch_id).strip())
                or not (lin.history_segment_id and str(lin.history_segment_id).strip())
                or not (lin.maintenance_event_id and str(lin.maintenance_event_id).strip())
                or not (lin.maintenance_action_id and str(lin.maintenance_action_id).strip())
                or lin.state_version is None
                or lin.state_version < 1
            ):
                raise ValueError(
                    "When source_kind is 'maintenance_replay_overlay', all 6 lineage fields "
                    "(simulation_session_id, overlay_branch_id, history_segment_id, maintenance_event_id, "
                    "maintenance_action_id, state_version >= 1) are required."
                )
        return self

    def to_input_identity(self) -> RuntimeInputIdentity:
        """Convert validated EnqueueRequest to canonical RuntimeInputIdentity."""
        return RuntimeInputIdentity(
            dataset_id=self.dataset_id,
            dataset_version=self.dataset_version,
            source=RuntimeSourceContext(
                source_uri=self.source_uri,
                source_checksum=self.source_checksum,
                source_kind=self.source_kind,
                source_contract_version=self.source_contract_version,
                source_schema_version=self.source_schema_version,
                pipeline_contract_version=self.pipeline_contract_version,
                lineage=self.lineage,
            ),
        )


def get_manager() -> PipelineManager:
    return PipelineManager.get_instance()


@router.get("/runtime-pipeline/status")
def get_pipeline_status() -> dict[str, Any]:
    """Inspect current queue length, active running job, and recent runs."""
    return get_manager().get_status()


@router.get("/runtime-pipeline/runs/{run_id}", response_model=PipelineRunState)
def get_pipeline_run_state(run_id: str) -> PipelineRunState:
    """Fetch complete stage execution state and prediction array by run ID."""
    state = get_manager().get_run_state(run_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "PIPELINE_RUN_NOT_FOUND", "message": f"Run '{run_id}' not found"},
        )
    return state


@router.get("/runtime-pipeline/queue", response_model=list[PipelineQueueItem])
def get_pipeline_queue(status: Optional[str] = Query(None, description="Filter by queue status")) -> list[PipelineQueueItem]:
    """List queued, running, succeeded, or failed queue items."""
    return get_manager().list_queue_items(status=status)


@router.post("/internal/runtime-pipeline/enqueue", response_model=PipelineQueueItem)
def enqueue_observation_source(req: EnqueueRequest) -> PipelineQueueItem:
    """Internal evaluation endpoint to enqueue completed observation file into FIFO queue."""
    try:
        input_identity = req.to_input_identity()
        return get_manager().enqueue(
            job_id=req.job_id,
            input_identity=input_identity,
            size_bytes=req.size_bytes,
        )
    except PipelineBaseError:
        raise
    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        code = getattr(exc, "code", "PIPELINE_ENQUEUE_FAILED")
        raise HTTPException(
            status_code=status_code,
            detail={"code": code, "message": str(exc)},
        ) from exc


@router.post("/internal/runtime-pipeline/retry-failed/{job_id}", response_model=PipelineQueueItem)
def retry_failed_job_endpoint(job_id: str) -> PipelineQueueItem:
    """Explicitly re-enqueue a failed or dead_letter job into the FIFO queue."""
    try:
        return get_manager().retry_failed_job(job_id)
    except PipelineBaseError:
        raise
    except Exception as exc:
        status_code = getattr(exc, "status_code", 500)
        code = getattr(exc, "code", "PIPELINE_RETRY_FAILED")
        raise HTTPException(
            status_code=status_code,
            detail={"code": code, "message": str(exc)},
        ) from exc

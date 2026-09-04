"""Repository for atomically persisting and retrieving PipelineRunState and PredictionResultBatchPayload."""

from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

from systems.generator.generator_config import PATHS
from systems.generator.app.runtime_pipeline.pipeline_exception import (
    PipelineCleanupTargetNotAllowedError,
    PipelineIntermediateCleanupFailedError,
    PipelineRecoveryError,
)
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    ArtifactReference,
    PipelineCheckpoint,
    PipelineRunState,
    PredictionDeliveryEventState,
    PredictionResultBatchPayload,
    now_utc_iso,
)

logger = logging.getLogger(__name__)


class PipelineRepository:
    """File-based persistent repository for pipeline run states, checkpoints, and event payloads."""

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = (
            Path(base_dir)
            if base_dir is not None
            else PATHS.data_preprocessed
        )

        self.runs_dir = self.base_dir / "pipeline_runs"
        self.checkpoints_dir = self.base_dir / "pipeline_checkpoints"
        self.events_dir = self.base_dir / "pipeline_events"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write_json(self, target_path: Path, data: dict[str, Any]) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.parent / f".tmp_{uuid.uuid4().hex}_{target_path.name}"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            temp_path.replace(target_path)
        except Exception as exc:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise exc

    def save_run_state(self, state: PipelineRunState) -> None:
        """Atomically persist PipelineRunState to disk."""
        target_file = self.runs_dir / f"{state.run_id}.json"
        try:
            self._atomic_write_json(target_file, state.model_dump())
        except Exception as exc:
            logger.exception(f"[PipelineRepository] Failed to save run state '{state.run_id}': {exc}")
            raise PipelineRecoveryError(f"실행 상태 저장 실패: {exc}") from exc

    def get_run_state(self, run_id: str) -> Optional[PipelineRunState]:
        """Fetch PipelineRunState by run ID."""
        clean_id = Path(run_id).name
        target_file = self.runs_dir / f"{clean_id}.json"
        if not target_file.is_file():
            return None
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PipelineRunState.model_validate(data)
        except Exception as exc:
            logger.warning(f"[PipelineRepository] Failed to load run state '{run_id}': {exc}")
            return None

    def save_event(self, event: PredictionResultBatchPayload) -> None:
        """Atomically persist PredictionResultBatchPayload to disk."""
        from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
            PredictionDeliveryService,
        )
        event_id, _ = PredictionDeliveryService.compute_canonical_payload_sha256(event)
        target_file = self.events_dir / f"{event_id}.json"
        try:
            self._atomic_write_json(target_file, event.model_dump(mode="json"))
        except Exception as exc:
            logger.warning(f"[PipelineRepository] Failed to save prediction event '{event_id}': {exc}")

    def get_event(self, event_id: str) -> Optional[PredictionResultBatchPayload]:
        """Fetch PredictionResultBatchPayload by event ID."""
        clean_id = Path(event_id).name
        target_file = self.events_dir / f"{clean_id}.json"
        if not target_file.is_file():
            return None
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PredictionResultBatchPayload.model_validate(data)
        except Exception as exc:
            logger.warning(f"[PipelineRepository] Failed to load prediction event '{event_id}': {exc}")
            return None

    def list_run_states(self, limit: int = 50) -> list[PipelineRunState]:
        """List recently saved run states."""
        runs = []
        files = sorted(self.runs_dir.glob("*.json"), key=os.path.getmtime, reverse=True)
        for f in files[:limit]:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                runs.append(PipelineRunState.model_validate(data))
            except Exception:
                continue
        return runs

    def update_prediction_event(
        self,
        *,
        run_id: str,
        event_id: str,
        asset_id: str,
        status: Literal["pending", "sending", "retry_wait", "sent", "failed"],
        attempt: int,
        max_attempts: int = 5,
        next_retry_at: Optional[str] = None,
        last_error_code: Optional[str] = None,
        last_error_message: Optional[str] = None,
    ) -> Optional[PipelineRunState]:
        """Atomically update a specific prediction delivery event state and aggregate overall status."""
        state = self.get_run_state(run_id)
        if not state:
            return None

        found = False
        updated_events = []
        for ev in state.prediction_events:
            if ev.event_id == event_id:
                found = True
                updated_events.append(
                    PredictionDeliveryEventState(
                        event_id=event_id,
                        asset_id=asset_id or ev.asset_id,
                        status=status,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        next_retry_at=next_retry_at,
                        last_error_code=last_error_code,
                        last_error_message=last_error_message,
                        updated_at=now_utc_iso(),
                    )
                )
            else:
                updated_events.append(ev)

        if not found:
            updated_events.append(
                PredictionDeliveryEventState(
                    event_id=event_id,
                    asset_id=asset_id,
                    status=status,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    next_retry_at=next_retry_at,
                    last_error_code=last_error_code,
                    last_error_message=last_error_message,
                    updated_at=now_utc_iso(),
                )
            )

        state.prediction_events = updated_events

        # Re-aggregate overall prediction_delivery_status
        if not state.prediction_events:
            state.prediction_delivery_status = "not_required"
        else:
            statuses = {ev.status for ev in state.prediction_events}
            if len(state.prediction_events) < len(state.prediction_event_ids):
                state.prediction_delivery_status = "pending"
            elif any(s == "failed" for s in statuses):
                state.prediction_delivery_status = "failed"
            elif all(s == "sent" for s in statuses):
                state.prediction_delivery_status = "sent"
            else:
                state.prediction_delivery_status = "pending"

        self.save_run_state(state)
        return state

    def save_checkpoint(self, checkpoint: PipelineCheckpoint) -> None:
        """Atomically persist PipelineCheckpoint to disk."""
        target_file = self.checkpoints_dir / f"{checkpoint.run_id}.json"
        try:
            self._atomic_write_json(target_file, checkpoint.model_dump())
        except Exception as exc:
            logger.exception(f"[PipelineRepository] Failed to save checkpoint '{checkpoint.run_id}': {exc}")
            raise PipelineRecoveryError(f"체크포인트 저장 실패: {exc}") from exc

    def get_checkpoint(self, run_id: str) -> Optional[PipelineCheckpoint]:
        """Fetch PipelineCheckpoint by run ID."""
        clean_id = Path(run_id).name
        target_file = self.checkpoints_dir / f"{clean_id}.json"
        if not target_file.is_file():
            return None
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PipelineCheckpoint.model_validate(data)
        except Exception as exc:
            logger.warning(f"[PipelineRepository] Failed to load checkpoint '{run_id}': {exc}")
            return None

    def find_resumable_run(self, source_identity: str) -> Optional[PipelineRunState]:
        """Find the most recent resumable run state matching source_identity.

        Legacy run states lacking source_identity or valid context cannot be safely resumed and are skipped.
        """
        if not source_identity or not str(source_identity).strip():
            return None

        runs = self.list_run_states(limit=100)
        for r in runs:
            try:
                chk = self.get_checkpoint(r.run_id) or r.checkpoint
                chk_identity = chk.source_identity if chk else None

                # Only match when an explicit source_identity is present and equal
                if chk_identity and chk_identity == source_identity:
                    if r.status in ("running", "failed", "partially_succeeded") and (not chk or chk.status == "resumable"):
                        return r
            except Exception as exc:
                logger.warning(f"[PipelineRepository] Skipping invalid run '{getattr(r, 'run_id', 'unknown')}' during resumption search: {exc}")
                continue
        return None

    def cleanup_run_intermediate_outputs(
        self,
        run_id: str,
        intermediate_refs: list[ArtifactReference],
    ) -> tuple[bool, list[str], Optional[str]]:
        """Safely cleanup run-dedicated intermediate artifacts.

        Strict safety invariant:
        - The target path MUST be within allowed staging/cache/preprocessed directories.
        - The target path MUST contain `run_id` as part of its path components.
        - Absolute root / shared directories / source files / model artifacts CANNOT be deleted.
        """
        clean_run_id = Path(run_id).name
        if not clean_run_id:
            return False, [], "Invalid empty run_id for cleanup"

        deleted_paths: list[str] = []
        errors: list[str] = []

        allowed_parent_dirs = [
            self.base_dir.resolve(),
            (self.base_dir / "pipeline_datasets").resolve(),
            (self.base_dir / "predictions").resolve(),
            (getattr(PATHS, "models_store", Path("models_store")) / "cache").resolve(),
            getattr(
                PATHS,
                "runtime_feature_root",
                Path("models_store") / "cache" / "runtime_features",
            ).resolve(),
        ]

        forbidden_names = {
            "models_store", "data", "ontology", "contracts", "systems", "tests",
            "manifest.json", "model.joblib", "feature_schema.json", "label_schema.json",
            "history_requirement.json", "metrics.json", "registry.json"
        }

        for ref in intermediate_refs:
            uri_str = ref.uri
            p = Path(uri_str)
            if not p.is_absolute():
                # Resolve relative to base_dir or project root
                p = (self.base_dir / p).resolve()
            else:
                p = p.resolve()

            # Safety Rule 1: Check forbidden names
            if p.name in forbidden_names:
                errors.append(f"Refusing to delete protected artifact '{p.name}' ({ref.uri})")
                continue

            # Safety Rule 2: Path must contain run_id
            if clean_run_id not in p.parts:
                errors.append(f"Target path does not contain run_id '{clean_run_id}': {ref.uri}")
                continue

            # Safety Rule 3: Must be inside one of allowed parents
            is_under_allowed = False
            for parent in allowed_parent_dirs:
                try:
                    p.relative_to(parent)
                    is_under_allowed = True
                    break
                except ValueError:
                    continue

            if not is_under_allowed:
                errors.append(f"Target path is outside allowed sandbox: {ref.uri}")
                continue

            # Safe to delete
            try:
                if p.is_file() or p.is_symlink():
                    p.unlink()
                    deleted_paths.append(str(p))
                    logger.info(f"[PipelineRepository] Cleaned intermediate file '{p}'")
                elif p.is_dir():
                    shutil.rmtree(p)
                    deleted_paths.append(str(p))
                    logger.info(f"[PipelineRepository] Cleaned intermediate directory '{p}'")
            except Exception as e:
                errors.append(f"Failed to delete '{p}': {e}")

        # Also clean empty run-dedicated directory if exists
        run_dataset_dir = (self.base_dir / "pipeline_datasets" / clean_run_id).resolve()
        if run_dataset_dir.is_dir():
            try:
                shutil.rmtree(run_dataset_dir)
                deleted_paths.append(str(run_dataset_dir))
            except Exception:
                pass

        if errors:
            return False, deleted_paths, "; ".join(errors)
        return True, deleted_paths, None

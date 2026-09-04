"""Service for managing Prediction Result Outbox and single-dispatch HTTP client."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Optional

from systems.generator.generator_config import PATHS
from systems.generator.app.runtime_pipeline.pipeline_exception import (
    PipelineDeliveryFailedError,
    PipelineDeliveryServerError,
    PipelineDeliveryTimeoutError,
    PipelineDeliveryUnauthorizedError,
    PipelineDeliveryUnprocessableError,
    PipelineOutboxEventConflictError,
)
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    PredictionOutboxItem,
    PredictionResultBatchPayload,
    now_utc_iso,
)

logger = logging.getLogger(__name__)
_OUTBOX_FILE_LOCK = threading.RLock()


def _replace_with_retry(temp_path: Path, target_path: Path) -> None:
    """Replace a file atomically, tolerating transient Windows sharing violations."""
    delays = (0.01, 0.05, 0.1)
    for attempt in range(len(delays) + 1):
        try:
            os.replace(temp_path, target_path)
            return
        except PermissionError:
            if attempt == len(delays):
                raise
            time.sleep(delays[attempt])


class PredictionDeliveryService:
    """HTTP client for dispatching prediction result batches with Outbox persistence and single-dispatch execution."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        outbox_dir: Optional[Path] = None,
        timeout: float = 10.0,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> None:
        url_from_env = os.environ.get("GENERATOR_PREDICTION_RESULT_URL")
        legacy_url = os.environ.get("GENERATOR_PREDICTION_RECEIVER_URL")
        if url_from_env and legacy_url and url_from_env != legacy_url:
            raise ValueError(
                "Both GENERATOR_PREDICTION_RESULT_URL and deprecated GENERATOR_PREDICTION_RECEIVER_URL are set with conflicting values. Please configure GENERATOR_PREDICTION_RESULT_URL only."
            )
        if legacy_url and not url_from_env:
            logger.warning(
                "[PredictionDeliveryService] GENERATOR_PREDICTION_RECEIVER_URL is deprecated. Use GENERATOR_PREDICTION_RESULT_URL instead."
            )
        base_endpoint_url = (
            endpoint_url
            or url_from_env
            or legacy_url
            or "http://localhost:8000/internal/prediction-results"
        )
        self.project_id = (
            project_id
            or os.environ.get("GENERATOR_PREDICTION_RESULT_PROJECT_ID")
            or "manufacturing-demo-project"
        )
        self.workspace_id = (
            workspace_id
            or os.environ.get("GENERATOR_PREDICTION_RESULT_WORKSPACE_ID")
            or "manufacturing-demo"
        )
        self.endpoint_url = self._endpoint_with_scope(
            base_endpoint_url,
            project_id=self.project_id,
            workspace_id=self.workspace_id,
        )
        self.outbox_dir = Path(outbox_dir) if outbox_dir else PATHS.notification_outbox_root
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self._maintenance_signal_lock = threading.Lock()
        self._pending_maintenance_event_ids: set[str] = set()

    @staticmethod
    def _endpoint_with_scope(endpoint_url: str, *, project_id: str, workspace_id: str) -> str:
        parsed = urllib.parse.urlsplit(endpoint_url)
        query = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        query.setdefault("project_id", project_id)
        query.setdefault("workspace_id", workspace_id)
        return urllib.parse.urlunsplit(
            parsed._replace(query=urllib.parse.urlencode(query))
        )

    def save_outbox_item(self, item: PredictionOutboxItem) -> Path:
        """Atomic save of outbox item to outbox_dir/{event_id}.json."""
        with _OUTBOX_FILE_LOCK:
            dest_path = self.outbox_dir / f"{item.event_id}.json"
            temp_path = self.outbox_dir / f".tmp_{uuid.uuid4().hex}_{item.event_id}.json"
            item.updated_at = now_utc_iso()
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(item.model_dump_json(indent=2))
                    f.flush()
                    os.fsync(f.fileno())
                _replace_with_retry(temp_path, dest_path)
                if item.status in {"pending", "retry_wait", "failed"}:
                    maintenance_event_id = self.maintenance_event_id(item)
                    if maintenance_event_id is not None:
                        with self._maintenance_signal_lock:
                            self._pending_maintenance_event_ids.add(maintenance_event_id)
                return dest_path
            finally:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except OSError:
                        pass

    @staticmethod
    def maintenance_event_id(item: PredictionOutboxItem) -> Optional[str]:
        """Return the replay lineage key used for operational prioritization."""
        source_context = item.payload.source_context
        if source_context.source_kind != "maintenance_replay_overlay":
            return None
        maintenance_event_id = source_context.lineage.maintenance_event_id
        if maintenance_event_id is None:
            return None
        normalized = str(maintenance_event_id).strip()
        return normalized or None

    def consume_pending_maintenance_event_ids(self) -> set[str]:
        """Atomically consume replay events registered since the last scan."""
        with self._maintenance_signal_lock:
            event_ids = set(self._pending_maintenance_event_ids)
            self._pending_maintenance_event_ids.clear()
            return event_ids

    def get_outbox_item(self, event_id: str) -> Optional[PredictionOutboxItem]:
        """Load single outbox item by event_id."""
        path = self.outbox_dir / f"{event_id}.json"
        if not path.is_file():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return PredictionOutboxItem.model_validate(data)
        except Exception as exc:
            logger.error(f"[PredictionDeliveryService] Failed to load outbox item '{event_id}': {exc}")
            return None

    def list_outbox_items(self, status: Optional[str] = None) -> list[PredictionOutboxItem]:
        """List all outbox items, optionally filtered by status."""
        items: list[PredictionOutboxItem] = []
        for file in sorted(self.outbox_dir.glob("*.json")):
            if file.name.startswith(".tmp_"):
                continue
            try:
                with open(file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                item = PredictionOutboxItem.model_validate(data)
                if status is None or item.status == status:
                    items.append(item)
            except Exception as exc:
                quarantine_dir = self.outbox_dir / "quarantine"
                quarantine_dir.mkdir(parents=True, exist_ok=True)
                dest = quarantine_dir / file.name
                try:
                    file.replace(dest)
                    logger.error(
                        f"[PredictionDeliveryService] Corrupt outbox file '{file.name}' quarantined to '{dest}': {exc} "
                        f"(error_code=PIPELINE_DELIVERY_OUTBOX_CORRUPT, retryable=False)"
                    )
                except Exception:
                    logger.error(f"[PredictionDeliveryService] Failed to quarantine corrupt file '{file.name}': {exc}")
        return items

    @staticmethod
    def compute_canonical_payload_sha256(payload: Any) -> tuple[str, str]:
        """Compute SHA-256 checksum of canonical payload representation and generate deterministic batch event_id."""
        import hashlib
        import json
        if isinstance(payload, dict):
            d = dict(payload)
        else:
            d = payload.model_dump(mode="json")

        d_clean = dict(d)
        d_clean.pop("emitted_at", None)
        d_clean.pop("batch_id", None)
        if isinstance(d_clean.get("producer"), dict):
            d_clean["producer"] = dict(d_clean["producer"])
            d_clean["producer"].pop("outbox_id", None)

        if isinstance(d_clean.get("results"), list):
            d_clean["results"] = sorted(
                d_clean["results"],
                key=lambda it: (
                    it.get("asset_id", "") if isinstance(it, dict) else getattr(it, "asset_id", ""),
                    it.get("model_id", "") if isinstance(it, dict) else getattr(it, "model_id", ""),
                    it.get("model_version", "") if isinstance(it, dict) else getattr(it, "model_version", ""),
                    str(it.get("observed_at", "")) if isinstance(it, dict) else str(getattr(it, "observed_at", "")),
                    it.get("event_id", "") if isinstance(it, dict) else getattr(it, "event_id", ""),
                ),
            )

        canonical_json = json.dumps(d_clean, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        payload_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        event_id = f"evt-batch-{payload_sha256[:32]}"
        return event_id, payload_sha256

    def register_idempotent_outbox_record(
        self, payload: PredictionResultBatchPayload, run_id: Optional[str] = None
    ) -> tuple[PredictionOutboxItem, str]:
        """Register outbox record with deterministic event_id. Idempotently returns existing record if present."""
        event_id, payload_sha256 = self.compute_canonical_payload_sha256(payload)

        existing_item = self.get_outbox_item(event_id)
        if existing_item is not None:
            _, existing_sha256 = self.compute_canonical_payload_sha256(existing_item.payload)
            if existing_sha256 == payload_sha256:
                logger.info(f"[PredictionDeliveryService] Idempotent reuse of existing outbox record '{event_id}'")
                return existing_item, payload_sha256
            else:
                raise PipelineOutboxEventConflictError(
                    f"동일한 event_id '{event_id}'에 대해 내용이 상이한 payload가 감지되었습니다.",
                    details=[{"event_id": event_id, "existing_sha256": existing_sha256, "new_sha256": payload_sha256}],
                    retryable=False,
                )

        item = self.create_outbox_record(payload, run_id=run_id)
        return item, payload_sha256

    def create_outbox_record(
        self, payload: PredictionResultBatchPayload, run_id: Optional[str] = None
    ) -> PredictionOutboxItem:
        """Create new pending outbox record for payload."""
        event_id, _ = self.compute_canonical_payload_sha256(payload)
        asset_id = payload.results[0].asset_id if (hasattr(payload, "results") and payload.results) else "unknown"
        actual_run_id = run_id or getattr(payload, "run_id", None) or getattr(payload, "batch_id", event_id)
        item = PredictionOutboxItem(
            event_id=event_id,
            run_id=actual_run_id,
            job_id=actual_run_id,
            asset_id=asset_id,
            status="pending",
            attempt=0,
            max_attempts=5,
            payload=payload,
        )
        self.save_outbox_item(item)
        return item

    def send_once(self, payload: PredictionResultBatchPayload) -> dict[str, Any]:
        """Perform a single HTTP POST dispatch attempt to the backend receiver."""
        body = payload.model_dump_json().encode("utf-8")
        event_id, _ = self.compute_canonical_payload_sha256(payload)
        batch_id = getattr(payload, "batch_id", event_id)
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": event_id,
            "X-Request-ID": batch_id,
        }
        auth_token = os.environ.get("GENERATOR_PREDICTION_RESULT_TOKEN", "").strip()
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        req = urllib.request.Request(
            self.endpoint_url,
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status_code = resp.getcode()
                resp_body = resp.read().decode("utf-8")
                logger.info(
                    f"[PredictionDeliveryService] Successfully sent prediction batch '{event_id}' "
                    f"(HTTP {status_code}) to {self.endpoint_url}"
                )
                return {"delivered": True, "status_code": status_code, "response": resp_body}
        except urllib.error.HTTPError as h_err:
            if h_err.code in (200, 202):
                return {"delivered": True, "status_code": h_err.code, "response": ""}
            elif h_err.code == 409:
                logger.error(f"[PredictionDeliveryService] Conflict error (HTTP 409) for batch '{event_id}'")
                raise PipelineOutboxEventConflictError(
                    f"수신 시스템에서 event ID 충돌이 발생했습니다 (HTTP 409): {event_id}",
                    details=[{"status_code": 409, "event_id": event_id}],
                    retryable=False,
                ) from h_err
            elif h_err.code == 422:
                logger.error(f"[PredictionDeliveryService] Contract unprocessable error (HTTP 422) for batch '{event_id}'")
                raise PipelineDeliveryUnprocessableError(
                    f"수신 시스템이 계약 위반으로 배치를 거부했습니다 (HTTP 422): {event_id}",
                    details=[{"status_code": 422, "event_id": event_id}],
                    retryable=False,
                ) from h_err
            elif h_err.code in (401, 403):
                logger.error(f"[PredictionDeliveryService] Authorization error (HTTP {h_err.code}) for batch '{event_id}'")
                raise PipelineDeliveryUnauthorizedError(
                    f"수신 시스템 인증/권한 오류 (HTTP {h_err.code}): {event_id}",
                    details=[{"status_code": h_err.code, "event_id": event_id}],
                    retryable=False,
                ) from h_err
            elif 400 <= h_err.code < 500:
                logger.error(
                    f"[PredictionDeliveryService] Client error (HTTP {h_err.code}) for batch '{event_id}'"
                )
                raise PipelineDeliveryFailedError(
                    f"수신 시스템 클라이언트 오류 (HTTP {h_err.code}): {event_id}",
                    details=[{"status_code": h_err.code, "event_id": event_id}],
                    retryable=False,
                ) from h_err
            else:
                logger.warning(
                    f"[PredictionDeliveryService] Server error (HTTP {h_err.code}) for batch '{event_id}'"
                )
                raise PipelineDeliveryServerError(
                    f"수신 시스템 서버 오류 (HTTP {h_err.code}): {event_id}",
                    details=[{"status_code": h_err.code, "event_id": event_id}],
                    retryable=True,
                ) from h_err
        except Exception as exc:
            logger.warning(f"[PredictionDeliveryService] Network or unexpected error sending batch '{event_id}': {exc}")
            raise PipelineDeliveryFailedError(
                f"예측 결과 전송 중 오류 발생: {exc}",
                details=[{"event_id": event_id, "error": str(exc)}],
                retryable=True,
            ) from exc

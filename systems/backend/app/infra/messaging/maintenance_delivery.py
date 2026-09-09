"""Operational delivery adapters for maintenance runtime integration events."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib import error, request

from app.infra.db.postgresql_compat import postgres_repository_connection
from app.infra.db.postgresql_repositories import is_postgresql
from app.maintenance.integration import validate_maintenance_event

from .outbox import OutboxMessage


class MaintenanceRuntimeDeliveryConflict(ValueError):
    retryable = False


class MaintenanceRuntimeDeliveryUnavailable(RuntimeError):
    retryable = True


@dataclass(frozen=True)
class MaintenanceRuntimeReceipt:
    external_delivery_id: str | None = None
    overlay_branch_id: str | None = None
    history_segment_id: str | None = None
    response: Mapping[str, Any] | None = None


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


class MaintenanceRuntimeDeliveryReceiptRepository:
    """Persist downstream acknowledgement without weakening outbox idempotency."""

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self.postgresql = is_postgresql(self.database)

    def existing(self, message: OutboxMessage) -> dict[str, Any] | None:
        query = """
            SELECT * FROM maintenance_runtime_delivery_receipts
            WHERE outbox_id=? AND organization_id=? AND project_id=?
        """
        params = (message.id, message.organization_id, message.project_id)
        if self.postgresql:
            with postgres_repository_connection(
                self.database,
                organization_id=message.organization_id,
                project_id=message.project_id,
            ) as connection:
                row = connection.execute(query, params).fetchone()
        else:
            with sqlite3.connect(self.database) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(query, params).fetchone()
        return None if row is None else dict(row)

    def record(
        self,
        message: OutboxMessage,
        *,
        transport: str,
        receipt: MaintenanceRuntimeReceipt,
    ) -> None:
        payload_sha256 = _sha256(message.payload)
        existing = self.existing(message)
        if existing is not None:
            if str(existing["payload_sha256"]) != payload_sha256:
                raise MaintenanceRuntimeDeliveryConflict(
                    f"maintenance delivery receipt payload conflict: {message.id}"
                )
            return
        now = datetime.now(timezone.utc).isoformat()
        response = dict(receipt.response or {})
        values = (
            message.id,
            message.organization_id,
            message.project_id,
            message.workspace_id,
            str(message.payload.get("event_id") or message.id),
            message.event_type,
            str(message.payload.get("equipment_id") or ""),
            str(message.payload.get("maintenance_action_id") or ""),
            message.payload.get("maintenance_event_id"),
            int(message.payload.get("state_version") or 0),
            transport,
            payload_sha256,
            receipt.external_delivery_id,
            receipt.overlay_branch_id,
            receipt.history_segment_id,
            json.dumps(response, ensure_ascii=False, sort_keys=True),
            now,
            now,
            now,
        )
        query = """
            INSERT INTO maintenance_runtime_delivery_receipts(
                outbox_id,organization_id,project_id,workspace_id,event_id,event_type,
                equipment_id,maintenance_action_id,maintenance_event_id,state_version,
                transport,payload_sha256,external_delivery_id,overlay_branch_id,
                history_segment_id,response_json,delivered_at,created_at,updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        if self.postgresql:
            with postgres_repository_connection(
                self.database,
                organization_id=message.organization_id,
                project_id=message.project_id,
            ) as connection:
                connection.execute(query, values)
            return
        with sqlite3.connect(self.database) as connection:
            connection.execute(query, values)


class MaintenanceReplayHttpHandler:
    """POST validated maintenance events to the configured gen_data endpoint."""

    handler_code = "maintenance-replay-http-v1"

    def __init__(
        self,
        url: str,
        *,
        receipt_repository: MaintenanceRuntimeDeliveryReceiptRepository,
        bearer_token: str | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not url.strip():
            raise ValueError("maintenance runtime URL is required")
        self.url = url.strip()
        self.receipt_repository = receipt_repository
        self.bearer_token = bearer_token.strip() if bearer_token else None
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    def __call__(self, message: OutboxMessage) -> None:
        validate_maintenance_event(message.payload)
        if str(message.payload.get("event_id") or "") != message.id:
            raise MaintenanceRuntimeDeliveryConflict("outbox id does not match payload event_id")
        existing = self.receipt_repository.existing(message)
        if existing is not None:
            if str(existing["payload_sha256"]) != _sha256(message.payload):
                raise MaintenanceRuntimeDeliveryConflict(
                    f"maintenance delivery receipt payload conflict: {message.id}"
                )
            return

        body = _canonical(message.payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Idempotency-Key": str(message.payload.get("idempotency_key") or message.id),
            "X-Ontology-Event-Id": message.id,
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        req = request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                status = int(getattr(response, "status", 200))
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            if 400 <= exc.code < 500 and exc.code not in {408, 409, 425, 429}:
                conflict = MaintenanceRuntimeDeliveryConflict(
                    f"gen_data rejected maintenance event ({exc.code}): {raw[:500]}"
                )
                conflict.retryable = False
                raise conflict from exc
            raise MaintenanceRuntimeDeliveryUnavailable(
                f"gen_data maintenance delivery failed ({exc.code}): {raw[:500]}"
            ) from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise MaintenanceRuntimeDeliveryUnavailable(
                f"gen_data maintenance delivery unavailable: {exc}"
            ) from exc
        if status < 200 or status >= 300:
            raise MaintenanceRuntimeDeliveryUnavailable(
                f"gen_data maintenance delivery returned HTTP {status}"
            )
        if not raw.strip():
            payload: dict[str, Any] = {}
        else:
            try:
                decoded = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise MaintenanceRuntimeDeliveryConflict(
                    "gen_data maintenance response must be JSON"
                ) from exc
            if not isinstance(decoded, dict):
                raise MaintenanceRuntimeDeliveryConflict(
                    "gen_data maintenance response must be an object"
                )
            payload = decoded
        returned_event_id = payload.get("event_id")
        if returned_event_id is not None and str(returned_event_id) != message.id:
            raise MaintenanceRuntimeDeliveryConflict(
                "gen_data maintenance response event_id does not match request"
            )
        self.receipt_repository.record(
            message,
            transport="http",
            receipt=MaintenanceRuntimeReceipt(
                external_delivery_id=(
                    None
                    if payload.get("delivery_id") is None
                    else str(payload["delivery_id"])
                ),
                overlay_branch_id=(
                    None
                    if payload.get("overlay_branch_id") is None
                    else str(payload["overlay_branch_id"])
                ),
                history_segment_id=(
                    None
                    if payload.get("history_segment_id") is None
                    else str(payload["history_segment_id"])
                ),
                response=payload,
            ),
        )


__all__ = [
    "MaintenanceReplayHttpHandler",
    "MaintenanceRuntimeDeliveryConflict",
    "MaintenanceRuntimeDeliveryReceiptRepository",
    "MaintenanceRuntimeDeliveryUnavailable",
    "MaintenanceRuntimeReceipt",
]

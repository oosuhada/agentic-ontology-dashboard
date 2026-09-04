"""Durable local/demo adapter for the gen_data Runtime Overlay JSONL inbox."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.maintenance.integration import validate_maintenance_event

from .outbox import OutboxMessage


MAINTENANCE_REPLAY_EVENT_TYPES = (
    "maintenance.started",
    "maintenance.completed",
    "maintenance.replay_requested",
)


class MaintenanceReplayDeliveryConflict(ValueError):
    retryable = False


class MaintenanceReplayJsonlHandler:
    """Append validated events while tolerating at-least-once redelivery."""

    handler_code = "maintenance-replay-jsonl-v1"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    @staticmethod
    def _canonical(payload: dict[str, Any]) -> str:
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _index(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        result: dict[str, str] = {}
        for line_number, raw_line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not raw_line.strip():
                continue
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid Runtime Overlay inbox JSON at {self.path}:{line_number}"
                ) from exc
            if not isinstance(payload, dict) or not payload.get("event_id"):
                raise ValueError(
                    f"invalid Runtime Overlay inbox event at {self.path}:{line_number}"
                )
            event_id = str(payload["event_id"])
            canonical = self._canonical(payload)
            existing = result.get(event_id)
            if existing is not None and existing != canonical:
                raise MaintenanceReplayDeliveryConflict(
                    f"Runtime Overlay inbox event_id conflict: {event_id}"
                )
            result[event_id] = canonical
        return result

    def __call__(self, message: OutboxMessage) -> None:
        payload = dict(message.payload)
        if message.event_type not in MAINTENANCE_REPLAY_EVENT_TYPES:
            raise MaintenanceReplayDeliveryConflict(
                f"unsupported maintenance replay event: {message.event_type}"
            )
        if payload.get("event_type") != message.event_type:
            raise MaintenanceReplayDeliveryConflict("outbox event_type does not match payload")
        if str(payload.get("event_id") or "") != message.id:
            raise MaintenanceReplayDeliveryConflict("outbox id does not match payload event_id")
        validate_maintenance_event(payload)

        canonical = self._canonical(payload)
        previous = self._index().get(message.id)
        if previous is not None:
            if previous != canonical:
                raise MaintenanceReplayDeliveryConflict(
                    f"Runtime Overlay inbox event_id conflict: {message.id}"
                )
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(canonical + "\n")
            handle.flush()
            os.fsync(handle.fileno())

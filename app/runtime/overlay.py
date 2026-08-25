"""Target-only Runtime Overlay for Closed-loop maintenance replay.

The overlay is a Source Data Producer capability.  It consumes only the
versioned Maintenance handoff, snapshots one simulation runtime, and emits
append-only post-maintenance observations.  It deliberately does not read a
Model Artifact, calculate history readiness, or produce predictions.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from app.simulation.producer import SimulationProducer
from physics_engine import Runtime


MAINTENANCE_CONTRACT_VERSION = "maintenance-replay-v1"
AVAILABLE_CONTRACT_VERSION = "runtime-overlay-observation-v1-preview"
OVERLAY_SOURCE_KIND = "maintenance_replay_overlay"
CHECKPOINT_VERSION = 4

_EVENT_TYPES = {
    "maintenance.started",
    "maintenance.completed",
    "maintenance.replay_requested",
}
_EVENT_FIELDS = {
    "contract_version",
    "event_type",
    "event_id",
    "idempotency_key",
    "state_version",
    "simulation_session_id",
    "maintenance_event_id",
    "maintenance_action_id",
    "work_order_id",
    "equipment_id",
    "maintenance_started_at",
    "maintenance_completed_at",
    "restart_at",
    "action_code",
    "state_patch",
    "caused_by",
}
_CAUSED_BY_FIELDS = {
    "source_product_result_id",
    "source_evidence_id",
    "decision_id",
}
_TEXT_FIELDS: dict[str, tuple[int, int]] = {
    "event_id": (1, 240),
    "idempotency_key": (8, 200),
    "simulation_session_id": (1, 240),
    "maintenance_event_id": (1, 240),
    "maintenance_action_id": (1, 240),
    "work_order_id": (1, 240),
    "equipment_id": (1, 240),
}
_TIMESTAMP_FIELDS = {
    "maintenance_started_at",
    "maintenance_completed_at",
    "restart_at",
}
_TOOL_REPLACEMENT_PATCH = {
    "tool_wear_min": {
        "operation": "reset",
        "value": 0,
        "unit": "min",
    }
}


class OverlayContractError(ValueError):
    """Raised when a maintenance handoff violates the source contract."""


class OverlayConflict(OverlayContractError):
    """Raised when an identity/version is reused with different semantics."""


class StaleOverlayEvent(OverlayContractError):
    """Raised when an older state version arrives after a newer state."""


def _parse_datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str) and value:
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise OverlayContractError(f"{field} must be an ISO-8601 timestamp") from exc
    else:
        raise OverlayContractError(f"{field} must be an ISO-8601 timestamp")
    if result.tzinfo is None:
        raise OverlayContractError(f"{field} must include timezone information")
    return result


def _payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _semantic_observation_hash(payload: dict[str, Any]) -> str:
    semantic = {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at", "observation_sha256"}
    }
    return _payload_hash(semantic)


def _overlay_observation_id(
    branch: OverlayBranch,
    observed_at: datetime,
    measurements: dict[str, Any],
) -> str:
    """Keep overlay identity distinct without changing canonical SensorRecord IDs."""
    digest = _payload_hash(
        {
            "simulation_session_id": branch.simulation_session_id,
            "overlay_branch_id": branch.overlay_branch_id,
            "equipment_id": branch.equipment_id,
            "observed_at": observed_at.isoformat(timespec="seconds"),
            "measurements": measurements,
        }
    )
    return f"obs-{digest[:32]}"


def _json_safe_random_state(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_safe_random_state(item) for item in value]
    if isinstance(value, list):
        return [_json_safe_random_state(item) for item in value]
    return value


def _tuple_random_state(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tuple_random_state(item) for item in value)
    return value


def _runtime_checkpoint(runtime: Runtime) -> dict[str, Any]:
    def timestamp(value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None

    return {
        "baseline": dict(runtime.baseline),
        "noise_state": dict(runtime.noise_state),
        "tool_wear_min": runtime.tool_wear_min,
        "tool_change_threshold_min": runtime.tool_change_threshold_min,
        "product_started_at": timestamp(runtime.product_started_at),
        "product_type": runtime.product_type,
        "product_ticks": runtime.product_ticks,
        "product_counter": runtime.product_counter,
        "planned_maintenance_until": timestamp(runtime.planned_maintenance_until),
        "tool_reset_at": timestamp(runtime.tool_reset_at),
        "rng_state": _json_safe_random_state(runtime.rng.getstate()),
    }


def _base_source_snapshot_sha256(
    *,
    base_dataset_version: str,
    source_run_id: str,
    simulation_session_id: str,
    equipment_id: str,
    maintenance_started_at: datetime,
    runtime: Runtime,
) -> str:
    """Identify the exact source runtime snapshot from which a branch diverges."""
    return _payload_hash(
        {
            "base_dataset_version": base_dataset_version,
            "source_run_id": source_run_id,
            "simulation_session_id": simulation_session_id,
            "equipment_id": equipment_id,
            "maintenance_started_at": maintenance_started_at.isoformat(),
            "runtime": _runtime_checkpoint(runtime),
        }
    )


def _restore_runtime(asset: dict[str, str], payload: dict[str, Any]) -> Runtime:
    rng = random.Random()
    rng.setstate(_tuple_random_state(payload["rng_state"]))

    def timestamp(value: str | None) -> datetime | None:
        return datetime.fromisoformat(value) if value else None

    return Runtime(
        asset=asset,
        rng=rng,
        baseline={key: float(value) for key, value in payload["baseline"].items()},
        noise_state={
            key: float(value) for key, value in payload.get("noise_state", {}).items()
        },
        tool_wear_min=float(payload.get("tool_wear_min", 0.0)),
        tool_change_threshold_min=float(payload.get("tool_change_threshold_min", 210.0)),
        product_started_at=timestamp(payload.get("product_started_at")),
        product_type=str(payload.get("product_type", "L")),
        product_ticks=int(payload.get("product_ticks", 0)),
        product_counter=int(payload.get("product_counter", 0)),
        planned_maintenance_until=timestamp(payload.get("planned_maintenance_until")),
        tool_reset_at=timestamp(payload.get("tool_reset_at")),
    )


def _durable_append(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


@dataclass
class OverlayBranch:
    simulation_session_id: str
    equipment_id: str
    maintenance_action_id: str
    action_code: str
    maintenance_started_at: datetime
    runtime: Runtime
    base_source_sha256: str
    state_version: int
    phase: str = "maintenance"
    maintenance_event_id: str | None = None
    maintenance_completed_at: datetime | None = None
    restart_at: datetime | None = None
    overlay_branch_id: str | None = None
    history_segment_id: str | None = None
    next_observed_at: datetime | None = None
    generated_rows: int = 0

    @property
    def key(self) -> str:
        return ":".join(
            (self.simulation_session_id, self.equipment_id, self.maintenance_action_id)
        )


class OverlayObservationStore:
    """Append-only observation storage with semantic conflict detection."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._index: dict[Path, dict[str, str]] = {}

    @staticmethod
    def _safe(value: str) -> str:
        return "".join(
            char if char.isalnum() or char in {"-", "_", "."} else "_"
            for char in value
        )

    def path_for(self, branch: OverlayBranch) -> Path:
        if not branch.overlay_branch_id:
            raise OverlayContractError(
                "overlay_branch_id is required before writing observations"
            )
        session = self._safe(branch.simulation_session_id)
        branch_name = self._safe(branch.overlay_branch_id)
        return self.root / session / f"{branch_name}.jsonl"

    def _load_index(self, path: Path) -> dict[str, str]:
        if path in self._index:
            return self._index[path]
        index: dict[str, str] = {}
        if path.exists():
            for line_number, raw_line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not raw_line.strip():
                    continue
                try:
                    row = json.loads(raw_line)
                    observation_id = str(row["observation_id"])
                    digest = str(row["observation_sha256"])
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise OverlayContractError(
                        f"invalid stored overlay observation at {path}:{line_number}"
                    ) from exc
                existing = index.get(observation_id)
                if existing is not None and existing != digest:
                    raise OverlayConflict(
                        f"stored observation identity conflict: {observation_id}"
                    )
                index[observation_id] = digest
        self._index[path] = index
        return index

    def append(self, branch: OverlayBranch, observation: dict[str, Any]) -> bool:
        path = self.path_for(branch)
        index = self._load_index(path)
        observation_id = str(observation["observation_id"])
        digest = _semantic_observation_hash(observation)
        observation["observation_sha256"] = digest
        existing = index.get(observation_id)
        if existing is not None:
            if existing != digest:
                raise OverlayConflict(f"observation identity conflict: {observation_id}")
            return False
        _durable_append(path, observation)
        index[observation_id] = digest
        return True


class RuntimeOverlayCoordinator:
    """Own target branches without changing Canonical simulation semantics."""

    def __init__(
        self,
        *,
        canonical_producer: SimulationProducer,
        simulation_session_id: str,
        output_root: Path,
        base_dataset_version: str = "predictive-maintenance-canonical-v3.1",
        generated_at: Callable[[], datetime] | None = None,
    ) -> None:
        self.canonical_producer = canonical_producer
        if not simulation_session_id.strip():
            raise OverlayContractError("simulation_session_id must not be blank")
        self.simulation_session_id = simulation_session_id
        self.assets = {
            str(asset["asset_id"]): asset for asset in canonical_producer.assets
        }
        self.interval = timedelta(minutes=canonical_producer.interval_minutes)
        self.base_dataset_version = base_dataset_version
        self.generated_at = generated_at or (lambda: datetime.now(timezone.utc))
        self.store = OverlayObservationStore(output_root / "runtime_overlay")
        self.checkpoint_path = (
            output_root / "runtime_overlay" / "runtime_overlay_state.json"
        )
        self.available_event_path = (
            output_root / "runtime_overlay" / "observations_available.jsonl"
        )
        self.branches: dict[str, OverlayBranch] = {}
        self.branch_by_equipment: dict[str, str] = {}
        self.processed_events: dict[str, str] = {}
        self.processed_event_ids: dict[str, str] = {}
        self.pending_available_events: dict[str, dict[str, Any]] = {}
        self._available_event_index: dict[str, str] | None = None
        self._restore_checkpoint()

    @property
    def active_equipment_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.branch_by_equipment))

    def excluded_equipment_ids(self, observed_at: datetime) -> set[str]:
        return {
            equipment_id
            for equipment_id, key in self.branch_by_equipment.items()
            if observed_at >= self.branches[key].maintenance_started_at
        }

    def _checkpoint(self) -> None:
        branches: dict[str, Any] = {}
        for key, branch in self.branches.items():
            branches[key] = {
                "simulation_session_id": branch.simulation_session_id,
                "equipment_id": branch.equipment_id,
                "maintenance_action_id": branch.maintenance_action_id,
                "action_code": branch.action_code,
                "maintenance_started_at": branch.maintenance_started_at.isoformat(),
                "base_source_sha256": branch.base_source_sha256,
                "state_version": branch.state_version,
                "phase": branch.phase,
                "maintenance_event_id": branch.maintenance_event_id,
                "maintenance_completed_at": (
                    branch.maintenance_completed_at.isoformat()
                    if branch.maintenance_completed_at
                    else None
                ),
                "restart_at": branch.restart_at.isoformat() if branch.restart_at else None,
                "overlay_branch_id": branch.overlay_branch_id,
                "history_segment_id": branch.history_segment_id,
                "next_observed_at": (
                    branch.next_observed_at.isoformat()
                    if branch.next_observed_at
                    else None
                ),
                "generated_rows": branch.generated_rows,
                "runtime": _runtime_checkpoint(branch.runtime),
            }
        _atomic_json(
            self.checkpoint_path,
            {
                "checkpoint_version": CHECKPOINT_VERSION,
                "source_run_id": self.canonical_producer.run_id,
                "simulation_session_id": self.simulation_session_id,
                "processed_events": self.processed_events,
                "processed_event_ids": self.processed_event_ids,
                "pending_available_events": self.pending_available_events,
                "branches": branches,
            },
        )

    def _restore_checkpoint(self) -> None:
        if not self.checkpoint_path.exists():
            return
        try:
            payload = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise OverlayContractError("invalid Runtime Overlay checkpoint") from exc
        if int(payload.get("checkpoint_version", 0)) != CHECKPOINT_VERSION:
            raise OverlayContractError("unsupported Runtime Overlay checkpoint version")
        self.processed_events = {
            str(key): str(value)
            for key, value in payload.get("processed_events", {}).items()
        }
        self.processed_event_ids = {
            str(key): str(value)
            for key, value in payload.get("processed_event_ids", {}).items()
        }
        pending = payload.get("pending_available_events", {})
        if not isinstance(pending, dict):
            raise OverlayContractError("pending_available_events must be an object")
        self.pending_available_events = {
            str(event_id): dict(event)
            for event_id, event in pending.items()
            if isinstance(event, dict)
        }
        stored_source_run_id = str(payload.get("source_run_id") or "")
        stored_session_id = str(payload.get("simulation_session_id") or "")
        stored_branches = payload.get("branches", {})
        if not isinstance(stored_branches, dict):
            raise OverlayContractError("Runtime Overlay checkpoint branches must be an object")
        same_active_run = (
            stored_source_run_id == self.canonical_producer.run_id
            and stored_session_id == self.simulation_session_id
        )
        for key, item in stored_branches.items():
            if not same_active_run:
                continue
            equipment_id = str(item["equipment_id"])
            asset = self.assets.get(equipment_id)
            if asset is None:
                raise OverlayContractError(
                    f"checkpoint references unknown equipment: {equipment_id}"
                )
            branch = OverlayBranch(
                simulation_session_id=str(item["simulation_session_id"]),
                equipment_id=equipment_id,
                maintenance_action_id=str(item["maintenance_action_id"]),
                action_code=str(item["action_code"]),
                maintenance_started_at=_parse_datetime(
                    item["maintenance_started_at"], "maintenance_started_at"
                ),
                runtime=_restore_runtime(asset, item["runtime"]),
                base_source_sha256=str(item["base_source_sha256"]),
                state_version=int(item["state_version"]),
                phase=str(item["phase"]),
                maintenance_event_id=item.get("maintenance_event_id"),
                maintenance_completed_at=(
                    _parse_datetime(
                        item["maintenance_completed_at"],
                        "maintenance_completed_at",
                    )
                    if item.get("maintenance_completed_at")
                    else None
                ),
                restart_at=(
                    _parse_datetime(item["restart_at"], "restart_at")
                    if item.get("restart_at")
                    else None
                ),
                overlay_branch_id=item.get("overlay_branch_id"),
                history_segment_id=item.get("history_segment_id"),
                next_observed_at=(
                    _parse_datetime(item["next_observed_at"], "next_observed_at")
                    if item.get("next_observed_at")
                    else None
                ),
                generated_rows=int(item.get("generated_rows", 0)),
            )
            self.branches[str(key)] = branch
            self.branch_by_equipment[equipment_id] = str(key)
        if stored_branches and not same_active_run:
            # RuntimeManager owns one active source run.  Keep append-only rows
            # and event dedupe indexes, but never expose a previous run's
            # branches as currently paused equipment to Backend readers.
            self._checkpoint()

    @staticmethod
    def _required(event: dict[str, Any], *fields: str) -> None:
        missing = [field for field in fields if event.get(field) in (None, "")]
        if missing:
            raise OverlayContractError(
                "missing required field(s): " + ", ".join(sorted(missing))
            )

    @staticmethod
    def _validate_text(value: Any, field: str, minimum: int, maximum: int) -> None:
        if not isinstance(value, str) or not minimum <= len(value) <= maximum:
            raise OverlayContractError(
                f"{field} must be a string with length {minimum}..{maximum}"
            )

    @classmethod
    def _validate_contract(cls, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            raise OverlayContractError("maintenance event must be an object")
        unknown = sorted(set(event) - _EVENT_FIELDS)
        if unknown:
            raise OverlayContractError("unknown field(s): " + ", ".join(unknown))
        cls._required(
            event,
            "contract_version",
            "event_type",
            "event_id",
            "idempotency_key",
            "state_version",
            "simulation_session_id",
            "maintenance_action_id",
            "equipment_id",
            "caused_by",
        )
        if event["contract_version"] != MAINTENANCE_CONTRACT_VERSION:
            raise OverlayContractError(
                f"unsupported maintenance contract: {event['contract_version']}"
            )
        if event["event_type"] not in _EVENT_TYPES:
            raise OverlayContractError(
                f"unsupported maintenance event: {event['event_type']}"
            )
        version = event["state_version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise OverlayContractError("state_version must be a positive integer")
        for field, (minimum, maximum) in _TEXT_FIELDS.items():
            if field in event:
                cls._validate_text(event[field], field, minimum, maximum)
        for field in _TIMESTAMP_FIELDS:
            if field in event:
                _parse_datetime(event[field], field)
        if "action_code" in event and event["action_code"] != "TOOL_REPLACEMENT":
            raise OverlayContractError("action_code must be TOOL_REPLACEMENT")
        if "state_patch" in event and event["state_patch"] != _TOOL_REPLACEMENT_PATCH:
            raise OverlayContractError(
                "state_patch must contain the canonical TOOL_REPLACEMENT patch"
            )
        caused_by = event["caused_by"]
        if not isinstance(caused_by, dict) or set(caused_by) != _CAUSED_BY_FIELDS:
            raise OverlayContractError("caused_by must contain the canonical lineage fields")
        cls._required(caused_by, *_CAUSED_BY_FIELDS)
        for field in _CAUSED_BY_FIELDS:
            cls._validate_text(caused_by[field], f"caused_by.{field}", 1, 240)

        event_type = str(event["event_type"])
        if event_type == "maintenance.started":
            cls._required(event, "work_order_id", "maintenance_started_at", "action_code")
            if "maintenance_event_id" in event:
                raise OverlayContractError(
                    "maintenance.started must not include maintenance_event_id"
                )
        elif event_type == "maintenance.completed":
            cls._required(
                event,
                "maintenance_event_id",
                "maintenance_completed_at",
                "action_code",
                "state_patch",
            )
            if (
                "maintenance_started_at" in event
                and _parse_datetime(
                    event["maintenance_completed_at"], "maintenance_completed_at"
                )
                < _parse_datetime(event["maintenance_started_at"], "maintenance_started_at")
            ):
                raise OverlayContractError(
                    "maintenance_completed_at must be >= maintenance_started_at"
                )
        else:
            cls._required(event, "maintenance_event_id", "restart_at")
            if (
                "maintenance_completed_at" in event
                and _parse_datetime(event["restart_at"], "restart_at")
                < _parse_datetime(
                    event["maintenance_completed_at"], "maintenance_completed_at"
                )
            ):
                raise OverlayContractError(
                    "restart_at must be >= maintenance_completed_at"
                )

    def _event_replay(self, event: dict[str, Any]) -> bool:
        digest = _payload_hash(event)
        idempotency_key = str(event["idempotency_key"])
        event_id = str(event["event_id"])
        identities = (
            ("idempotency_key", idempotency_key, self.processed_events),
            ("event_id", event_id, self.processed_event_ids),
        )
        replayed = False
        for label, key, index in identities:
            existing = index.get(key)
            if existing is not None and existing != digest:
                raise OverlayConflict(f"{label}_conflict: {key}")
            replayed = replayed or existing is not None
        return replayed

    def _record_event(self, event: dict[str, Any]) -> None:
        digest = _payload_hash(event)
        self.processed_events[str(event["idempotency_key"])] = digest
        self.processed_event_ids[str(event["event_id"])] = digest
        self._checkpoint()

    def _branch_for_event(self, event: dict[str, Any]) -> OverlayBranch:
        key = ":".join(
            (
                str(event["simulation_session_id"]),
                str(event["equipment_id"]),
                str(event["maintenance_action_id"]),
            )
        )
        branch = self.branches.get(key)
        if branch is None:
            raise OverlayContractError(f"maintenance.started branch not found: {key}")
        return branch

    @staticmethod
    def _assert_newer_version(branch: OverlayBranch, event: dict[str, Any]) -> int:
        version = int(event["state_version"])
        if version < branch.state_version:
            raise StaleOverlayEvent(
                f"stale state_version {version}; current={branch.state_version}"
            )
        if version == branch.state_version:
            raise OverlayConflict(f"state_version_conflict: {version}")
        return version

    def process_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Apply one versioned Maintenance event to source-side overlay state."""
        self._validate_contract(event)
        if str(event["simulation_session_id"]) != self.simulation_session_id:
            raise OverlayContractError(
                "simulation_session_id does not match the active replay-session binding"
            )
        equipment_id = str(event["equipment_id"])
        if equipment_id not in self.assets or equipment_id not in self.canonical_producer.runtimes:
            raise OverlayContractError(f"unknown equipment_id: {equipment_id}")
        if self._event_replay(event):
            branch = self._branch_for_event(event)
            return {
                "replayed": True,
                "phase": branch.phase,
                "state_version": branch.state_version,
            }

        event_type = str(event["event_type"])
        if event_type == "maintenance.started":
            key = ":".join(
                (
                    str(event["simulation_session_id"]),
                    equipment_id,
                    str(event["maintenance_action_id"]),
                )
            )
            if key in self.branches:
                raise OverlayConflict(f"maintenance branch already exists: {key}")
            if equipment_id in self.branch_by_equipment:
                raise OverlayConflict(
                    f"equipment already has an active overlay branch: {equipment_id}"
                )
            maintenance_started_at = _parse_datetime(
                event["maintenance_started_at"], "maintenance_started_at"
            )
            runtime_snapshot = copy.deepcopy(
                self.canonical_producer.runtimes[equipment_id]
            )
            branch = OverlayBranch(
                simulation_session_id=str(event["simulation_session_id"]),
                equipment_id=equipment_id,
                maintenance_action_id=str(event["maintenance_action_id"]),
                action_code=str(event["action_code"]),
                maintenance_started_at=maintenance_started_at,
                runtime=runtime_snapshot,
                base_source_sha256=_base_source_snapshot_sha256(
                    base_dataset_version=self.base_dataset_version,
                    source_run_id=self.canonical_producer.run_id,
                    simulation_session_id=self.simulation_session_id,
                    equipment_id=equipment_id,
                    maintenance_started_at=maintenance_started_at,
                    runtime=runtime_snapshot,
                ),
                state_version=int(event["state_version"]),
            )
            self.branches[key] = branch
            self.branch_by_equipment[equipment_id] = key
        else:
            branch = self._branch_for_event(event)
            version = self._assert_newer_version(branch, event)
            if event_type == "maintenance.completed":
                self._required(
                    event,
                    "maintenance_event_id",
                    "maintenance_completed_at",
                    "action_code",
                    "state_patch",
                )
                if branch.phase != "maintenance":
                    raise OverlayContractError(
                        "maintenance.completed requires maintenance phase"
                    )
                completed_at = _parse_datetime(
                    event["maintenance_completed_at"], "maintenance_completed_at"
                )
                if completed_at < branch.maintenance_started_at:
                    raise OverlayContractError(
                        "maintenance_completed_at must be >= maintenance_started_at"
                    )
                self._apply_state_patch(branch, event)
                branch.maintenance_event_id = str(event["maintenance_event_id"])
                branch.maintenance_completed_at = completed_at
                branch.phase = "completed"
                branch.state_version = version
            else:
                self._required(event, "maintenance_event_id", "restart_at")
                if branch.phase != "completed" or branch.maintenance_completed_at is None:
                    raise OverlayContractError(
                        "maintenance.replay_requested requires completed maintenance"
                    )
                if str(event["maintenance_event_id"]) != branch.maintenance_event_id:
                    raise OverlayContractError(
                        "maintenance_event_id does not match completed branch"
                    )
                restart_at = _parse_datetime(event["restart_at"], "restart_at")
                if restart_at < branch.maintenance_completed_at:
                    raise OverlayContractError(
                        "restart_at must be >= maintenance_completed_at"
                    )
                branch.restart_at = restart_at
                branch.overlay_branch_id = f"{branch.maintenance_event_id}:post"
                branch.history_segment_id = f"{branch.maintenance_event_id}:post"
                branch.next_observed_at = restart_at
                branch.phase = "restarting"
                branch.state_version = version

        self._record_event(event)
        return {
            "replayed": False,
            "phase": branch.phase,
            "state_version": branch.state_version,
        }

    @staticmethod
    def _apply_state_patch(branch: OverlayBranch, event: dict[str, Any]) -> None:
        action_code = str(event["action_code"])
        if action_code != branch.action_code:
            raise OverlayContractError(
                "action_code does not match maintenance.started"
            )
        if action_code != "TOOL_REPLACEMENT":
            raise OverlayContractError(f"unsupported MVP action_code: {action_code}")
        if event["state_patch"] != _TOOL_REPLACEMENT_PATCH:
            raise OverlayContractError(
                "TOOL_REPLACEMENT requires tool_wear_min reset -> 0 min"
            )
        if str(branch.runtime.asset.get("asset_type")) != "cnc":
            raise OverlayContractError(
                "TOOL_REPLACEMENT is only valid for CNC equipment"
            )
        branch.runtime.tool_wear_min = 0.0
        branch.runtime.tool_reset_at = None
        branch.runtime.planned_maintenance_until = None

    def _produce_overlay_record(
        self,
        branch: OverlayBranch,
        observed_at: datetime,
    ) -> dict[str, Any]:
        if branch.overlay_branch_id is None or branch.history_segment_id is None:
            raise OverlayContractError("overlay branch identity is not initialized")
        producer = SimulationProducer(
            run_id=(
                f"{self.canonical_producer.run_id}:overlay:"
                f"{branch.maintenance_event_id}"
            ),
            start_at=self.canonical_producer.start_at,
            end_at=max(self.canonical_producer.end_at, observed_at + self.interval),
            interval_minutes=self.canonical_producer.interval_minutes,
            product_cycle_minutes=self.canonical_producer.product_cycle_minutes,
            seed=self.canonical_producer.seed,
            rate_profile=self.canonical_producer.rate_profile,
            initial_sequence=branch.generated_rows,
        )
        producer.runtimes[branch.equipment_id] = branch.runtime
        producer.episodes_by_asset[branch.equipment_id] = []
        result = producer.produce_tick(
            observed_at,
            included_asset_ids={branch.equipment_id},
        )
        if len(result.records) != 1:
            raise RuntimeError(
                f"overlay producer emitted {len(result.records)} records for one equipment"
            )
        branch.runtime = producer.runtimes[branch.equipment_id]
        record = result.records[0]
        overlay_metadata = {
            "overlay_id": branch.overlay_branch_id,
            "parent_branch": "canonical",
            "maintenance_event_id": branch.maintenance_event_id,
            "state_patch_reference": branch.maintenance_action_id,
            "simulation_session_id": branch.simulation_session_id,
            "history_segment_id": branch.history_segment_id,
            "state_version": branch.state_version,
        }
        observation = record.to_dict()
        observation.update(
            {
                "equipment_id": branch.equipment_id,
                "observation_id": _overlay_observation_id(
                    branch,
                    observed_at,
                    record.measurements,
                ),
                "generated_at": self.generated_at().isoformat(),
                # The internal physics record remains a simulation SensorRecord.
                # This external DTO identifies the maintenance-derived source.
                "source_kind": OVERLAY_SOURCE_KIND,
                "branch_kind": "overlay",
                "overlay": overlay_metadata,
                "base_dataset_version": self.base_dataset_version,
                "base_source_sha256": branch.base_source_sha256,
                "simulation_session_id": branch.simulation_session_id,
                "overlay_branch_id": branch.overlay_branch_id,
                "maintenance_event_id": branch.maintenance_event_id,
                "maintenance_action_id": branch.maintenance_action_id,
                "state_version": branch.state_version,
                "history_segment_id": branch.history_segment_id,
            }
        )
        # The flat fields are a compatibility projection for the current
        # ontology_dashboard Runtime Overlay reader.  ``measurements`` remains
        # the measurement source of truth and both views use the same values.
        observation.update(record.measurements)
        return observation

    def advance_branch_to(
        self,
        equipment_id: str,
        target_virtual_time: datetime,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Fast-forward one branch without changing the global simulation clock."""
        key = self.branch_by_equipment.get(equipment_id)
        if key is None:
            raise OverlayContractError(
                f"no overlay branch for equipment: {equipment_id}"
            )
        branch = self.branches[key]
        if branch.phase not in {"restarting", "running"} or branch.next_observed_at is None:
            return [], None
        if target_virtual_time.tzinfo is None:
            raise OverlayContractError(
                "target_virtual_time must include timezone information"
            )

        written: list[dict[str, Any]] = []
        while branch.next_observed_at <= target_virtual_time:
            observed_at = branch.next_observed_at
            observation = self._produce_overlay_record(branch, observed_at)
            self.store.append(branch, observation)
            written.append(observation)
            branch.generated_rows += 1
            branch.next_observed_at = observed_at + self.interval
        if not written:
            return [], None

        branch.phase = "running"
        available = self._available_event(branch, written)
        self.pending_available_events[str(available["event_id"])] = available
        self._checkpoint()
        return written, available

    def advance_active_branches_to(
        self,
        target_virtual_time: datetime,
    ) -> list[dict[str, Any]]:
        available_events: list[dict[str, Any]] = []
        for equipment_id in self.active_equipment_ids:
            _rows, available = self.advance_branch_to(
                equipment_id,
                target_virtual_time,
            )
            if available is not None:
                self.persist_available_event(available)
                available_events.append(available)
        return available_events

    def _available_event(
        self,
        branch: OverlayBranch,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        path = self.store.path_for(branch)
        return {
            "contract_version": AVAILABLE_CONTRACT_VERSION,
            "event_type": "runtime_overlay.observations.available",
            "event_id": (
                f"OVERLAY-AVAILABLE:{branch.overlay_branch_id}:{branch.generated_rows}"
            ),
            "simulation_session_id": branch.simulation_session_id,
            "equipment_id": branch.equipment_id,
            "maintenance_action_id": branch.maintenance_action_id,
            "maintenance_event_id": branch.maintenance_event_id,
            "overlay_branch_id": branch.overlay_branch_id,
            "history_segment_id": branch.history_segment_id,
            "source_kind": OVERLAY_SOURCE_KIND,
            "state_version": branch.state_version,
            "batch_rows": len(rows),
            "generated_rows": branch.generated_rows,
            "observed_from": rows[0]["observed_at"],
            "observed_to": rows[-1]["observed_at"],
            "storage_reference": str(path),
        }

    def _load_available_event_index(self) -> dict[str, str]:
        if self._available_event_index is not None:
            return self._available_event_index
        index: dict[str, str] = {}
        if self.available_event_path.exists():
            for line_number, raw_line in enumerate(
                self.available_event_path.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if not raw_line.strip():
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise OverlayContractError(
                        f"invalid availability event at {self.available_event_path}:"
                        f"{line_number}"
                    ) from exc
                event_id = str(event.get("event_id") or "")
                if not event_id:
                    raise OverlayContractError(
                        "stored availability event is missing event_id"
                    )
                digest = _payload_hash(event)
                existing = index.get(event_id)
                if existing is not None and existing != digest:
                    raise OverlayConflict(
                        f"stored availability event identity conflict: {event_id}"
                    )
                index[event_id] = digest
        self._available_event_index = index
        return index

    def persist_available_event(self, event: dict[str, Any]) -> None:
        event_id = str(event.get("event_id") or "")
        if not event_id:
            raise OverlayContractError("availability event_id is required")
        digest = _payload_hash(event)
        index = self._load_available_event_index()
        existing = index.get(event_id)
        if existing is not None and existing != digest:
            raise OverlayConflict(
                f"availability event identity conflict: {event_id}"
            )
        if existing is None:
            _durable_append(self.available_event_path, event)
            index[event_id] = digest
        if event_id in self.pending_available_events:
            del self.pending_available_events[event_id]
            self._checkpoint()

    def recover_pending_available_events(self) -> int:
        recovered = 0
        for event_id in list(self.pending_available_events):
            self.persist_available_event(self.pending_available_events[event_id])
            recovered += 1
        return recovered

    def consume_event_file(self, path: Path) -> int:
        """Consume the idempotent JSONL inbox produced by Backend Outbox dispatch."""
        if not path.exists():
            return 0
        processed = 0
        for line_number, raw_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not raw_line.strip():
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise OverlayContractError(
                    f"invalid maintenance event JSON at {path}:{line_number}"
                ) from exc
            if (
                isinstance(event, dict)
                and str(event.get("simulation_session_id") or "")
                != self.simulation_session_id
            ):
                continue
            result = self.process_event(event)
            processed += int(not result["replayed"])
        return processed

    def outputs(self) -> dict[str, Any]:
        branch_files = [
            str(self.store.path_for(branch))
            for branch in self.branches.values()
            if branch.overlay_branch_id
        ]
        return {
            "checkpoint": str(self.checkpoint_path),
            "observations_available": str(self.available_event_path),
            "branches": branch_files,
            "active_equipment_ids": list(self.active_equipment_ids),
        }

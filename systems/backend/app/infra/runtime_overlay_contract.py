"""Machine-readable Runtime Overlay producer/consumer contract validation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from app.common.runtime_settings import project_root


OBSERVATION_CONTRACT_VERSION = "runtime-overlay-observation-v1"
AVAILABLE_CONTRACT_VERSION = "runtime-overlay-observations-available-v1"
OVERLAY_SOURCE_KIND = "maintenance_replay_overlay"
_MEASUREMENT_FIELDS = (
    "air_temperature_k",
    "process_temperature_k",
    "rotational_speed_rpm",
    "torque_nm",
    "tool_wear_min",
    "is_operating",
    "operating_state",
    "product_type",
)


def _storage_component(simulation_session_id: str, overlay_branch_id: str) -> str:
    """Return a collision-resistant path component for a logical identity pair."""
    identity = json.dumps(
        [str(simulation_session_id), str(overlay_branch_id)],
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(identity).hexdigest()
    return f"sha256-{digest}"


def expected_storage_reference(event: dict[str, Any]) -> str:
    component = _storage_component(
        str(event["simulation_session_id"]),
        str(event["overlay_branch_id"]),
    )
    return (PurePosixPath("runtime_overlay") / f"{component}.jsonl").as_posix()


def resolve_storage_reference(stream_root: str | Path, event: dict[str, Any]) -> Path:
    reference = PurePosixPath(str(event["storage_reference"]))
    if reference.is_absolute() or ".." in reference.parts:
        raise ValueError("Runtime Overlay storage_reference must be a safe relative path")
    expected = expected_storage_reference(event)
    if reference.as_posix() != expected:
        raise ValueError(
            "Runtime Overlay storage_reference does not match its session/branch: "
            f"expected={expected} actual={reference.as_posix()}"
        )
    root = Path(stream_root).expanduser().resolve()
    candidate = root.joinpath(*reference.parts).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "Runtime Overlay storage_reference must resolve inside the stream root"
        ) from exc
    return candidate


def semantic_observation_sha256(payload: dict[str, Any]) -> str:
    semantic = {
        key: value
        for key, value in payload.items()
        if key not in {"generated_at", "observation_sha256"}
    }
    encoded = json.dumps(
        semantic,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@lru_cache(maxsize=2)
def _validator(schema_name: str) -> Draft202012Validator:
    schema_path = project_root() / "contracts" / "schemas" / schema_name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_schema(payload: dict[str, Any], schema_name: str, label: str) -> None:
    errors = sorted(
        _validator(schema_name).iter_errors(payload),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        rendered = "; ".join(
            f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}"
            for error in errors
        )
        raise ValueError(f"{label} schema validation failed: {rendered}")


def validate_overlay_observation(payload: dict[str, Any]) -> None:
    _validate_schema(
        payload,
        "runtime-overlay-observation.schema.json",
        "Runtime Overlay observation",
    )
    if payload["asset_id"] != payload["equipment_id"]:
        raise ValueError("Runtime Overlay asset_id must equal equipment_id")
    measurements = payload["measurements"]
    for field in _MEASUREMENT_FIELDS:
        if payload[field] != measurements[field]:
            raise ValueError(
                f"Runtime Overlay flat projection differs from measurements.{field}"
            )
    overlay = payload["overlay"]
    mirrored = {
        "overlay_id": "overlay_branch_id",
        "maintenance_event_id": "maintenance_event_id",
        "state_patch_reference": "maintenance_action_id",
        "simulation_session_id": "simulation_session_id",
        "history_segment_id": "history_segment_id",
        "state_version": "state_version",
    }
    for nested, top_level in mirrored.items():
        if overlay[nested] != payload[top_level]:
            raise ValueError(
                f"Runtime Overlay overlay.{nested} differs from {top_level}"
            )
    actual = semantic_observation_sha256(payload)
    if payload["observation_sha256"] != actual:
        raise ValueError(
            "Runtime Overlay observation checksum mismatch: "
            f"declared={payload['observation_sha256']} actual={actual}"
        )


def validate_overlay_available_event(payload: dict[str, Any]) -> None:
    _validate_schema(
        payload,
        "runtime-overlay-observations-available.schema.json",
        "Runtime Overlay observations available event",
    )
    if int(payload["generated_rows"]) < int(payload["batch_rows"]):
        raise ValueError("Runtime Overlay generated_rows must be >= batch_rows")
    observed_from = datetime.fromisoformat(
        str(payload["observed_from"]).replace("Z", "+00:00")
    )
    observed_to = datetime.fromisoformat(
        str(payload["observed_to"]).replace("Z", "+00:00")
    )
    if observed_to < observed_from:
        raise ValueError("Runtime Overlay observed_to must be >= observed_from")
    expected = expected_storage_reference(payload)
    if str(payload["storage_reference"]) != expected:
        raise ValueError(
            "Runtime Overlay storage_reference does not match its session/branch"
        )

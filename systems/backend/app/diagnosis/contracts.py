from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

MODEL_INPUT_COLUMNS = [
    "Type",
    "Air temperature [K]",
    "Process temperature [K]",
    "Rotational speed [rpm]",
    "Torque [Nm]",
    "Tool wear [min]",
]
TARGET_COLUMN = "Machine failure"
FAILURE_MODE_COLUMNS = ["TWF", "HDF", "PWF", "OSF", "RNF"]
IDENTIFIER_COLUMNS = ["UDI", "Product ID"]
DERIVED_COLUMNS = [
    "temperature_difference_k",
    "mechanical_power_w",
    "overstrain_index",
]

SENSOR_RANGES: dict[str, tuple[float, float]] = {
    "air_temperature_k": (250.0, 350.0),
    "process_temperature_k": (250.0, 400.0),
    "rotational_speed_rpm": (0.0, 10000.0),
    "torque_nm": (0.0, 500.0),
    "tool_wear_min": (0.0, 1000.0),
}

DISPLAY_NAMES = {
    "tool_wear_min": "공구 마모",
    "temperature_difference_k": "공정·공기 온도 차이",
    "mechanical_power_w": "기계 동력",
    "overstrain_index": "과부하 지표",
    "torque_nm": "토크",
    "rotational_speed_rpm": "회전 속도",
    "process_temperature_k": "공정 온도",
    "air_temperature_k": "공기 온도",
}

UNITS = {
    "tool_wear_min": "min",
    "temperature_difference_k": "K",
    "mechanical_power_w": "W",
    "overstrain_index": "N·m·min",
    "torque_nm": "N·m",
    "rotational_speed_rpm": "rpm",
    "process_temperature_k": "K",
    "air_temperature_k": "K",
}


@dataclass(frozen=True)
class QualityIssue:
    code: str
    field: str
    message: str
    severity: str = "error"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "field": self.field,
            "message": self.message,
            "severity": self.severity,
        }


def project_root() -> Path:
    for env_name in ("ONTOLOGY_DASHBOARD_PROJECT_ROOT", "ONTOLOGY_DASHBOARD_ROOT"):
        configured = os.getenv(env_name, "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
    cwd = Path.cwd().resolve()
    if (cwd / "contracts" / "schemas").is_dir() and (cwd / "data" / "fixtures").is_dir():
        return cwd
    app_root = Path("/app")
    if (app_root / "contracts" / "schemas").is_dir() and (app_root / "data" / "fixtures").is_dir():
        return app_root
    for parent in Path(__file__).resolve().parents:
        if (parent / "contracts" / "schemas").is_dir() and (parent / "data" / "fixtures").is_dir():
            return parent
    raise RuntimeError(
        "cannot resolve ontology_dashboard runtime root; "
        "set ONTOLOGY_DASHBOARD_PROJECT_ROOT"
    )


def schema_path() -> Path:
    return project_root() / "contracts" / "schemas" / "input-event.schema.json"


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_fixture(path: str | Path, *, validate_envelope: bool = True) -> dict[str, Any]:
    payload = load_json(path)
    if validate_envelope:
        schema = load_json(schema_path())
        errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
            key=lambda item: list(item.absolute_path),
        )
        if errors:
            rendered = "; ".join(
                f"{'/'.join(map(str, err.absolute_path)) or '<root>'}: {err.message}"
                for err in errors
            )
            raise ValueError(f"fixture schema validation failed: {rendered}")
    return payload


def derive_features(observation: dict[str, Any]) -> dict[str, float]:
    required = [
        "air_temperature_k",
        "process_temperature_k",
        "rotational_speed_rpm",
        "torque_nm",
        "tool_wear_min",
    ]
    missing = [name for name in required if observation.get(name) is None]
    if missing:
        raise ValueError(f"cannot derive features with missing values: {missing}")

    air = float(observation["air_temperature_k"])
    process = float(observation["process_temperature_k"])
    speed = float(observation["rotational_speed_rpm"])
    torque = float(observation["torque_nm"])
    wear = float(observation["tool_wear_min"])
    return {
        "temperature_difference_k": process - air,
        "mechanical_power_w": torque * speed * (2.0 * math.pi / 60.0),
        "overstrain_index": torque * wear,
    }


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def audit_fixture(payload: dict[str, Any]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    observations = [*payload.get("history", []), payload.get("observation", {})]

    for index, observation in enumerate(observations):
        prefix = f"history[{index}]" if index < len(observations) - 1 else "observation"
        for field, (minimum, maximum) in SENSOR_RANGES.items():
            value = observation.get(field)
            if value is None:
                issues.append(QualityIssue("missing_sensor", f"{prefix}.{field}", "필수 센서 값이 없습니다."))
                continue
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                issues.append(QualityIssue("invalid_type", f"{prefix}.{field}", "센서 값이 숫자가 아닙니다."))
                continue
            if not math.isfinite(numeric) or not minimum <= numeric <= maximum:
                issues.append(
                    QualityIssue(
                        "out_of_range",
                        f"{prefix}.{field}",
                        f"값 {value}이 데이터 품질 범위 {minimum}–{maximum} 밖에 있습니다.",
                    )
                )

    timestamps = [_parse_timestamp(item.get("timestamp", "")) for item in payload.get("history", [])]
    if any(item is None for item in timestamps):
        issues.append(QualityIssue("invalid_timestamp", "history.timestamp", "유효하지 않은 타임스탬프가 있습니다."))
    else:
        for previous, current in zip(timestamps, timestamps[1:]):
            if current <= previous:  # type: ignore[operator]
                issues.append(QualityIssue("non_monotonic_time", "history.timestamp", "시계열 시간이 증가하지 않습니다."))
                break

    current_ts = _parse_timestamp(payload.get("observation", {}).get("timestamp", ""))
    if current_ts is None:
        issues.append(QualityIssue("invalid_timestamp", "observation.timestamp", "현재 관측 시각이 유효하지 않습니다."))
    elif timestamps and timestamps[-1] is not None and current_ts < timestamps[-1]:
        issues.append(QualityIssue("current_before_history", "observation.timestamp", "현재 관측이 마지막 이력보다 과거입니다."))

    return issues


def assert_no_leakage(feature_names: Iterable[str]) -> None:
    features = set(feature_names)
    forbidden = {TARGET_COLUMN, *FAILURE_MODE_COLUMNS}
    leaked = sorted(features & forbidden)
    if leaked:
        raise ValueError(f"target leakage columns are forbidden as model inputs: {leaked}")


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fixture_paths(root: Path | None = None) -> list[Path]:
    base = root or project_root()
    return sorted((base / "data" / "fixtures").glob("GS-*.json"))

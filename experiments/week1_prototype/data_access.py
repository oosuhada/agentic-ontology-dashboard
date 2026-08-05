"""Read-only access helpers for Predictive Maintenance Canonical V3.1."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

import pandas as pd


CANONICAL_ENV = "CANONICAL_V3_1_ROOT"


class CanonicalDataError(RuntimeError):
    """Raised when the Canonical V3.1 package cannot be resolved or read."""


def _candidate_roots(explicit: str | Path | None = None) -> Iterable[Path]:
    if explicit:
        yield Path(explicit).expanduser()

    configured = os.getenv(CANONICAL_ENV)
    if configured:
        yield Path(configured).expanduser()

    # Common local layout used by this project. This is only a convenience
    # fallback; portable executions should set CANONICAL_V3_1_ROOT explicitly.
    yield (
        Path.home()
        / "Documents"
        / "Macbook air personal"
        / "비스텔리전스 파이널 프로젝트"
        / "predictive_maintenance_canonical_v3.1"
    )

    cwd = Path.cwd().resolve()
    for parent in (cwd, *cwd.parents):
        yield parent / "predictive_maintenance_canonical_v3.1"


def resolve_canonical_root(explicit: str | Path | None = None) -> Path:
    """Return the package root after checking the required canonical files."""

    checked: list[str] = []
    for candidate in _candidate_roots(explicit):
        root = candidate.resolve()
        checked.append(str(root))
        if (
            (root / "canonical" / "dataset" / "asset_master.csv").is_file()
            and (
                root
                / "canonical"
                / "model_outputs"
                / "prediction_snapshot.jsonl"
            ).is_file()
        ):
            return root

    joined = "\n- ".join(checked)
    raise CanonicalDataError(
        "Canonical V3.1 package was not found. Set "
        f"{CANONICAL_ENV} to the package root. Checked:\n- {joined}"
    )


def canonical_path(root: Path, *parts: str) -> Path:
    path = root / "canonical" / Path(*parts)
    if not path.is_file():
        raise CanonicalDataError(f"Required canonical file is missing: {path}")
    return path


def _parse_timestamp_columns(frame: pd.DataFrame) -> pd.DataFrame:
    for column in frame.columns:
        if column.endswith("_at") or column == "observed_at":
            frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
    return frame


def load_asset_master(root: Path) -> pd.DataFrame:
    return pd.read_csv(canonical_path(root, "dataset", "asset_master.csv"))


def load_prediction_snapshot(root: Path) -> pd.DataFrame:
    frame = pd.read_json(
        canonical_path(root, "model_outputs", "prediction_snapshot.jsonl"),
        lines=True,
    )
    return _parse_timestamp_columns(frame)


def load_prediction_timeline(
    root: Path,
    asset_id: str,
    *,
    max_rows: int = 2_000,
) -> pd.DataFrame:
    """Read timeline rows for one asset without loading the full JSONL file."""

    rows: list[dict] = []
    path = canonical_path(root, "model_outputs", "prediction_timeline.jsonl")
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            payload = json.loads(raw_line)
            if payload.get("asset_id") != asset_id:
                continue
            rows.append(payload)

    if not rows:
        return pd.DataFrame(
            columns=[
                "asset_id",
                "asset_type",
                "observed_at",
                "failure_probability",
                "status",
            ]
        )

    frame = _parse_timestamp_columns(pd.DataFrame(rows))
    frame = frame.sort_values("observed_at")
    if len(frame) > max_rows:
        stride = max(1, len(frame) // max_rows)
        frame = frame.iloc[::stride].tail(max_rows)
    return frame.reset_index(drop=True)


def _read_filtered_csv(
    path: Path,
    *,
    asset_id: str,
    usecols: list[str],
    max_rows: int,
) -> pd.DataFrame:
    chunks: list[pd.DataFrame] = []
    for chunk in pd.read_csv(path, usecols=usecols, chunksize=50_000):
        selected = chunk.loc[chunk["asset_id"] == asset_id]
        if not selected.empty:
            chunks.append(selected)

    if not chunks:
        return pd.DataFrame(columns=usecols)

    frame = _parse_timestamp_columns(pd.concat(chunks, ignore_index=True))
    frame = frame.sort_values("observed_at")
    if len(frame) > max_rows:
        stride = max(1, len(frame) // max_rows)
        frame = frame.iloc[::stride].tail(max_rows)
    return frame.reset_index(drop=True)


def load_cnc_sensor_observation(
    root: Path,
    asset_id: str,
    *,
    max_rows: int = 2_500,
) -> pd.DataFrame:
    columns = [
        "observed_at",
        "asset_id",
        "product_type",
        "air_temperature_k",
        "process_temperature_k",
        "rotational_speed_rpm",
        "torque_nm",
        "tool_wear_min",
    ]
    return _read_filtered_csv(
        canonical_path(root, "dataset", "cnc_sensor_observation.csv"),
        asset_id=asset_id,
        usecols=columns,
        max_rows=max_rows,
    )


def load_compressor_sensor_observation(
    root: Path,
    asset_id: str,
    *,
    max_rows: int = 2_500,
) -> pd.DataFrame:
    columns = [
        "observed_at",
        "asset_id",
        "voltage_raw",
        "rotation_raw",
        "pressure_raw",
        "vibration_raw",
        "relative_vibration_z",
    ]
    return _read_filtered_csv(
        canonical_path(root, "dataset", "compressor_sensor_observation.csv"),
        asset_id=asset_id,
        usecols=columns,
        max_rows=max_rows,
    )


def load_failure_truth(root: Path) -> pd.DataFrame:
    compressor = pd.read_csv(
        canonical_path(root, "evaluation_truth", "compressor_failure_truth.csv")
    )
    cnc = pd.read_csv(canonical_path(root, "evaluation_truth", "cnc_failure_truth.csv"))
    frame = pd.concat([compressor, cnc], ignore_index=True)
    return _parse_timestamp_columns(frame)


def load_prediction_factors(root: Path, prediction_id: str) -> pd.DataFrame:
    rows: list[dict] = []
    path = canonical_path(root, "model_outputs", "prediction_factor.jsonl")
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            payload = json.loads(raw_line)
            if payload.get("prediction_id") == prediction_id:
                rows.append(payload)
    return pd.DataFrame(rows).sort_values("rank") if rows else pd.DataFrame()


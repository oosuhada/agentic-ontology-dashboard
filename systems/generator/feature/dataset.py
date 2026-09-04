from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .contracts import (
    FAILURE_MODE_COLUMNS,
    IDENTIFIER_COLUMNS,
    MODEL_INPUT_COLUMNS,
    TARGET_COLUMN,
    assert_no_leakage,
    file_sha256,
)

EXPECTED_COLUMNS = [*IDENTIFIER_COLUMNS, *MODEL_INPUT_COLUMNS, TARGET_COLUMN, *FAILURE_MODE_COLUMNS]
EXPECTED_REFERENCE_SHA256 = "59db4f1d9c34c58136d89e5a006ec190dcea19e9dbea74f6b3b0c6f22a44d183"


@dataclass(frozen=True)
class DatasetAudit:
    path: str
    sha256: str
    rows: int
    columns: int
    missing_cells: int
    duplicate_rows: int
    machine_failures: int
    failure_rate: float
    unexpected_columns: list[str]
    missing_columns: list[str]
    leakage_check: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_ai4i(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = [column for column in EXPECTED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"AI4I columns are missing: {missing}")
    return frame


def audit_ai4i(path: str | Path) -> DatasetAudit:
    source = Path(path)
    frame = load_ai4i(source)
    assert_no_leakage(MODEL_INPUT_COLUMNS)
    target = frame[TARGET_COLUMN]
    return DatasetAudit(
        path=str(source),
        sha256=file_sha256(source),
        rows=int(frame.shape[0]),
        columns=int(frame.shape[1]),
        missing_cells=int(frame.isna().sum().sum()),
        duplicate_rows=int(frame.duplicated().sum()),
        machine_failures=int(target.sum()),
        failure_rate=float(target.mean()),
        unexpected_columns=sorted(set(frame.columns) - set(EXPECTED_COLUMNS)),
        missing_columns=sorted(set(EXPECTED_COLUMNS) - set(frame.columns)),
        leakage_check="pass",
    )


def canonicalize(frame: pd.DataFrame) -> pd.DataFrame:
    renamed = frame.rename(
        columns={
            "Type": "product_type",
            "Air temperature [K]": "air_temperature_k",
            "Process temperature [K]": "process_temperature_k",
            "Rotational speed [rpm]": "rotational_speed_rpm",
            "Torque [Nm]": "torque_nm",
            "Tool wear [min]": "tool_wear_min",
            "Machine failure": "machine_failure",
        }
    ).copy()
    renamed["temperature_difference_k"] = renamed["process_temperature_k"] - renamed["air_temperature_k"]
    renamed["mechanical_power_w"] = (
        renamed["torque_nm"] * renamed["rotational_speed_rpm"] * (2.0 * 3.141592653589793 / 60.0)
    )
    renamed["overstrain_index"] = renamed["torque_nm"] * renamed["tool_wear_min"]
    return renamed

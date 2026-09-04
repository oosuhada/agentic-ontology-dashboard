"""Generator-local source/feature contract helpers.

These constants describe model-development inputs only. Runtime observation
validation lives under ``systems.backend.app.diagnosis`` so the generator and
backend do not import each other's implementation code.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable


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

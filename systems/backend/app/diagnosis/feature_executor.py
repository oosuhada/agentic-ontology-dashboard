"""Backend-owned execution of the published predictive-maintenance feature contract.

The Generator publishes feature names and history requirements, but Backend must
reproduce those features from runtime observations without importing Generator
implementation code.  ``pdm-feature-executor-v1`` mirrors the deterministic
grouped pandas semantics used by the Generator feature builder for one asset.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


FEATURE_EXECUTOR_VERSION = "pdm-feature-executor-v1"
_TEMPORAL_OPERATIONS = {
    "rolling_mean",
    "rolling_std",
    "gradient",
    "ema",
    "lag",
    "moving_average",
}


def _feature_recipe(feature_name: str) -> tuple[str, str, dict[str, int]] | None:
    parts = feature_name.split("__")
    if len(parts) != 4:
        return None
    source_field, _ontology_node, operation, parameter_text = parts
    if operation not in _TEMPORAL_OPERATIONS:
        return None

    parameters: dict[str, int] = {}
    if parameter_text != "default":
        parameter_parts = parameter_text.split("_")
        if len(parameter_parts) != 2 or parameter_parts[0] not in {"window", "span", "periods"}:
            raise ValueError(f"unsupported predictive-maintenance feature parameters: {feature_name}")
        try:
            parameters[parameter_parts[0]] = int(parameter_parts[1])
        except ValueError as exc:
            raise ValueError(f"invalid predictive-maintenance feature parameters: {feature_name}") from exc
    return source_field, operation, parameters


def _runtime_timeline(
    fixture: dict[str, Any],
    *,
    history_requirement: dict[str, Any],
) -> pd.DataFrame:
    observation = dict(fixture.get("observation") or {})
    history = [dict(row) for row in (fixture.get("history") or [])]
    order_by = str(history_requirement.get("order_by") or "observed_at")

    rows: list[dict[str, Any]] = []
    for row in [*history, observation]:
        timestamp = row.get(order_by) or row.get("timestamp") or row.get("observed_at")
        if timestamp is None:
            raise ValueError("runtime history row has no timestamp/observed_at value")
        normalized = dict(row)
        normalized["__runtime_timestamp"] = pd.Timestamp(timestamp)
        rows.append(normalized)

    # The current observation is often already the final history row.  Keep the
    # last value for a timestamp so the current observation replaces, rather
    # than duplicates, that row.
    by_timestamp: dict[pd.Timestamp, dict[str, Any]] = {}
    for row in rows:
        by_timestamp[row["__runtime_timestamp"]] = row
    ordered = [by_timestamp[key] for key in sorted(by_timestamp)]
    frame = pd.DataFrame(ordered)

    maximum_lookback_hours = float(history_requirement.get("maximum_lookback_hours") or 0.0)
    if maximum_lookback_hours > 0 and not frame.empty:
        cutoff = frame["__runtime_timestamp"].max() - pd.Timedelta(hours=maximum_lookback_hours)
        frame = frame[frame["__runtime_timestamp"] >= cutoff].reset_index(drop=True)

    minimum_rows = int(history_requirement.get("minimum_history_rows") or 0)
    if minimum_rows and len(frame) < minimum_rows:
        raise ValueError(
            "runtime history is insufficient for Model Artifact feature contract: "
            f"required>={minimum_rows} rows including current observation, actual={len(frame)}"
        )
    return frame


def _temporal_value(series: pd.Series, operation: str, parameters: dict[str, int]) -> float:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.isna().any():
        raise ValueError("runtime history contains non-numeric or missing values for a model feature")

    if operation in {"rolling_mean", "moving_average"}:
        window = int(parameters.get("window", 5 if operation == "rolling_mean" else 10))
        value = numeric.rolling(window, min_periods=1).mean().iloc[-1]
    elif operation == "rolling_std":
        window = int(parameters.get("window", 5))
        value = numeric.rolling(window, min_periods=1).std().iloc[-1]
    elif operation == "gradient":
        value = numeric.diff().iloc[-1]
    elif operation == "ema":
        span = int(parameters.get("span", 10))
        value = numeric.ewm(span=span).mean().iloc[-1]
    elif operation == "lag":
        periods = int(parameters.get("periods", 1))
        value = numeric.shift(periods).iloc[-1]
    else:  # pragma: no cover - guarded by _feature_recipe
        raise ValueError(f"unsupported predictive-maintenance feature operation: {operation}")

    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"runtime history cannot produce finite feature value for operation={operation}")
    return numeric_value


def execute_feature_contract(
    fixture: dict[str, Any],
    *,
    feature_names: list[str],
    direct_values: dict[str, Any],
    history_requirement: dict[str, Any] | None = None,
    executor_version: str | None = None,
) -> dict[str, Any]:
    """Return model-ready values in the exact published Feature Schema order."""

    recipes = {name: _feature_recipe(name) for name in feature_names}
    temporal_names = [name for name, recipe in recipes.items() if recipe is not None]
    if temporal_names and executor_version != FEATURE_EXECUTOR_VERSION:
        raise ValueError(
            "Model Artifact requires temporal feature execution but declares unsupported "
            f"feature_executor_version={executor_version!r}"
        )

    timeline = (
        _runtime_timeline(fixture, history_requirement=history_requirement or {})
        if temporal_names
        else None
    )

    values: dict[str, Any] = {}
    for feature_name in feature_names:
        if feature_name in direct_values:
            values[feature_name] = direct_values[feature_name]
            continue

        recipe = recipes[feature_name]
        if recipe is None or timeline is None:
            raise ValueError(f"runtime observation is incompatible with Model Artifact feature: {feature_name}")
        source_field, operation, parameters = recipe
        if source_field not in timeline.columns:
            raise ValueError(
                "runtime history is incompatible with Model Artifact feature source: "
                f"{source_field}"
            )
        values[feature_name] = _temporal_value(timeline[source_field], operation, parameters)
    return values

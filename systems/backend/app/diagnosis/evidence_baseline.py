from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Any, Callable

_NON_SENSOR_FIELDS = {"timestamp", "product_type"}


@dataclass(frozen=True)
class BaselineStat:
    mean: float | None
    std: float
    n: int
    z_score: float | None


@dataclass(frozen=True)
class BaselineWindow:
    rows: list[tuple[str, dict[str, float]]]
    observed_at: str

    @property
    def display_timestamps(self) -> list[str]:
        timestamps = [timestamp for timestamp, row in self.rows if timestamp and row]
        if self.observed_at:
            timestamps.append(self.observed_at)
        return timestamps

    def stat(self, feature: str, current: float) -> BaselineStat:
        values = [row[feature] for _, row in self.rows if feature in row]
        baseline_mean = round(mean(values), 6) if values else None
        std_raw = pstdev(values) if len(values) > 1 else 0.0
        z_score = None
        if baseline_mean is not None and std_raw > 0:
            z_score = round((current - baseline_mean) / std_raw, 6)
        return BaselineStat(
            mean=baseline_mean,
            std=round(std_raw, 6),
            n=len(values),
            z_score=z_score,
        )


def build_history_baseline_window(
    fixture: dict[str, Any],
    *,
    enrich_row: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> BaselineWindow:
    raw_observation = fixture.get("observation") or {}
    observed_at = str(raw_observation.get("timestamp") or "")
    deduped: dict[str, dict[str, float]] = {}
    anonymous_rows: list[tuple[str, dict[str, float]]] = []

    for row in fixture.get("history", []):
        timestamp = str(row.get("timestamp") or "")
        if observed_at and timestamp == observed_at:
            continue
        row_values = dict(row)
        if enrich_row is not None:
            try:
                row_values = {**row_values, **enrich_row(row)}
            except (KeyError, TypeError, ValueError):
                pass
        numeric = numeric_observation(row_values)
        if not numeric:
            continue
        if timestamp:
            deduped[timestamp] = numeric
        else:
            anonymous_rows.append(("", numeric))
    return BaselineWindow(rows=[*anonymous_rows, *deduped.items()], observed_at=observed_at)


def numeric_observation(observation: dict[str, Any]) -> dict[str, float]:
    numeric: dict[str, float] = {}
    for key, value in observation.items():
        if key in _NON_SENSOR_FIELDS or isinstance(value, bool) or value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            numeric[key] = number
    return numeric

"""Sensor-window statistics for a detected preventive-intervention candidate."""

from __future__ import annotations

import csv
import statistics
from datetime import datetime, timedelta
from pathlib import Path

from .contracts import DetectedRiskRiseEvent, SensorFeatureStatistic, SourceReference


CNC_SENSOR_UNITS = {
    "air_temperature_k": "K",
    "process_temperature_k": "K",
    "rotational_speed_rpm": "rpm",
    "torque_nm": "N·m",
    "tool_wear_min": "min",
}
REQUIRED_COLUMNS = {"observed_at", "asset_id", *CNC_SENSOR_UNITS}


def _sample_stddev(values: list[float]) -> float:
    return statistics.stdev(values) if len(values) > 1 else 0.0


def analyze_cnc_sensor_windows(
    csv_path: Path,
    event: DetectedRiskRiseEvent,
    *,
    baseline_window_hours: float,
) -> list[SensorFeatureStatistic]:
    baseline_from = event.started_at - timedelta(hours=baseline_window_hours)
    baseline_rows: list[dict[str, str]] = []
    risk_rows: list[dict[str, str]] = []

    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"sensor CSV missing required columns: {', '.join(sorted(missing))}")
        for line_number, row in enumerate(reader, start=2):
            if row.get("asset_id") != event.asset_id:
                continue
            try:
                observed_at = datetime.fromisoformat(row["observed_at"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid observed_at at sensor CSV line {line_number}") from exc
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise ValueError(f"observed_at must include timezone at sensor CSV line {line_number}")
            for feature in CNC_SENSOR_UNITS:
                try:
                    float(row[feature])
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"sensor feature {feature} must be numeric at CSV line {line_number}"
                    ) from exc
            if baseline_from <= observed_at < event.started_at:
                baseline_rows.append(row)
            elif event.started_at <= observed_at <= event.peak_at:
                risk_rows.append(row)

    if not baseline_rows or not risk_rows:
        raise ValueError("both baseline and risk sensor windows must contain observations")

    statistics_by_feature: list[SensorFeatureStatistic] = []
    for feature, unit in CNC_SENSOR_UNITS.items():
        baseline = [float(row[feature]) for row in baseline_rows]
        risk = [float(row[feature]) for row in risk_rows]
        baseline_mean = statistics.fmean(baseline)
        risk_mean = statistics.fmean(risk)
        baseline_stddev = _sample_stddev(baseline)
        statistics_by_feature.append(
            SensorFeatureStatistic(
                feature=feature,
                unit=unit,
                baseline_count=len(baseline),
                risk_count=len(risk),
                baseline_mean=baseline_mean,
                baseline_median=statistics.median(baseline),
                baseline_stddev=baseline_stddev,
                risk_mean=risk_mean,
                risk_median=statistics.median(risk),
                risk_stddev=_sample_stddev(risk),
                change_percent=(
                    ((risk_mean - baseline_mean) / abs(baseline_mean)) * 100
                    if baseline_mean != 0
                    else None
                ),
                baseline_sigma_shift=(
                    (risk_mean - baseline_mean) / baseline_stddev
                    if baseline_stddev != 0
                    else None
                ),
                source_reference=SourceReference(
                    source="canonical/dataset/cnc_sensor_observation.csv",
                    source_field=feature,
                    asset_id=event.asset_id,
                    period_from=baseline_from,
                    period_to=event.peak_at,
                ),
            )
        )
    return statistics_by_feature

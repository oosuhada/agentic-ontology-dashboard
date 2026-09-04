"""Deterministic risk-rise detection over a versioned Prediction Timeline."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .contracts import (
    DetectedRiskRiseEvent,
    PredictionTimelinePoint,
    RiskRiseDetectionPolicy,
)


def load_risk_rise_policy(path: Path) -> RiskRiseDetectionPolicy:
    return RiskRiseDetectionPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def load_prediction_timeline(path: Path) -> list[PredictionTimelinePoint]:
    points: list[PredictionTimelinePoint] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            points.append(
                PredictionTimelinePoint.model_validate(
                    {
                        **{
                            field: row[field]
                            for field in (
                                "prediction_id",
                                "asset_id",
                                "asset_type",
                                "observed_at",
                                "failure_probability",
                                "model_version",
                            )
                        },
                        "top_factors": row.get("top_factors", []),
                    }
                )
            )
        except Exception as exc:
            raise ValueError(f"invalid prediction timeline row at line {line_number}") from exc
    return points


def _hours_between(started_at: datetime, ended_at: datetime) -> float:
    return (ended_at - started_at).total_seconds() / 3600


def detect_risk_rise_events(
    points: Iterable[PredictionTimelinePoint],
    policy: RiskRiseDetectionPolicy,
) -> list[DetectedRiskRiseEvent]:
    """Detect rises beginning at the observation before the first threshold-crossing step."""

    grouped: dict[str, list[PredictionTimelinePoint]] = defaultdict(list)
    for point in points:
        if point.asset_type in policy.eligible_asset_types:
            grouped[point.asset_id].append(point)

    events: list[DetectedRiskRiseEvent] = []
    for asset_id, asset_points in sorted(grouped.items()):
        ordered = sorted(asset_points, key=lambda item: item.observed_at)
        for previous, current in zip(ordered, ordered[1:]):
            if previous.asset_type != current.asset_type:
                raise ValueError(f"asset_type changed within timeline for {asset_id}")
            if previous.model_version != current.model_version:
                raise ValueError(f"model_version changed within adjacent timeline rows for {asset_id}")
            if previous.observed_at == current.observed_at:
                raise ValueError(f"duplicate observed_at within timeline for {asset_id}")

        index = 1
        while index < len(ordered):
            previous = ordered[index - 1]
            current = ordered[index]
            gap_hours = _hours_between(previous.observed_at, current.observed_at)
            step_delta = current.failure_probability - previous.failure_probability
            if (
                gap_hours > policy.maximum_observation_gap_hours
                or step_delta < policy.minimum_step_probability_increase
            ):
                index += 1
                continue

            start_index = index - 1
            peak_index = index
            cursor = index + 1
            terminated_by = "end_of_timeline"
            while cursor < len(ordered):
                prior = ordered[cursor - 1]
                candidate = ordered[cursor]
                candidate_gap = _hours_between(prior.observed_at, candidate.observed_at)
                if candidate_gap > policy.maximum_observation_gap_hours:
                    terminated_by = "gap"
                    break
                if candidate.failure_probability <= prior.failure_probability:
                    terminated_by = "non_increase"
                    break
                peak_index = cursor
                cursor += 1

            baseline = ordered[start_index]
            peak = ordered[peak_index]
            include_terminating_row = terminated_by == "non_increase"
            ended = ordered[cursor] if include_terminating_row else peak
            source_stop = cursor + 1 if include_terminating_row else cursor
            total_delta = peak.failure_probability - baseline.failure_probability
            if total_delta >= policy.minimum_total_probability_increase:
                events.append(
                    DetectedRiskRiseEvent(
                        event_id=f"RISK-RISE#{asset_id}#{baseline.observed_at.isoformat()}",
                        asset_id=asset_id,
                        asset_type=baseline.asset_type,
                        started_at=baseline.observed_at,
                        peak_at=peak.observed_at,
                        ended_at=ended.observed_at,
                        baseline_probability=baseline.failure_probability,
                        peak_probability=peak.failure_probability,
                        probability_delta=total_delta,
                        time_to_peak_hours=_hours_between(baseline.observed_at, peak.observed_at),
                        duration_hours=_hours_between(baseline.observed_at, ended.observed_at),
                        terminated_by=terminated_by,
                        policy_version=policy.policy_version,
                        model_version=baseline.model_version,
                        source_prediction_ids=[
                            item.prediction_id for item in ordered[start_index:source_stop]
                        ],
                    )
                )
            # The pair that ended the run is either non-increasing or outside the
            # allowed gap. The next possible trigger therefore starts at cursor.
            index = cursor + 1

    return events


def rank_events_by_risk_factor(
    events: Iterable[DetectedRiskRiseEvent],
    points: Iterable[PredictionTimelinePoint],
    *,
    feature_prefix: str,
    eligible_asset_types: Iterable[str] | None = None,
) -> list[DetectedRiskRiseEvent]:
    """Rank events whose peak prediction exposes a matching risk-up factor."""

    eligible = set(eligible_asset_types) if eligible_asset_types is not None else None
    point_by_key: dict[tuple[str, datetime], PredictionTimelinePoint] = {}
    for point in points:
        if eligible is not None and point.asset_type not in eligible:
            continue
        key = (point.asset_id, point.observed_at)
        if key in point_by_key:
            raise ValueError(
                "duplicate asset_id and observed_at in prediction points: "
                f"{point.asset_id}, {point.observed_at.isoformat()}"
            )
        point_by_key[key] = point

    ranked: list[tuple[float, float, str, DetectedRiskRiseEvent]] = []
    for event in events:
        peak_key = (event.asset_id, event.peak_at)
        peak = point_by_key.get(peak_key)
        if peak is None:
            raise ValueError(
                "missing peak prediction row for asset and timestamp: "
                f"{event.asset_id}, {event.peak_at.isoformat()}"
            )
        contributions = [
            factor.signed_contribution
            for factor in peak.top_factors
            if factor.feature.startswith(feature_prefix) and factor.direction.value == "risk_up"
        ]
        if contributions:
            ranked.append(
                (
                    event.probability_delta,
                    max(contributions),
                    event.event_id,
                    event,
                )
            )
    return [
        item[3]
        for item in sorted(
            ranked,
            key=lambda item: (-item[0], -item[1], item[2]),
        )
    ]

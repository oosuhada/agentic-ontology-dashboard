from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from experiments.preventive_intervention.cli import DEFAULT_POLICY_PATH, main as cli_main
from experiments.preventive_intervention.contracts import (
    PredictionTimelinePoint,
    RiskRiseDetectionPolicy,
)
from experiments.preventive_intervention.risk_rise import (
    detect_risk_rise_events,
    load_risk_rise_policy,
    rank_events_by_risk_factor,
)
from experiments.preventive_intervention.sensor_analysis import analyze_cnc_sensor_windows


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = (
    ROOT
    / "experiments"
    / "preventive_intervention"
    / "policies"
    / "risk-rise-detection-v1.json"
)


def point(hour: int, probability: float, *, asset_id: str = "CNC-01") -> PredictionTimelinePoint:
    return PredictionTimelinePoint(
        prediction_id=f"{asset_id}#2026-08-01T{hour:02d}:00:00+09:00",
        asset_id=asset_id,
        asset_type="cnc",
        observed_at=f"2026-08-01T{hour:02d}:00:00+09:00",
        failure_probability=probability,
        model_version="independent-logreg-v3.1",
        top_factors=[],
    )


def test_policy_records_the_distribution_basis() -> None:
    policy = load_risk_rise_policy(POLICY_PATH)
    assert policy.minimum_step_probability_increase == pytest.approx(0.191046)
    assert policy.distribution_basis["statistic"] == "positive_adjacent_probability_delta_p90"
    assert policy.policy_scope == "offline_what_if_candidate_detection"
    assert policy.authoritative_for_operational_risk is False
    assert "what_if_candidate_selection" in policy.allowed_uses
    assert "status_grade_assignment" in policy.prohibited_uses
    assert "recommended_action_assignment" in policy.prohibited_uses


def test_policy_rejects_removed_operational_use_prohibition() -> None:
    payload = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    payload["prohibited_uses"].remove("status_grade_assignment")
    with pytest.raises(ValidationError, match="all operational-use prohibitions"):
        RiskRiseDetectionPolicy.model_validate(payload)


def test_detects_threshold_triggered_rise_and_records_non_increase_end() -> None:
    policy = load_risk_rise_policy(POLICY_PATH)
    events = detect_risk_rise_events(
        [point(0, 0.1), point(1, 0.35), point(2, 0.6), point(3, 0.55)],
        policy,
    )
    assert len(events) == 1
    event = events[0]
    assert event.baseline_probability == pytest.approx(0.1)
    assert event.peak_probability == pytest.approx(0.6)
    assert event.probability_delta == pytest.approx(0.5)
    assert event.time_to_peak_hours == pytest.approx(2)
    assert event.duration_hours == pytest.approx(3)
    assert event.terminated_by == "non_increase"
    assert len(event.source_prediction_ids) == 4


def test_gap_terminates_at_peak_and_excludes_the_distant_row() -> None:
    policy = load_risk_rise_policy(POLICY_PATH)
    distant_payload = point(2, 0.05).model_dump(mode="json")
    distant_payload.update(
        {"observed_at": "2026-08-08T02:00:00+09:00", "prediction_id": "distant"}
    )
    distant = PredictionTimelinePoint.model_validate(distant_payload)
    events = detect_risk_rise_events([point(0, 0.1), point(1, 0.4), distant], policy)
    event = events[0]
    assert event.terminated_by == "gap"
    assert event.ended_at == event.peak_at
    assert event.duration_hours == pytest.approx(1)
    assert "distant" not in event.source_prediction_ids


def test_total_threshold_can_exceed_step_threshold_without_losing_valid_run() -> None:
    policy = load_risk_rise_policy(POLICY_PATH).model_copy(
        update={"minimum_step_probability_increase": 0.2, "minimum_total_probability_increase": 0.5}
    )
    events = detect_risk_rise_events(
        [point(0, 0.1), point(1, 0.35), point(2, 0.61), point(3, 0.5)], policy
    )
    assert len(events) == 1
    assert events[0].probability_delta == pytest.approx(0.51)


def test_discarded_short_run_does_not_hide_a_later_valid_event() -> None:
    policy = load_risk_rise_policy(POLICY_PATH).model_copy(
        update={"minimum_step_probability_increase": 0.2, "minimum_total_probability_increase": 0.5}
    )
    events = detect_risk_rise_events(
        [
            point(0, 0.1),
            point(1, 0.35),
            point(2, 0.3),
            point(3, 0.2),
            point(4, 0.45),
            point(5, 0.72),
            point(6, 0.6),
        ],
        policy,
    )
    assert len(events) == 1
    assert events[0].started_at.hour == 3


def test_rejects_model_version_change_within_asset_timeline() -> None:
    policy = load_risk_rise_policy(POLICY_PATH)
    changed = point(1, 0.5).model_copy(update={"model_version": "different-model"})
    with pytest.raises(ValueError, match="model_version changed"):
        detect_risk_rise_events([point(0, 0.1), changed], policy)


def test_ignores_subthreshold_and_non_cnc_changes() -> None:
    policy = load_risk_rise_policy(POLICY_PATH)
    small_change = [point(0, 0.1), point(1, 0.2)]
    compressor = [
        PredictionTimelinePoint.model_validate(
            {
                **json.loads(item.model_dump_json()),
                "asset_id": "CMP-01",
                "asset_type": "compressor",
                "prediction_id": item.prediction_id.replace("CNC-01", "CMP-01"),
            }
        )
        for item in (point(0, 0.1), point(1, 0.8))
    ]
    assert detect_risk_rise_events([*small_change, *compressor], policy) == []


def test_rejects_duplicate_timestamps_for_an_asset() -> None:
    policy = load_risk_rise_policy(POLICY_PATH)
    with pytest.raises(ValueError, match="duplicate observed_at"):
        detect_risk_rise_events([point(0, 0.1), point(0, 0.5)], policy)


def test_ranks_only_events_with_matching_peak_risk_factor() -> None:
    policy = load_risk_rise_policy(POLICY_PATH)
    points = [point(0, 0.1), point(1, 0.5), point(2, 0.4)]
    peak_payload = points[1].model_dump(mode="json")
    peak_payload["top_factors"] = [
        {
            "feature": "tool_wear_min_6h_change",
            "signed_contribution": 2.0,
            "direction": "risk_up",
        }
    ]
    points[1] = PredictionTimelinePoint.model_validate(peak_payload)
    other = [point(4, 0.1, asset_id="CNC-02"), point(5, 0.5, asset_id="CNC-02"), point(6, 0.4, asset_id="CNC-02")]
    all_points = [*points, *other]
    events = detect_risk_rise_events(all_points, policy)
    ranked = rank_events_by_risk_factor(
        events,
        all_points,
        feature_prefix="tool_wear_min",
        eligible_asset_types=policy.eligible_asset_types,
    )
    assert len(events) == 2
    assert ranked == [events[0]]


def test_ranking_does_not_depend_on_prediction_id_timestamp_format() -> None:
    policy = load_risk_rise_policy(POLICY_PATH)
    points = [point(0, 0.1), point(1, 0.5), point(2, 0.4)]
    peak_payload = points[1].model_dump(mode="json")
    peak_payload["prediction_id"] = "source-defined-id-without-iso-timestamp"
    peak_payload["top_factors"] = [
        {
            "feature": "tool_wear_min_6h_change",
            "signed_contribution": 2.0,
            "direction": "risk_up",
        }
    ]
    points[1] = PredictionTimelinePoint.model_validate(peak_payload)

    events = detect_risk_rise_events(points, policy)

    assert rank_events_by_risk_factor(events, points, feature_prefix="tool_wear_min") == events


def test_ranking_rejects_duplicate_asset_timestamp_keys() -> None:
    policy = load_risk_rise_policy(POLICY_PATH)
    points = [point(0, 0.1), point(1, 0.5), point(2, 0.4)]
    events = detect_risk_rise_events(points, policy)

    with pytest.raises(ValueError, match="duplicate asset_id and observed_at"):
        rank_events_by_risk_factor(
            events,
            [*points, points[1].model_copy(update={"prediction_id": "duplicate-id"})],
            feature_prefix="tool_wear_min",
        )


def test_ranking_ignores_duplicate_noneligible_asset_keys() -> None:
    policy = load_risk_rise_policy(POLICY_PATH)
    points = [point(0, 0.1), point(1, 0.5), point(2, 0.4)]
    events = detect_risk_rise_events(points, policy)
    compressor = point(0, 0.1, asset_id="CMP-01").model_copy(update={"asset_type": "compressor"})
    rank_events_by_risk_factor(
        events,
        [*points, compressor, compressor.model_copy(update={"prediction_id": "duplicate"})],
        feature_prefix="tool_wear_min",
        eligible_asset_types=policy.eligible_asset_types,
    )


def test_calculates_baseline_and_risk_sensor_statistics(tmp_path: Path) -> None:
    csv_path = tmp_path / "cnc.csv"
    csv_path.write_text(
        "observed_at,asset_id,air_temperature_k,process_temperature_k,rotational_speed_rpm,torque_nm,tool_wear_min\n"
        "2026-07-31T18:00:00+09:00,CNC-01,299,309,1500,40,10\n"
        "2026-07-31T19:00:00+09:00,CNC-01,301,311,1520,42,20\n"
        "2026-08-01T00:00:00+09:00,CNC-01,302,312,1540,44,30\n"
        "2026-08-01T01:00:00+09:00,CNC-01,304,314,1560,46,50\n",
        encoding="utf-8",
    )
    policy = load_risk_rise_policy(POLICY_PATH)
    event = detect_risk_rise_events(
        [point(0, 0.1), point(1, 0.5), point(2, 0.4)], policy
    )[0]
    result = analyze_cnc_sensor_windows(
        csv_path,
        event,
        baseline_window_hours=policy.baseline_window_hours,
    )
    wear = next(item for item in result if item.feature == "tool_wear_min")
    assert wear.baseline_mean == pytest.approx(15)
    assert wear.risk_mean == pytest.approx(40)
    assert wear.change_percent == pytest.approx(166.6666667)
    assert wear.baseline_sigma_shift is not None


def test_sensor_csv_requires_columns_and_timezone(tmp_path: Path) -> None:
    policy = load_risk_rise_policy(POLICY_PATH)
    event = detect_risk_rise_events([point(0, 0.1), point(1, 0.5), point(2, 0.4)], policy)[0]
    missing = tmp_path / "missing.csv"
    missing.write_text("observed_at,asset_id\n2026-08-01T00:00:00+09:00,CNC-01\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required columns"):
        analyze_cnc_sensor_windows(missing, event, baseline_window_hours=6)

    naive = tmp_path / "naive.csv"
    naive.write_text(
        "observed_at,asset_id,air_temperature_k,process_temperature_k,rotational_speed_rpm,torque_nm,tool_wear_min\n"
        "2026-08-01T00:00:00,CNC-01,299,309,1500,40,10\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must include timezone"):
        analyze_cnc_sensor_windows(naive, event, baseline_window_hours=6)


def test_cli_default_policy_is_cwd_independent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert DEFAULT_POLICY_PATH.is_absolute()
    timeline = tmp_path / "timeline.jsonl"
    timeline.write_text(
        "".join(item.model_dump_json() + "\n" for item in [point(0, 0.1), point(1, 0.5), point(2, 0.4)]),
        encoding="utf-8",
    )
    output = tmp_path / "out.jsonl"
    other_cwd = tmp_path / "other"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    cli_main(["detect", "--timeline", str(timeline), "--output", str(output)])
    assert output.exists()


def test_cli_analyze_reproduces_ranking_and_sensor_statistics(tmp_path: Path) -> None:
    timeline = tmp_path / "timeline.jsonl"
    points = [point(0, 0.1), point(1, 0.5), point(2, 0.4)]
    peak = points[1].model_dump(mode="json")
    peak["top_factors"] = [
        {
            "feature": "tool_wear_min_6h_change",
            "signed_contribution": 2.0,
            "direction": "risk_up",
        }
    ]
    points[1] = PredictionTimelinePoint.model_validate(peak)
    timeline.write_text(
        "".join(item.model_dump_json() + "\n" for item in points),
        encoding="utf-8",
    )
    sensors = tmp_path / "sensors.csv"
    sensors.write_text(
        "observed_at,asset_id,air_temperature_k,process_temperature_k,rotational_speed_rpm,torque_nm,tool_wear_min\n"
        "2026-07-31T18:00:00+09:00,CNC-01,299,309,1500,40,10\n"
        "2026-07-31T19:00:00+09:00,CNC-01,301,311,1520,42,20\n"
        "2026-08-01T00:00:00+09:00,CNC-01,302,312,1540,44,30\n"
        "2026-08-01T01:00:00+09:00,CNC-01,304,314,1560,46,50\n",
        encoding="utf-8",
    )
    output = tmp_path / "analysis.json"

    cli_main(
        [
            "analyze",
            "--timeline",
            str(timeline),
            "--sensors",
            str(sensors),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["detected_event_count"] == 1
    assert payload["matching_candidate_count"] == 1
    assert payload["selected_event"]["asset_id"] == "CNC-01"
    wear = next(item for item in payload["sensor_statistics"] if item["feature"] == "tool_wear_min")
    assert wear["baseline_sigma_shift"] is not None

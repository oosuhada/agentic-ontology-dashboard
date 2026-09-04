"""CLI for reproducible preventive-intervention experiment outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .risk_rise import (
    detect_risk_rise_events,
    load_prediction_timeline,
    load_risk_rise_policy,
    rank_events_by_risk_factor,
)
from .sensor_analysis import analyze_cnc_sensor_windows


DEFAULT_POLICY_PATH = Path(__file__).resolve().parent / "policies" / "risk-rise-detection-v1.json"


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeline", type=Path, required=True)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect = subparsers.add_parser("detect", help="write all detected risk-rise events")
    _common_arguments(detect)
    detect.add_argument("--output", type=Path, required=True)

    analyze = subparsers.add_parser(
        "analyze",
        help="rank tool-wear candidates and reproduce the selected sensor statistics",
    )
    _common_arguments(analyze)
    analyze.add_argument("--sensors", type=Path, required=True)
    analyze.add_argument("--output", type=Path, required=True)
    analyze.add_argument("--feature-prefix", default="tool_wear_min")
    return parser.parse_args(argv)


def _validate_output_path(timeline: Path, output: Path) -> tuple[Path, Path]:
    resolved_timeline = timeline.resolve()
    resolved_output = output.resolve()
    if resolved_timeline == resolved_output:
        raise ValueError("output must not overwrite the source Prediction Timeline")
    return resolved_timeline, resolved_output


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    timeline, output = _validate_output_path(args.timeline, args.output)
    if args.command == "analyze" and args.sensors.resolve() == output:
        raise ValueError("output must not overwrite the source sensor CSV")
    policy = load_risk_rise_policy(args.policy)
    points = load_prediction_timeline(timeline)
    events = detect_risk_rise_events(points, policy)

    if args.command == "detect":
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            "".join(
                json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"
                for event in events
            ),
            encoding="utf-8",
        )
        print(f"generated {len(events)} risk-rise events at {output}")
        return

    ranked = rank_events_by_risk_factor(
        events,
        points,
        feature_prefix=args.feature_prefix,
        eligible_asset_types=policy.eligible_asset_types,
    )
    if not ranked:
        raise ValueError(f"no risk-up candidates matched feature prefix {args.feature_prefix!r}")
    selected = ranked[0]
    sensor_statistics = analyze_cnc_sensor_windows(
        args.sensors.resolve(),
        selected,
        baseline_window_hours=policy.baseline_window_hours,
    )
    _write_json(
        output,
        {
            "policy_version": policy.policy_version,
            "detected_event_count": len(events),
            "matching_candidate_count": len(ranked),
            "selected_event": selected.model_dump(mode="json"),
            "sensor_statistics": [item.model_dump(mode="json") for item in sensor_statistics],
        },
    )
    print(f"generated ranked candidate analysis at {output}")


if __name__ == "__main__":
    main()

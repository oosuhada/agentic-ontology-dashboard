from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pytest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "gen_data_layer2_observation"
FIXTURE_ONLY_SOURCE_KIND = "fixture_only_gen_data_layer2_log"


def normalize_gen_data_layer2_rows(
    rows: Iterable[dict[str, Any]],
    *,
    feature_mapping: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Fixture-only normalizer for documenting Generator Observation handoff.

    This test helper intentionally lives outside systems/backend production code.
    AssetDetailViewModel consumers must read Generator-produced
    Observation/Feature series contracts, not raw gen_data Layer files.
    """

    mapping = feature_mapping or {}
    grouped: dict[tuple[str, str], dict[str, Any]] = {}

    for source_index, row in enumerate(rows, start=1):
        asset_id, sensor_key = _parse_node_id(_required_text(row, "node_id"))
        observed_at = _normalize_timestamp(_required_text(row, "source_timestamp"))
        feature_key = mapping.get(sensor_key, sensor_key)
        observation = grouped.setdefault(
            (asset_id, observed_at),
            {
                "asset_id": asset_id,
                "observed_at": observed_at,
                "measurements": {},
                "quality": {},
                "source": {
                    "source_kind": FIXTURE_ONLY_SOURCE_KIND,
                    "node_ids": [],
                    "source_row_numbers": [],
                    "server_timestamps": [],
                },
            },
        )
        observation["measurements"][feature_key] = _number_or_none(row.get("value"))
        observation["quality"][feature_key] = {
            "quality_status": _quality_status(row.get("status_code")),
            "source_status_code": row.get("status_code"),
            "reason": row.get("reason"),
        }
        observation["source"]["node_ids"].append(row["node_id"])
        observation["source"]["source_row_numbers"].append(source_index)
        server_timestamp = row.get("server_timestamp")
        if server_timestamp is not None and str(server_timestamp).strip():
            observation["source"]["server_timestamps"].append(
                _normalize_timestamp(str(server_timestamp))
            )

    return sorted(grouped.values(), key=lambda item: (item["asset_id"], item["observed_at"]))


def _parse_node_id(node_id: str) -> tuple[str, str]:
    asset_id, separator, sensor_key = node_id.rpartition(".")
    if not separator or not asset_id or not sensor_key:
        raise ValueError("node_id must be formatted as '{asset_id}.{sensor_key}'")
    return asset_id, sensor_key


def _required_text(row: dict[str, Any], field: str) -> str:
    value = row.get(field)
    if value is None or str(value).strip() == "":
        raise ValueError(f"{field} is required")
    return str(value).strip()


def _normalize_timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _number_or_none(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    return float(value)


def _quality_status(status_code: Any) -> str:
    normalized = str(status_code or "").strip().lower()
    if normalized == "good":
        return "good"
    if normalized == "bad":
        return "bad"
    return "unknown"


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_layer2_rows_are_pivoted_to_observation_shape() -> None:
    rows = _read_jsonl(FIXTURE_ROOT / "sample_log.jsonl")
    expected = json.loads((FIXTURE_ROOT / "expected_observations.json").read_text())

    observations = normalize_gen_data_layer2_rows(
        rows,
        feature_mapping={"rpm": "rotational_speed_rpm"},
    )

    assert observations == expected


def test_bad_null_sensor_value_is_preserved_as_unavailable_measurement() -> None:
    rows = _read_jsonl(FIXTURE_ROOT / "sample_log.jsonl")

    observation = normalize_gen_data_layer2_rows(
        rows,
        feature_mapping={"rpm": "rotational_speed_rpm"},
    )[0]

    assert observation["measurements"]["rotational_speed_rpm"] is None
    assert observation["quality"]["rotational_speed_rpm"] == {
        "quality_status": "bad",
        "source_status_code": "Bad",
        "reason": "sensor_timeout",
    }


def test_source_timestamp_not_server_timestamp_defines_observed_at() -> None:
    rows = [
        {
            "node_id": "CNC-S01-L01-01.torque_nm",
            "source_timestamp": "2026-08-20T01:00:00Z",
            "server_timestamp": "2026-08-20T01:30:00Z",
            "value": 42.5,
            "status_code": "Good",
        }
    ]

    observation = normalize_gen_data_layer2_rows(rows)[0]

    assert observation["observed_at"] == "2026-08-20T01:00:00Z"
    assert observation["source"]["server_timestamps"] == ["2026-08-20T01:30:00Z"]


def test_node_id_must_include_asset_and_sensor_key() -> None:
    with pytest.raises(ValueError, match="node_id"):
        normalize_gen_data_layer2_rows(
            [
                {
                    "node_id": "torque_nm",
                    "source_timestamp": "2026-08-20T01:00:00Z",
                    "value": 42.5,
                    "status_code": "Good",
                }
            ]
        )


def test_unknown_status_code_stays_unknown_quality() -> None:
    observation = normalize_gen_data_layer2_rows(
        [
            {
                "node_id": "CNC-S01-L01-01.torque_nm",
                "source_timestamp": "2026-08-20T01:00:00Z",
                "value": 42.5,
                "status_code": "Stale",
            }
        ]
    )[0]

    assert observation["quality"]["torque_nm"]["quality_status"] == "unknown"

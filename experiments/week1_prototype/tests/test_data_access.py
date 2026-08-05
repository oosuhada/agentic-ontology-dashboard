from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from data_access import (
    load_asset_master,
    load_prediction_timeline,
    resolve_canonical_root,
)


def _build_minimal_package(root: Path) -> Path:
    dataset = root / "canonical" / "dataset"
    outputs = root / "canonical" / "model_outputs"
    dataset.mkdir(parents=True)
    outputs.mkdir(parents=True)

    pd.DataFrame(
        [
            {
                "asset_id": "CNC-01",
                "asset_type": "cnc",
                "site_id": "S01",
                "cell_id": "S01-L01",
            }
        ]
    ).to_csv(dataset / "asset_master.csv", index=False)
    (outputs / "prediction_snapshot.jsonl").write_text(
        json.dumps(
            {
                "prediction_id": "CNC-01#1",
                "asset_id": "CNC-01",
                "asset_type": "cnc",
                "observed_at": "2026-08-01T00:00:00+09:00",
                "failure_probability": 0.2,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (outputs / "prediction_timeline.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "prediction_id": "CNC-01#1",
                        "asset_id": "CNC-01",
                        "asset_type": "cnc",
                        "observed_at": "2026-08-01T00:00:00+09:00",
                        "failure_probability": 0.2,
                        "status": "normal",
                    }
                ),
                json.dumps(
                    {
                        "prediction_id": "OTHER#1",
                        "asset_id": "OTHER",
                        "asset_type": "cnc",
                        "observed_at": "2026-08-01T00:00:00+09:00",
                        "failure_probability": 0.9,
                        "status": "critical",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return root


def test_resolve_and_read_minimal_package(tmp_path: Path) -> None:
    root = _build_minimal_package(tmp_path / "canonical-v3.1")
    resolved = resolve_canonical_root(root)
    assets = load_asset_master(resolved)

    assert resolved == root.resolve()
    assert assets["asset_id"].tolist() == ["CNC-01"]


def test_timeline_reader_filters_asset_without_loading_other_rows(tmp_path: Path) -> None:
    root = _build_minimal_package(tmp_path / "canonical-v3.1")
    timeline = load_prediction_timeline(root, "CNC-01")

    assert timeline["asset_id"].tolist() == ["CNC-01"]
    assert timeline["failure_probability"].tolist() == [0.2]


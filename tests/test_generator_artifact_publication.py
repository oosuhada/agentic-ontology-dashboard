from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from systems.generator import entrypoint


def test_compressor_publication_returns_published_artifact(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "compressor_sensor_observation.csv"
    truth = tmp_path / "compressor_failure_truth.csv"
    telemetry = pd.DataFrame(
        {
            "observed_at": ["2026-08-08T00:00:00Z"],
            "asset_id": ["CMP-1"],
            "site_id": ["S01"],
            "operating_state": ["running"],
            "voltage_raw": [170.0],
            "rotation_raw": [440.0],
            "pressure_raw": [100.0],
            "vibration_raw": [40.0],
            "relative_vibration_z": [0.0],
        }
    )
    failures = pd.DataFrame({"asset_id": ["CMP-1"], "failure_occurred_at": ["2026-08-09T00:00:00Z"]})
    telemetry.to_csv(source, index=False)
    failures.to_csv(truth, index=False)
    feature_schema = {
        "schema_version": entrypoint.FEATURE_SCHEMA_VERSION,
        "features": ["voltage_raw_current"],
        "feature_engineering": {
            "expected_cadence_minutes": 10.0,
            "runtime_context": {
                "recent_history_rows_required": 35,
                "history_order": "strictly_ascending_before_current_observation",
                "new_asset_policy": "calibrate_baseline_before_inference",
            },
        },
    }
    training = SimpleNamespace(
        selected_model="random_forest",
        model={"model": "fixture"},
        threshold_curve=[{"threshold": 0.2, "precision": 0.5, "recall": 0.5}],
        feature_schema=feature_schema,
        training_config={"selected_threshold": 0.2},
        metrics={"regression_sanity": {"average_precision": 0.5}},
    )
    published = tmp_path / "published-artifact"

    monkeypatch.setenv("MODEL_ARTIFACT_URI", str(tmp_path / "artifacts"))
    monkeypatch.setenv("COMPRESSOR_OBSERVATION_URI", str(source))
    monkeypatch.setenv("COMPRESSOR_FAILURE_TRUTH_URI", str(truth))
    monkeypatch.setattr(entrypoint, "PATHS", SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setattr(entrypoint, "train_compressor_model", lambda *_args, **_kwargs: training)

    def fake_publish_model_artifact(**kwargs):
        assert kwargs["model_id"] == "compressor-failure-risk"
        assert kwargs["compatibility"]["observation_family"] == "compressor"
        assert set(kwargs["extra_files"]) == {"threshold_curve"}
        assert all(Path(path).exists() for path in kwargs["extra_files"].values())
        assert kwargs["label_schema"]["label_schema_version"] == (
            "compressor-failure-within-horizon-v1"
        )
        assert kwargs["history_requirement"]["minimum_history_rows"] == 36
        assert kwargs["history_requirement"]["observation_family"] == "compressor"
        return published

    monkeypatch.setattr(entrypoint, "publish_model_artifact", fake_publish_model_artifact)

    artifact = entrypoint.publish_training_artifact()

    assert artifact == published


def _write_gate_artifact(
    root: Path,
    *,
    family: str,
    regression_ap: float,
    regression_recall: float,
    deployment_ap: float,
    deployment_precision: float,
    deployment_recall: float,
    deployment_prevalence: float,
    precision_lift: float,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        '{"compatibility":{"observation_family":"' + family + '"}}\n',
        encoding="utf-8",
    )
    (root / "metrics.json").write_text(
        """
{
  "feature_table": {"prevalence": 0.025},
  "regression_sanity": {"average_precision": %s, "recall": %s},
  "deployment_realism_test": {
    "average_precision": %s,
    "precision": %s,
    "recall": %s,
    "prevalence": %s,
    "precision_lift_over_prevalence": %s
  }
}
"""
        % (
            regression_ap,
            regression_recall,
            deployment_ap,
            deployment_precision,
            deployment_recall,
            deployment_prevalence,
            precision_lift,
        ),
        encoding="utf-8",
    )
    return root


def test_compressor_promotion_gate_blocks_low_precision_candidate(tmp_path: Path) -> None:
    artifact = _write_gate_artifact(
        tmp_path / "bad-compressor",
        family="compressor",
        regression_ap=0.165756,
        regression_recall=0.645833,
        deployment_ap=0.127337,
        deployment_precision=0.011811,
        deployment_recall=1.0,
        deployment_prevalence=0.003586,
        precision_lift=3.293963,
    )

    with pytest.raises(RuntimeError, match="Compressor Model Artifact promotion blocked"):
        entrypoint.assert_promotion_sanity(artifact)


def test_compressor_promotion_gate_accepts_stable_candidate(tmp_path: Path) -> None:
    artifact = _write_gate_artifact(
        tmp_path / "stable-compressor",
        family="compressor",
        regression_ap=0.185693,
        regression_recall=0.25625,
        deployment_ap=0.509353,
        deployment_precision=0.135338,
        deployment_recall=0.75,
        deployment_prevalence=0.011696,
        precision_lift=11.57,
    )

    entrypoint.assert_promotion_sanity(artifact)

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from app.diagnosis.materialization import ProductResultMaterializationService
from scripts import prepare_local_realtime_models
from systems.generator import entrypoint


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_legacy_publication_is_pinned_to_frozen_recipe(
    monkeypatch,
    tmp_path: Path,
) -> None:
    canonical = tmp_path / "canonical"
    dataset = canonical / "dataset"
    truth = canonical / "evaluation_truth"
    outputs = canonical / "model_outputs"
    dataset.mkdir(parents=True)
    truth.mkdir(parents=True)
    outputs.mkdir(parents=True)

    canonical_hashes: dict[str, str] = {}
    truth_hashes: dict[str, str] = {}
    for family in ("compressor", "cnc"):
        observation = dataset / f"{family}_sensor_observation.csv"
        failure_truth = truth / f"{family}_failure_truth.csv"
        observation.write_text("observation\n", encoding="utf-8")
        failure_truth.write_text("truth\n", encoding="utf-8")
        canonical_hashes[observation.name] = _sha256(observation)
        truth_hashes[failure_truth.name] = _sha256(failure_truth)

    metrics_file = outputs / "model_metrics.json"
    snapshot_file = outputs / "prediction_snapshot.jsonl"
    metrics_file.write_text(
        json.dumps({"compressor": {}, "cnc": {}}), encoding="utf-8"
    )
    snapshot_file.write_text("{}\n", encoding="utf-8")
    contract = {
        "model_version": "independent-logreg-v3.1",
        "dataset_version": "canonical-ai4i-physics-v3.1",
        "canonical_input_sha256": canonical_hashes,
        "evaluation_truth_input_sha256": truth_hashes,
        "output_sha256": {
            metrics_file.name: _sha256(metrics_file),
            snapshot_file.name: _sha256(snapshot_file),
        },
    }
    (outputs / "model_contract.json").write_text(
        json.dumps(contract), encoding="utf-8"
    )

    monkeypatch.setattr(entrypoint, "PATHS", SimpleNamespace(data_dir=dataset))
    monkeypatch.setenv("MODEL_ARTIFACT_URI", str(tmp_path / "artifacts"))
    reconstruction = SimpleNamespace(
        model={"frozen": True},
        feature_columns=["sensor_current"],
        baseline_stats={"ASSET-1": {"sensor": {"mean": 0.0, "std": 1.0}}},
        rows=10,
        positive_rows=2,
        reference_prediction_count=1,
        max_reference_probability_error=0.0,
    )
    monkeypatch.setattr(
        entrypoint,
        "reconstruct_legacy_v31_model",
        lambda **_kwargs: reconstruction,
    )
    published_kwargs: list[dict] = []

    def fake_publish(**kwargs):
        published_kwargs.append(kwargs)
        return tmp_path / "published" / kwargs["model_id"]

    monkeypatch.setattr(entrypoint, "publish_model_artifact", fake_publish)

    result = entrypoint.publish_legacy_v31_artifacts()

    assert set(result) == {"compressor", "cnc"}
    assert {item["model_version"] for item in published_kwargs} == {
        "independent-logreg-v3.1"
    }
    assert {item["training_config"]["selected_model"] for item in published_kwargs} == {
        "logistic_regression"
    }
    assert {item["training_config"]["selected_threshold"] for item in published_kwargs} == {
        0.5
    }
    assert all(
        item["training_config"]["severity_thresholds"]
        == {"attention": 0.2, "warning": 0.45, "critical": 0.75}
        for item in published_kwargs
    )


def test_local_model_preparation_selects_pinned_legacy_not_newest_candidate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def candidates(_store: Path, model_id: str) -> list[dict]:
        return [
            {
                "model_id": model_id,
                "model_version": "newer-but-unapproved-model",
                "created_at": "2026-09-02T00:00:00Z",
                "_artifact_dir": str(tmp_path / "newer"),
            },
            {
                "model_id": model_id,
                "model_version": "independent-logreg-v3.1",
                "created_at": "2026-08-10T00:00:00Z",
                "training_config": {
                    "training_config_version": (
                        "independent-logreg-v3.1-frozen-reconstruction-v1"
                    ),
                    "selected_threshold": 0.5,
                },
                "provenance": {
                    "reconstruction": "deterministic_from_frozen_v3.1_recipe"
                },
                "_artifact_dir": str(tmp_path / "legacy"),
            },
        ]

    monkeypatch.setattr(
        prepare_local_realtime_models,
        "_manifest_candidates",
        candidates,
    )
    monkeypatch.setattr(
        "systems.generator.model.publisher.validate_model_artifact",
        lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        prepare_local_realtime_models,
        "_publish",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("pinned artifact must not trigger reconstruction")
        ),
    )

    def fake_update(_self, model_set, validate_artifacts=True):
        assert validate_artifacts is True
        return model_set

    monkeypatch.setattr(
        "systems.generator.app.runtime_pipeline.active_model_set_service."
        "ActiveModelSetService.update_active_model_set",
        fake_update,
    )

    result = prepare_local_realtime_models.prepare(
        gen_data_root=tmp_path / "gen_data",
        models_store=tmp_path / "models",
    )

    assert result["model_set_version"] == "3.1.0-independent-logreg-pinned"
    assert {
        item["model_version"] for item in result["models"].values()
    } == {"independent-logreg-v3.1"}


def test_backend_severity_policy_preserves_v3_1_risk_bands() -> None:
    ProductResultMaterializationService._threshold_policy.cache_clear()

    assert ProductResultMaterializationService._generator_policy_decision(
        score=0.19,
        selected_threshold=0.5,
        criticality=None,
    )["status"] == "normal"
    assert ProductResultMaterializationService._generator_policy_decision(
        score=0.20,
        selected_threshold=0.5,
        criticality=None,
    )["status"] == "attention"
    assert ProductResultMaterializationService._generator_policy_decision(
        score=0.45,
        selected_threshold=0.5,
        criticality=None,
    )["status"] == "warning"
    assert ProductResultMaterializationService._generator_policy_decision(
        score=0.75,
        selected_threshold=0.5,
        criticality=None,
    )["status"] == "critical"

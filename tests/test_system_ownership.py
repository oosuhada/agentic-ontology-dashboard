from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from jsonschema import Draft202012Validator

from systems.backend.app.diagnosis.contracts import load_fixture
from systems.backend.app.diagnosis.evidence import build_evidence_package, build_product_result_artifact
from systems.backend.app.diagnosis.predictor import ArtifactPredictor, HeuristicPredictor, configured_predictor
from systems.generator.model import train_and_publish_model


ROOT = Path(__file__).resolve().parents[1]


def _write_ai4i_fixture(path: Path, rows: int = 120) -> None:
    payload = []
    for index in range(rows):
        failure = 1 if index % 5 == 0 else 0
        payload.append(
            {
                "UDI": index + 1,
                "Product ID": f"M{index:05d}",
                "Type": "M" if index % 3 else "H",
                "Air temperature [K]": 298.0 + (index % 5) * 0.2,
                "Process temperature [K]": 307.5 + (index % 7) * 0.3,
                "Rotational speed [rpm]": 1450 + (index % 11) * 12 - failure * 120,
                "Torque [Nm]": 42.0 + (index % 9) + failure * 18.0,
                "Tool wear [min]": 40 + (index % 30) * 5 + failure * 75,
                "Machine failure": failure,
                "TWF": 0,
                "HDF": 0,
                "PWF": 0,
                "OSF": 0,
                "RNF": 0,
            }
        )
    pd.DataFrame(payload).to_csv(path, index=False)


def test_generator_publishes_model_artifact_and_backend_consumes_it(tmp_path: Path) -> None:
    csv_path = tmp_path / "ai4i.csv"
    _write_ai4i_fixture(csv_path)
    artifact_root = tmp_path / "artifacts"

    artifact_path = train_and_publish_model(
        csv_path=csv_path,
        artifact_uri=artifact_root,
        dataset_version="test-ai4i-v1",
    )

    manifest = json.loads((artifact_path / "manifest.json").read_text(encoding="utf-8"))
    schema = json.loads((ROOT / "contracts" / "schemas" / "model-artifact.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(manifest)) == []
    assert manifest["artifact_type"] == "predictive_maintenance_model"
    assert manifest["dataset_version"] == "test-ai4i-v1"
    assert manifest["compatibility"]["runtime"] == "app.diagnosis"

    predictor = ArtifactPredictor(artifact_path)
    fixture = load_fixture("data/fixtures/GS-002-tool-wear-warning.json")
    normal_fixture = load_fixture("data/fixtures/GS-001-normal-stable.json")
    prediction = predictor.predict(fixture)
    normal_prediction = predictor.predict(normal_fixture)
    result = build_product_result_artifact(fixture, predictor=predictor)
    evidence = build_evidence_package(fixture, predictor=predictor)

    assert prediction.model_artifact is not None
    assert result["prediction_task"] == "binary_failure_within_horizon"
    assert result["provenance"]["source_type"] == "product_runtime_inference"
    assert result["provenance"]["model_artifact"]["model_version"] == manifest["model_version"]
    assert prediction.factors
    assert normal_prediction.factors
    assert [(item.feature, item.score) for item in prediction.factors[:3]] != [
        (item.feature, item.score)
        for item in normal_prediction.factors[:3]
    ]
    assert result["top_factors"]
    assert result["top_factors"][0]["explanation_method"] == "model_artifact_local_proxy_attribution"
    assert result["evidence_payload"]["recommended_actions"][0]["basis"]
    assert evidence["model"]["mode"] == "trained"
    assert evidence["model"]["artifact"]["dataset_version"] == "test-ai4i-v1"


def test_model_positive_probability_cannot_remain_operationally_normal(tmp_path: Path) -> None:
    csv_path = tmp_path / "ai4i.csv"
    _write_ai4i_fixture(csv_path)
    artifact_path = train_and_publish_model(
        csv_path=csv_path,
        artifact_uri=tmp_path / "artifacts",
        dataset_version="threshold-contract-v1",
    )
    predictor = ArtifactPredictor(artifact_path)
    predictor.manifest.setdefault("training_config", {})["selected_threshold"] = 0.12

    class FixedProbabilityModel:
        def predict_proba(self, frame):
            return np.asarray([[0.82, 0.18] for _ in range(len(frame))], dtype=float)

    predictor.model = FixedProbabilityModel()
    fixture = load_fixture("data/fixtures/GS-001-normal-stable.json")
    fixture["equipment"]["criticality"] = "medium"

    prediction = predictor.predict(fixture)

    assert prediction.predicted_failure_type == "failure_risk"
    assert prediction.risk_band in {"attention", "warning", "critical"}
    assert prediction.recommended_decision != "continue_monitoring"


def test_week2_fixture_fallback_remains_backend_owned(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_ARTIFACT_URI", raising=False)
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK", "1")
    fixture = load_fixture("data/fixtures/GS-002-tool-wear-warning.json")
    predictor = HeuristicPredictor()
    result = build_product_result_artifact(fixture, predictor=predictor)

    assert result["schema_version"] == "result-artifact-v1.0"
    assert result["prediction_task"] == "binary_failure_within_horizon"
    assert result["provenance"]["source_type"] == "product_runtime_inference"
    assert result["provenance"]["canonical_source_mutated"] is False


@pytest.mark.parametrize("app_env", ["local", "demo", "test"])
def test_heuristic_fallback_defaults_on_only_for_local_demo_test(monkeypatch, app_env: str) -> None:
    monkeypatch.delenv("MODEL_ARTIFACT_URI", raising=False)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK", raising=False)
    monkeypatch.setenv("APP_ENV", app_env)

    assert isinstance(configured_predictor(), HeuristicPredictor)


@pytest.mark.parametrize("app_env", ["development", "dev", "deploy", "staging", "production"])
def test_heuristic_fallback_defaults_off_for_nonlocal_environments(monkeypatch, app_env: str) -> None:
    monkeypatch.delenv("MODEL_ARTIFACT_URI", raising=False)
    monkeypatch.delenv("ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK", raising=False)
    monkeypatch.setenv("APP_ENV", app_env)

    with pytest.raises(RuntimeError, match="MODEL_ARTIFACT_URI is required"):
        configured_predictor()


def test_explicit_heuristic_fallback_override_is_honored(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_ARTIFACT_URI", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK", "1")

    assert isinstance(configured_predictor(), HeuristicPredictor)


def test_explicit_heuristic_fallback_disable_is_honored(monkeypatch) -> None:
    monkeypatch.delenv("MODEL_ARTIFACT_URI", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_ALLOW_HEURISTIC_MODEL_FALLBACK", "0")

    with pytest.raises(RuntimeError, match="MODEL_ARTIFACT_URI is required"):
        configured_predictor()


def test_legacy_ml_namespace_is_compatibility_adapter() -> None:
    from ontology_dashboard_manufacturing_ml import HeuristicPredictor as LegacyPredictor
    from ontology_dashboard_manufacturing_ml import build_evidence_package as legacy_evidence

    assert LegacyPredictor.__module__ == "systems.backend.app.diagnosis.predictor"
    assert legacy_evidence.__module__ == "systems.backend.app.diagnosis.evidence"

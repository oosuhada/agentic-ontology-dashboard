from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from systems.generator.app.runtime_pipeline.active_model_set_service import (
    ActiveModelSetService,
)
from systems.generator.app.runtime_pipeline.pipeline_schema import (
    ActiveModelConfig,
    ActiveModelSet,
)
from systems.generator.app.runtime_pipeline.prediction_service import PredictionService


def test_explicit_cnc_artifact_id_is_not_rewritten(tmp_path: Path) -> None:
    prediction = PredictionService(models_store_dir=tmp_path)
    active_sets = ActiveModelSetService(models_store_dir=tmp_path)

    assert prediction.resolve_model_id("lightgbm") == "pdm-lightgbm"
    assert prediction.resolve_model_id("cnc-failure-risk") == "cnc-failure-risk"
    assert active_sets._resolve_model_id("cnc-failure-risk") == "cnc-failure-risk"


def test_active_model_set_accepts_safe_explicit_artifact_id(tmp_path: Path) -> None:
    service = ActiveModelSetService(models_store_dir=tmp_path)
    model_set = ActiveModelSet(
        model_set_id="cnc-runtime",
        model_set_version="1.0.0",
        updated_at=datetime.now(timezone.utc),
        models={
            "cnc-failure-risk": ActiveModelConfig(
                model_version="cnc-random-forest-v3-test",
                required=True,
            )
        },
    )

    updated = service.update_active_model_set(model_set, validate_artifacts=False)

    assert updated.models["cnc-failure-risk"].required is True
    assert service.load_active_model_set().models == updated.models

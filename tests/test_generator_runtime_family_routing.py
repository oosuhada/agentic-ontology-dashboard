from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

pytest.importorskip("lightgbm")

from systems.generator.app.runtime_pipeline.pipeline_exception import (
    PipelineRuntimeFeatureFailedError,
)
from systems.generator.app.runtime_pipeline.pipeline_service import PipelineService


def artifact_for(family: str | None):
    compatibility = {} if family is None else {"observation_family": family}
    return SimpleNamespace(
        model_id=f"{family or 'generic'}-model",
        manifest={"compatibility": compatibility},
    )


def test_mixed_runtime_observations_are_routed_by_artifact_family() -> None:
    observations = pd.DataFrame(
        [
            {"asset_id": "CNC-01", "asset_type": "cnc", "tool_wear_min": 10.0},
            {"asset_id": "CMP-01", "asset_type": "compressor", "pressure_raw": 0.2},
        ]
    )

    cnc = PipelineService._filter_observations_for_artifact(
        observations,
        artifact_for("cnc"),
    )
    compressor = PipelineService._filter_observations_for_artifact(
        observations,
        artifact_for("compressor"),
    )

    assert cnc["asset_id"].tolist() == ["CNC-01"]
    assert compressor["asset_id"].tolist() == ["CMP-01"]


def test_generic_artifact_keeps_all_runtime_observations() -> None:
    observations = pd.DataFrame(
        [
            {"asset_id": "CNC-01", "asset_type": "cnc"},
            {"asset_id": "CMP-01", "asset_type": "compressor"},
        ]
    )

    routed = PipelineService._filter_observations_for_artifact(
        observations,
        artifact_for(None),
    )

    assert routed.equals(observations)


def test_family_artifact_requires_asset_type_at_runtime_boundary() -> None:
    observations = pd.DataFrame([{"asset_id": "CNC-01", "tool_wear_min": 10.0}])

    with pytest.raises(PipelineRuntimeFeatureFailedError, match="asset_type"):
        PipelineService._filter_observations_for_artifact(
            observations,
            artifact_for("cnc"),
        )

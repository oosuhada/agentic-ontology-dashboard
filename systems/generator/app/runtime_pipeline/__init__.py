"""Generator Runtime Pipeline package."""

from importlib import import_module

from systems.generator.app.runtime_pipeline.pipeline_schema import (
    ArtifactReference,
    InternalModelPredictionResult,
    ModelPredictionResult,
    PipelineError,
    PipelineQueueItem,
    PipelineRunState,
    PredictionDeliveryEventState,
    PredictionOutboxItem,
    PredictionResultBatchPayload,
    StageState,
)
from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineBaseError


_LAZY_EXPORTS = {
    "PipelineQueue": ("systems.generator.app.runtime_pipeline.pipeline_queue", "PipelineQueue"),
    "PipelineStateManager": (
        "systems.generator.app.runtime_pipeline.pipeline_state",
        "PipelineStateManager",
    ),
    "PipelineRepository": (
        "systems.generator.app.runtime_pipeline.pipeline_repository",
        "PipelineRepository",
    ),
    "RuntimeFeatureService": (
        "systems.generator.app.runtime_pipeline.runtime_feature_service",
        "RuntimeFeatureService",
    ),
    "PredictionService": (
        "systems.generator.app.runtime_pipeline.prediction_service",
        "PredictionService",
    ),
    "PredictionBatchService": (
        "systems.generator.app.runtime_pipeline.prediction_batch_service",
        "PredictionBatchService",
    ),
    "PredictionDeliveryService": (
        "systems.generator.app.runtime_pipeline.prediction_delivery_service",
        "PredictionDeliveryService",
    ),
    "PredictionDeliveryWorker": (
        "systems.generator.app.runtime_pipeline.prediction_delivery_worker",
        "PredictionDeliveryWorker",
    ),
    "PipelineService": (
        "systems.generator.app.runtime_pipeline.pipeline_service",
        "PipelineService",
    ),
    "PipelineWorker": (
        "systems.generator.app.runtime_pipeline.pipeline_worker",
        "PipelineWorker",
    ),
    "PipelineManager": (
        "systems.generator.app.runtime_pipeline.pipeline_manager",
        "PipelineManager",
    ),
    "runtime_pipeline_router": (
        "systems.generator.app.runtime_pipeline.pipeline_router",
        "router",
    ),
}


def __getattr__(name: str):
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = _LAZY_EXPORTS[name]
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value

__all__ = [
    "ArtifactReference",
    "InternalModelPredictionResult",
    "ModelPredictionResult",
    "PipelineError",
    "PipelineQueueItem",
    "PipelineRunState",
    "PredictionDeliveryEventState",
    "PredictionOutboxItem",
    "PredictionResultBatchPayload",
    "StageState",
    "PipelineBaseError",
    "PipelineQueue",
    "PipelineStateManager",
    "PipelineRepository",
    "RuntimeFeatureService",
    "PredictionService",
    "PredictionBatchService",
    "PredictionDeliveryService",
    "PredictionDeliveryWorker",
    "PipelineService",
    "PipelineWorker",
    "PipelineManager",
    "runtime_pipeline_router",
]

"""Preprocessing domain module for Generator."""

from __future__ import annotations

from systems.generator.app.preprocessing.preprocessing_schema import (
    PreprocessingRequest,
    PreprocessingResponse,
    PreprocessingResultPayload,
    PreprocessingPlanResponse,
    PreprocessingStructureResponse,
    PreprocessingColumnsResponse,
    ErrorEnvelope,
    ErrorEnvelopeBody,
)
from systems.generator.app.preprocessing.preprocessing_exception import (
    PreprocessingError,
    DatasetNotFoundError,
    DatasetContractError,
    PreprocessingRoleError,
    PreprocessingPlanningError,
    PreprocessingPlanValidationError,
    PreprocessingPlanPublishError,
    PreprocessingConflictError,
)
from systems.generator.app.preprocessing.preprocessing_repository import PreprocessingRepository
from systems.generator.app.preprocessing.preprocessing_planner import PreprocessingPlanner
from systems.generator.app.preprocessing.preprocessing_profiler import (
    build_family_registry,
    load_family_registry,
)
from systems.generator.app.preprocessing.preprocessing_service import (
    PreprocessingService,
    preprocess_with_plan,
    load_all_sources,
    get_last_plans,
)
from systems.generator.app.preprocessing.preprocessing_router import router as preprocessing_router

__all__ = [
    "PreprocessingRequest",
    "PreprocessingResponse",
    "PreprocessingResultPayload",
    "PreprocessingPlanResponse",
    "PreprocessingStructureResponse",
    "PreprocessingColumnsResponse",
    "ErrorEnvelope",
    "ErrorEnvelopeBody",
    "PreprocessingError",
    "DatasetNotFoundError",
    "DatasetContractError",
    "PreprocessingRoleError",
    "PreprocessingPlanningError",
    "PreprocessingPlanValidationError",
    "PreprocessingPlanPublishError",
    "PreprocessingConflictError",
    "PreprocessingRepository",
    "PreprocessingPlanner",
    "PreprocessingService",
    "preprocess_with_plan",
    "load_all_sources",
    "get_last_plans",
    "build_family_registry",
    "load_family_registry",
    "preprocessing_router",
]

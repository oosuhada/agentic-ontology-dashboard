"""FastAPI router for Generator Training domain API."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Request

from systems.generator.app.training.training_schema import TrainingRequest, TrainingResponse
from systems.generator.app.training.training_service import TrainingService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["training"])


def get_training_service() -> TrainingService:
    """Dependency provider for TrainingService."""
    return TrainingService()


@router.post("/train", response_model=TrainingResponse)
def post_train(
    req: TrainingRequest,
    request: Request,
    service: TrainingService = Depends(get_training_service),
) -> TrainingResponse:
    """Synchronous endpoint to train all registered models on verified Feature Dataset Bundle."""
    req_id = getattr(request.state, "request_id", None)
    logger.info(f"[TrainingAPI] Received POST /train for dataset={req.dataset_id}, feature_ver={req.feature_dataset_version}")
    return service.train_models(req=req, target_model=None, request_id=req_id)


@router.post("/train/{base_model}", response_model=TrainingResponse)
def post_train_single(
    base_model: str,
    req: TrainingRequest,
    request: Request,
    service: TrainingService = Depends(get_training_service),
) -> TrainingResponse:
    """Synchronous endpoint to train a specific base model on verified Feature Dataset Bundle."""
    req_id = getattr(request.state, "request_id", None)
    logger.info(
        f"[TrainingAPI] Received POST /train/{base_model} for dataset={req.dataset_id}, "
        f"feature_ver={req.feature_dataset_version}"
    )
    return service.train_models(req=req, target_model=base_model, request_id=req_id)

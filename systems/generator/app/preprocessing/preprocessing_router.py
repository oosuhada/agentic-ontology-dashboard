"""FastAPI Router for Generator Preprocessing domain."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Request
from systems.generator.app.preprocessing.preprocessing_schema import (
    PreprocessingRequest,
    PreprocessingResponse,
)
from systems.generator.app.preprocessing.preprocessing_service import PreprocessingService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["preprocessing"])


def get_preprocessing_service() -> PreprocessingService:
    return PreprocessingService()


@router.post("/preprocessing", response_model=PreprocessingResponse)
def post_preprocessing(
    req: PreprocessingRequest,
    request: Request,
    service: PreprocessingService = Depends(get_preprocessing_service),
) -> PreprocessingResponse:
    """Execute dataset preprocessing planning, validation, and versioned publishing."""
    req_id = getattr(request.state, "request_id", None)
    return service.run_preprocessing(req, request_id=req_id)

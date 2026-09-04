"""FastAPI router for Feature domain endpoints."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Request, Depends

from systems.generator.app.feature.feature_schema import (
    FeatureRequest,
    FeatureResponse,
)
from systems.generator.app.feature.feature_service import FeatureService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feature"])


def get_feature_service() -> FeatureService:
    """Dependency provider for FeatureService."""
    return FeatureService()


@router.post(
    "/feature",
    response_model=FeatureResponse,
    summary="Observation/Failure 데이터셋, Preprocessing Plan 및 Schema를 기반으로 Feature Dataset Bundle 발행",
    description=(
        "지정된 Preprocessing Plan(ID/version)과 Feature/Label Schema를 소비하여 Feature 및 Label을 계산하고 "
        "5개 필수 파일로 구성된 불변 Feature Dataset Bundle을 원자적으로 발행합니다."
    ),
)
def post_feature(
    request: FeatureRequest,
    http_request: Request,
    service: FeatureService = Depends(get_feature_service),
) -> FeatureResponse:
    """Synchronous endpoint executing CPU/IO-bound feature generation in threadpool."""
    req_id = getattr(http_request.state, "request_id", None) or http_request.headers.get("X-Request-ID")
    logger.info(f"[FeatureRouter] Received POST /feature request (req_id={req_id})")
    return service.execute_feature(request, request_id=req_id)

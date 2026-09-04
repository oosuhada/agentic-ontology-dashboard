"""FastAPI router for Generator Protocol Extraction domain."""

from __future__ import annotations

import logging
import uuid
from typing import Optional, Union
from fastapi import APIRouter, Depends, Header, Request, status

from systems.generator.app.extraction.extraction_exception import (
    ExtractionRequestInvalidError,
    ExtractionSourceNotFoundError,
)
from systems.generator.app.extraction.extraction_manager import (
    ExtractionManager,
    get_extraction_manager,
)
from systems.generator.app.extraction.extraction_schema import (
    ExtractionManagerStatus,
    ExtractionRequest,
    ExtractionResponse,
    ExtractionRuntimeHandoff,
    GenDataExtractionRequest,
    GenDataExtractionResponse,
)
from systems.generator.app.extraction.extraction_service import ExtractionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["extraction"])
_extraction_service: Optional[ExtractionService] = None


def get_extraction_service() -> ExtractionService:
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = ExtractionService()
    return _extraction_service


def set_extraction_service(service: Optional[ExtractionService]) -> None:
    global _extraction_service
    _extraction_service = service


@router.get(
    "/extraction/status",
    response_model=ExtractionManagerStatus,
    status_code=status.HTTP_200_OK,
    summary="Get background worker and extraction manager status",
    description="Returns the current operational status of the Extraction Manager, Background Worker, and all tracked sources.",
)
def get_extraction_status(
    manager: ExtractionManager = Depends(get_extraction_manager),
) -> ExtractionManagerStatus:
    """Return extraction manager and background worker status."""
    return manager.get_status()


@router.post(
    "/extraction",
    response_model=Union[GenDataExtractionResponse, ExtractionResponse],
    status_code=status.HTTP_200_OK,
    summary="Execute gen_data protocol extraction into Canonical Observation Dataset",
    description=(
        "Executes on-demand incremental extraction for gen_data sensor streams or legacy protocol logs, "
        "enforces single-writer locks, and publishes versioned Canonical Observation Artifacts."
    ),
)
async def extract_protocol_records(
    request_body: Union[GenDataExtractionRequest, ExtractionRequest],
    request: Request,
    x_request_id: Optional[str] = Header(None, alias="X-Request-ID"),
    service: ExtractionService = Depends(get_extraction_service),
    manager: ExtractionManager = Depends(get_extraction_manager),
) -> Union[GenDataExtractionResponse, ExtractionResponse]:
    """Endpoint executing extraction on demand."""
    req_id = x_request_id or getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")

    if isinstance(request_body, GenDataExtractionRequest):
        logger.info(
            f"[ExtractionAPI] Received gen_data extraction request: request_id={req_id}, "
            f"source_uri={request_body.source_uri}, mapping={request_body.mapping_id}/{request_body.mapping_version}"
        )
        return await manager.execute_request(request_body, request_id=req_id)

    logger.info(
        f"[ExtractionAPI] Received legacy protocol extraction request: request_id={request_body.request_id}, "
        f"dataset={request_body.dataset_id}/{request_body.dataset_version}, "
        f"mapping={request_body.mapping_id}/{request_body.mapping_version}"
    )
    return service.execute_extraction(request_body)

@router.get(
    "/extraction/handoffs/{handoff_id}",
    response_model=ExtractionRuntimeHandoff,
    status_code=status.HTTP_200_OK,
    summary="Get extraction runtime handoff record by ID",
    description="Returns the status and delivery details of a specific Extraction -> Runtime Prediction handoff record.",
)
def get_extraction_handoff(
    handoff_id: str,
    manager: ExtractionManager = Depends(get_extraction_manager),
) -> ExtractionRuntimeHandoff:
    """Retrieve handoff record by handoff_id."""
    clean_id = handoff_id.strip()
    if not clean_id or len(clean_id) != 64:
        raise ExtractionRequestInvalidError(
            f"Invalid handoff_id format: '{handoff_id}'. Must be a 64-character hex string."
        )
    handoff, _ = manager.handoff_repo.find_handoff_by_id(clean_id)
    if handoff is None:
        raise ExtractionSourceNotFoundError(
            f"Handoff record with ID '{clean_id}' not found."
        )
    return handoff


@router.post(
    "/extraction/handoffs/{handoff_id}/retry",
    response_model=ExtractionRuntimeHandoff,
    status_code=status.HTTP_200_OK,
    summary="Retry a failed or pending extraction runtime handoff record",
    description="Explicitly attempts to re-deliver a pending, retry_wait, or retry_exhausted handoff record to the Runtime Prediction Queue.",
)
def retry_extraction_handoff(
    handoff_id: str,
    manager: ExtractionManager = Depends(get_extraction_manager),
) -> ExtractionRuntimeHandoff:
    """Retry handoff delivery."""
    clean_id = handoff_id.strip()
    if not clean_id or len(clean_id) != 64:
        raise ExtractionRequestInvalidError(
            f"Invalid handoff_id format: '{handoff_id}'. Must be a 64-character hex string."
        )
    handoff, _ = manager.handoff_repo.find_handoff_by_id(clean_id)
    if handoff is None:
        raise ExtractionSourceNotFoundError(
            f"Handoff record with ID '{clean_id}' not found."
        )
    if handoff.status == "blocked":
        raise ExtractionRequestInvalidError(
            f"Cannot retry blocked handoff '{clean_id}'. Verify and fix dataset integrity first."
        )
    return manager.handoff_service.process_handoff(handoff)

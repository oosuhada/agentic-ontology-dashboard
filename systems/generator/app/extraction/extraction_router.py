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
    ExtractionReplayRequest,
    ExtractionRequest,
    ExtractionResponse,
    ExtractionRuntimeHandoff,
    GenDataExtractionRequest,
    GenDataExtractionResponse,
)
from systems.generator.app.extraction.extraction_service import ExtractionService
from systems.generator.app.extraction.mapping_repository import MappingRepository

logger = logging.getLogger(__name__)

router = APIRouter(tags=["extraction"])
_extraction_service: Optional[ExtractionService] = None
_mapping_repository: Optional[MappingRepository] = None


def get_extraction_service() -> ExtractionService:
    global _extraction_service
    if _extraction_service is None:
        _extraction_service = ExtractionService()
    return _extraction_service


def set_extraction_service(service: Optional[ExtractionService]) -> None:
    global _extraction_service
    _extraction_service = service


def get_mapping_repository() -> MappingRepository:
    global _mapping_repository
    if _mapping_repository is None:
        _mapping_repository = MappingRepository()
    return _mapping_repository


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


@router.get("/extraction/mappings")
def list_mapping_versions(
    repository: MappingRepository = Depends(get_mapping_repository),
):
    return {"items": repository.list_mappings()}


@router.get("/extraction/mappings/{mapping_id}/versions/{mapping_version}")
def get_mapping_version(
    mapping_id: str,
    mapping_version: str,
    repository: MappingRepository = Depends(get_mapping_repository),
):
    data, _path = repository.load_mapping(mapping_id, mapping_version)
    return {
        "mapping_id": mapping_id,
        "mapping_version": mapping_version,
        "status": data.get("status"),
        "mapping": data,
    }


@router.post(
    "/extraction/replays",
    response_model=ExtractionResponse,
    summary="Replay an approved Mapping into a new immutable Dataset version",
)
def replay_extraction(
    request_body: ExtractionReplayRequest,
    service: ExtractionService = Depends(get_extraction_service),
) -> ExtractionResponse:
    """Replay from source offset zero using a fresh run_id and Dataset version.

    Existing Dataset versions are never edited.  The normal Extraction service
    still performs source checksum, approved Mapping, single-writer and
    provenance validation.
    """
    return service.execute_extraction(request_body.extraction)


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

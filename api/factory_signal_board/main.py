from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .contracts import DecisionRequest, FollowUpRequest, LayoutRequest, NoteRequest, ReportRequest
from .service import EventNotFound, FactorySignalService

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def get_service() -> FactorySignalService:
    database_path = os.getenv("FACTORY_SIGNAL_DB")
    return FactorySignalService(ROOT, database_path=database_path)


app = FastAPI(
    title="Factory Signal Board API",
    version="0.1.0",
    description="Grounded predictive-maintenance evidence, reports, governed layouts, and demo workflow",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.exception_handler(EventNotFound)
async def not_found_handler(_: Request, exc: EventNotFound) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "not_found", "message": f"resource not found: {exc.args[0]}"}},
    )


@app.exception_handler(ValueError)
async def validation_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "contract_validation_failed", "message": str(exc)}},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "factory-signal-board", "mode": "offline-capable"}


@app.get("/api/equipment")
def list_equipment(service: FactorySignalService = Depends(get_service)):
    return {"items": service.list_equipment()}


@app.get("/api/equipment/{equipment_id}")
def get_equipment(equipment_id: str, service: FactorySignalService = Depends(get_service)):
    return service.equipment(equipment_id)


@app.get("/api/events")
def list_events(service: FactorySignalService = Depends(get_service)):
    return {"items": service.list_events()}


@app.get("/api/events/{event_id}")
def get_event(event_id: str, service: FactorySignalService = Depends(get_service)):
    return service.event(event_id)


@app.get("/api/events/{event_id}/evidence")
def get_evidence(event_id: str, service: FactorySignalService = Depends(get_service)):
    return service.evidence(event_id)


@app.post("/api/events/{event_id}/report")
def create_report(event_id: str, request: ReportRequest, service: FactorySignalService = Depends(get_service)):
    report, trace = service.report(event_id, request)
    return {"report": report.model_dump(mode="json"), "trace": trace}


@app.post("/api/events/{event_id}/layout")
def create_layout(event_id: str, request: LayoutRequest, service: FactorySignalService = Depends(get_service)):
    layout, trace = service.layout(event_id, request)
    return {"layout": layout.model_dump(mode="json"), "trace": trace}


@app.post("/api/events/{event_id}/decision")
def record_decision(event_id: str, request: DecisionRequest, service: FactorySignalService = Depends(get_service)):
    return service.decide(event_id, request)


@app.post("/api/events/{event_id}/notes")
def add_note(event_id: str, request: NoteRequest, service: FactorySignalService = Depends(get_service)):
    return service.note(event_id, request)


@app.post("/api/events/{event_id}/follow-up")
def follow_up(event_id: str, request: FollowUpRequest, service: FactorySignalService = Depends(get_service)):
    return service.follow_up(event_id, request).model_dump(mode="json")


@app.get("/api/events/{event_id}/activity")
def event_activity(event_id: str, service: FactorySignalService = Depends(get_service)):
    service.event(event_id)
    return service.repository.event_activity(event_id)


@app.post("/api/demo/reset")
def reset_demo(service: FactorySignalService = Depends(get_service)):
    return service.reset()


@app.get("/api/openapi-contract")
def openapi_contract() -> dict:
    return app.openapi()

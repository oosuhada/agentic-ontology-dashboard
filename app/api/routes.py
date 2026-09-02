from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import FastForwardOverlayRequest, StartRunRequest
from app.runtime.manager import RuntimeManager


router = APIRouter()


def _manager(request: Request) -> RuntimeManager:
    return request.app.state.runtime_manager


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return HTTPException(status_code=404, detail=str(exc).strip("'"))
    if isinstance(exc, (ValueError, RuntimeError)):
        return HTTPException(status_code=409 if "active" in str(exc) else 400, detail=str(exc))
    return HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


@router.post("/api/runs", status_code=201)
def start_run(payload: StartRunRequest, request: Request):
    try:
        return _manager(request).start_run(**payload.model_dump())
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/api/runs/{run_id}/stop")
def stop_run(run_id: str, request: Request):
    try:
        return _manager(request).stop(run_id)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/api/runs/{run_id}/tick")
def tick_run(run_id: str, request: Request):
    try:
        return _manager(request).tick(run_id)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/api/runs/{run_id}/runtime-overlay/fast-forward")
def fast_forward_runtime_overlay(
    run_id: str,
    payload: FastForwardOverlayRequest,
    request: Request,
):
    try:
        return _manager(request).fast_forward_overlay(
            run_id,
            equipment_id=payload.equipment_id,
            target_generated_rows=payload.target_generated_rows,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/api/runs/{run_id}")
def run_status(run_id: str, request: Request):
    try:
        return _manager(request).status(run_id)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/api/runs/{run_id}/outputs")
def run_outputs(run_id: str, request: Request):
    try:
        return _manager(request).outputs(run_id)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/api/runs/{run_id}/equipment/{equipment_id}")
def equipment_state(run_id: str, equipment_id: str, request: Request):
    try:
        return _manager(request).equipment_state(run_id, equipment_id)
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/health/live")
def health_live():
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready(request: Request):
    ready = _manager(request).ready()
    if not ready:
        raise HTTPException(status_code=503, detail="runtime dependencies are not ready")
    return {"status": "ready"}

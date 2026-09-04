"""Generator domain canonical FastAPI application."""

from __future__ import annotations

import logging
import uuid
from typing import Any
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from contextlib import asynccontextmanager

from systems.generator.app.preprocessing.preprocessing_router import router as preprocessing_router
from systems.generator.app.preprocessing.preprocessing_exception import PreprocessingError
from systems.generator.app.preprocessing.preprocessing_schema import ErrorEnvelope, ErrorEnvelopeBody
from systems.generator.app.feature.feature_router import router as feature_router
from systems.generator.app.feature.feature_exception import FeatureError
from systems.generator.app.training.training_router import router as training_router
from systems.generator.app.training.training_exception import TrainingError
from systems.generator.model.publisher import ModelPublishError
from systems.generator.app.training_compat.training_compat_router import router as training_compat_router
from systems.generator.app.training_compat.training_lifecycle import lifespan as training_lifespan
from systems.generator.app.extraction.extraction_router import router as extraction_router
from systems.generator.app.extraction.extraction_exception import ExtractionError
from systems.generator.app.extraction.extraction_manager import ExtractionManager
from systems.generator.app.runtime_pipeline.pipeline_router import router as runtime_pipeline_router
from systems.generator.app.runtime_pipeline.pipeline_exception import PipelineBaseError
from systems.generator.app.runtime_pipeline.pipeline_manager import PipelineManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def combined_lifespan(app: FastAPI):
    """Combined lifespan coordinating training compat tasks, extraction worker, and runtime pipeline worker."""
    extraction_mgr = ExtractionManager.get_instance()
    if extraction_mgr.enabled:
        await extraction_mgr.start()
    app.state.extraction_manager = extraction_mgr

    async with training_lifespan(app):
        pipeline_mgr = PipelineManager.get_instance()
        pipeline_mgr.start()
        app.state.pipeline_manager = pipeline_mgr
        try:
            yield
        finally:
            pipeline_mgr.stop()
            if extraction_mgr.running:
                await extraction_mgr.stop()



def _build_error_response(
    status_code: int,
    code: str,
    message: str,
    path: str,
    request_id: str,
    details: list[Any] | None = None,
) -> JSONResponse:
    error_id = f"err-{uuid.uuid4().hex[:8]}"
    envelope = ErrorEnvelope(
        error=ErrorEnvelopeBody(
            code=code,
            message=message,
            path=path,
            request_id=request_id,
            error_id=error_id,
            details=details or [],
        )
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump())


def register_middleware(app: FastAPI) -> None:
    """Register HTTP middleware."""
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or f"req-{uuid.uuid4().hex[:12]}"
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


def register_exception_handlers(app: FastAPI) -> None:
    """Register standard domain and framework exception handlers."""
    @app.exception_handler(ExtractionError)
    async def extraction_error_handler(request: Request, exc: ExtractionError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")
        logger.warning(f"[ExtractionAPI] ExtractionError: {exc.code} - {exc.message}")
        return _build_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            path=request.url.path,
            request_id=req_id,
            details=exc.details,
        )

    @app.exception_handler(PreprocessingError)
    async def preprocessing_error_handler(request: Request, exc: PreprocessingError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")
        logger.warning(f"[PreprocessingAPI] PreprocessingError: {exc.code} - {exc.message}")
        return _build_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            path=request.url.path,
            request_id=req_id,
            details=exc.details,
        )

    @app.exception_handler(FeatureError)
    async def feature_error_handler(request: Request, exc: FeatureError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")
        logger.warning(f"[FeatureAPI] FeatureError: {exc.code} - {exc.message}")
        return _build_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            path=request.url.path,
            request_id=req_id,
            details=exc.details,
        )

    @app.exception_handler(TrainingError)
    @app.exception_handler(ModelPublishError)
    async def training_error_handler(request: Request, exc: TrainingError | ModelPublishError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")
        code = getattr(exc, "code", "TRAINING_ERROR")
        msg = getattr(exc, "message", str(exc))
        status_c = getattr(exc, "status_code", 500)
        details = getattr(exc, "details", [])
        logger.warning(f"[TrainingAPI] {type(exc).__name__}: {code} - {msg}")
        return _build_error_response(
            status_code=status_c,
            code=code,
            message=msg,
            path=request.url.path,
            request_id=req_id,
            details=details,
        )

    @app.exception_handler(PipelineBaseError)
    async def pipeline_error_handler(request: Request, exc: PipelineBaseError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")
        logger.warning(f"[RuntimePipelineAPI] PipelineBaseError: {exc.code} - {exc.message}")
        return _build_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            path=request.url.path,
            request_id=req_id,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")
        details = []
        for err in exc.errors():
            details.append({
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            })
        logger.warning(f"[GeneratorAPI] Request validation error: {details}")
        # Return ErrorEnvelope for domain routes, standard detail for training compat if needed
        if request.url.path.startswith(("/extraction", "/preprocessing", "/feature", "/train", "/runtime-pipeline", "/internal/runtime-pipeline")):
            return _build_error_response(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="REQUEST_VALIDATION_ERROR",
                message="요청 형식이 올바르지 않습니다.",
                path=request.url.path,
                request_id=req_id,
                details=details,
            )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": details},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        req_id = getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")
        logger.info(f"[GeneratorAPI] HTTP Exception {exc.status_code} on {request.url.path}: {exc.detail}")
        if request.url.path.startswith(("/extraction", "/preprocessing", "/feature", "/train", "/runtime-pipeline", "/internal/runtime-pipeline")):
            return _build_error_response(
                status_code=exc.status_code,
                code=f"HTTP_{exc.status_code}",
                message=str(exc.detail) if exc.detail else "HTTP 요청 처리 중 오류가 발생했습니다.",
                path=request.url.path,
                request_id=req_id,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", f"req-{uuid.uuid4().hex[:12]}")
        logger.exception(f"[GeneratorAPI] Unhandled error on {request.url.path}: {exc}")
        if request.url.path.startswith(("/extraction", "/preprocessing", "/feature", "/train", "/runtime-pipeline", "/internal/runtime-pipeline")):
            return _build_error_response(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="INTERNAL_SERVER_ERROR",
                message="서버 내부 오류가 발생했습니다.",
                path=request.url.path,
                request_id=req_id,
            )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "서버 내부 오류가 발생했습니다."},
        )


def register_routers(app: FastAPI) -> None:
    """Register all domain and compatibility routers."""
    @app.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok", "system": "generator"}

    app.include_router(extraction_router)
    app.include_router(preprocessing_router)
    app.include_router(feature_router)
    app.include_router(training_router)
    app.include_router(runtime_pipeline_router)
    app.include_router(training_compat_router)



def create_app() -> FastAPI:
    """App factory creating fully configured Generator domain FastAPI application."""
    application = FastAPI(
        title="Generator Domain API",
        description="Generator control-plane, dataset preprocessing, and model training daemon",
        version="1.0.0",
        lifespan=combined_lifespan,
    )
    register_middleware(application)
    register_exception_handlers(application)
    register_routers(application)
    return application



app = create_app()

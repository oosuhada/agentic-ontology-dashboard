"""Minimal FastAPI application factory for the working product runtime."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.common.runtime_settings import allowed_origin_regex, allowed_origins, project_root
from app.infra.db.pool import close_pools
from app.infra.observability.runtime_validation import validate_runtime_environment


ROOT = project_root()


@asynccontextmanager
async def application_lifespan(_: FastAPI):
    try:
        yield
    finally:
        close_pools()


def create_app() -> FastAPI:
    validate_runtime_environment(ROOT)
    application = FastAPI(
        title="Ontology Dashboard API",
        version="0.8.0",
        description="Predictive-maintenance Operations backend.",
        lifespan=application_lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_origin_regex=allowed_origin_regex()
        or (
            r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
            if os.getenv("APP_ENV", "development").lower() in {"development", "demo", "test"}
            else None
        ),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-CSRF-Token",
            "Idempotency-Key",
        ],
        expose_headers=[
            "Content-Disposition",
            "X-Export-Checkpoint-ID",
            "X-Content-SHA256",
            "X-Snapshot-SHA256",
        ],
    )
    application.middleware("http")(_security_headers)
    return application


async def _security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith(("/api/auth", "/api/admin", "/api/exports")):
        response.headers["Cache-Control"] = "no-store"
    return response


__all__ = ["create_app"]

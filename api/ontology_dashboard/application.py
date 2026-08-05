"""FastAPI application factory for Ontology Dashboard."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from .postgresql_pool import close_pools
from .settings import allowed_origins, validate_runtime_environment

ROOT = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def application_lifespan(_: FastAPI):
    try:
        yield
    finally:
        close_pools()


def create_app() -> FastAPI:
    """Create a configured application without registering feature routers."""
    validate_runtime_environment(ROOT)
    app = FastAPI(
        title="Ontology Dashboard API",
        version="0.7.0",
        description=(
            "Domain-neutral ontology dashboard foundation with governed domain packs, "
            "workspace-scoped objects, role templates, actions, planning, export and audit."
        ),
        lifespan=application_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(),
        allow_origin_regex=(
            r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
            if os.getenv("APP_ENV", "development").lower() in {"development", "demo", "test"}
            else None
        ),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
        expose_headers=[
            "Content-Disposition",
            "X-Export-Checkpoint-ID",
            "X-Content-SHA256",
            "X-Snapshot-SHA256",
        ],
    )
    app.middleware("http")(_security_headers)
    return app


async def _security_headers(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path in {"/docs", "/redoc"}:
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https://fastapi.tiangolo.com; "
            "connect-src 'self'; frame-ancestors 'none'"
        )
    else:
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    if request.url.path.startswith(("/api/auth", "/api/admin", "/api/exports")):
        response.headers["Cache-Control"] = "no-store"
    if os.getenv("APP_ENV", "development").lower() == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

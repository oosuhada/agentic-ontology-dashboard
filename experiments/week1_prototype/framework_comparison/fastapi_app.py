"""FastAPI implementation of the shared health contract."""

from __future__ import annotations

from fastapi import FastAPI

from .contracts import HEALTH_PAYLOAD, HealthResponse


app = FastAPI(
    title="Week 1 FastAPI health experiment",
    version="1.0.0",
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(**HEALTH_PAYLOAD)


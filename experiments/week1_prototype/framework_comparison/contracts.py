"""Shared health contract used by both framework implementations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


HEALTH_PAYLOAD = {
    "status": "ok",
    "service": "ontology-dashboard-week1",
    "mode": "framework-comparison",
}


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    mode: str


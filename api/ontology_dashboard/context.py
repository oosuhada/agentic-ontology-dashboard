"""Compatibility context providers for the manufacturing demo boundary."""

from __future__ import annotations

import os
from typing import Any

import httpx

from ontology_dashboard_manufacturing_ml.evidence import FixtureContextProvider


class Project3HttpContextProvider:
    provider_name = "project3_http"

    def __init__(self, base_url: str | None = None, timeout_seconds: float = 5.0) -> None:
        self.base_url = (base_url or os.getenv("PROJECT3_API_URL", "")).rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_context(self, equipment_id: str, failure_type: str) -> dict[str, Any]:
        if not self.base_url:
            raise RuntimeError("PROJECT3_API_URL is not configured")
        response = httpx.get(
            f"{self.base_url}/api/maintenance-context",
            params={"equipment_id": equipment_id, "failure_type": failure_type},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        required = {"version", "source_refs", "checklist", "recommended_actions"}
        missing = sorted(required - set(payload))
        if missing:
            raise ValueError(f"Project 3 context response is missing fields: {missing}")
        return {
            "provider": self.provider_name,
            "version": str(payload["version"]),
            "source_type": str(payload.get("source_type", "project3_evidence")),
            "source_refs": list(payload["source_refs"]),
            "checklist": list(payload["checklist"]),
            "recommended_actions": list(payload["recommended_actions"]),
        }


class ResilientContextProvider:
    provider_name = "resilient"

    def __init__(self, primary: Project3HttpContextProvider | None = None) -> None:
        self.primary = primary or Project3HttpContextProvider()
        self.fallback = FixtureContextProvider()

    def get_context(self, equipment_id: str, failure_type: str) -> dict[str, Any]:
        try:
            return self.primary.get_context(equipment_id, failure_type)
        except Exception as exc:
            payload = self.fallback.get_context(equipment_id, failure_type)
            payload["provider"] = "fixture_fallback"
            payload["version"] = f"{payload['version']}|fallback:{type(exc).__name__}"
            return payload

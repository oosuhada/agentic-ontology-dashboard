"""HTTP adapter for the Generator-owned runtime prediction enqueue boundary."""

from __future__ import annotations

import os
from typing import Any

import httpx


_DUPLICATE_CODES = {
    "PIPELINE_DUPLICATE_INPUT",
    "PIPELINE_SOURCE_ALREADY_REGISTERED",
    "PIPELINE_SOURCE_ALREADY_PROCESSED",
}


class GeneratorRuntimePipelineUnavailable(RuntimeError):
    """Raised when an Overlay snapshot cannot be handed to Generator."""


class GeneratorRuntimePipelineClient:
    """Submit immutable observation snapshots without importing Generator code."""

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.endpoint = (
            os.getenv("ONTOLOGY_DASHBOARD_GENERATOR_RUNTIME_ENQUEUE_URL", "")
            if endpoint is None
            else endpoint
        ).strip()
        self.timeout_seconds = timeout_seconds
        self.client = client

    @staticmethod
    def _error_code(payload: Any) -> str | None:
        if not isinstance(payload, dict):
            return None
        detail = payload.get("detail")
        if isinstance(detail, dict) and detail.get("code"):
            return str(detail["code"])
        error = payload.get("error")
        if isinstance(error, dict) and error.get("code"):
            return str(error["code"])
        if payload.get("code"):
            return str(payload["code"])
        return None

    def enqueue(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.endpoint:
            raise GeneratorRuntimePipelineUnavailable(
                "ONTOLOGY_DASHBOARD_GENERATOR_RUNTIME_ENQUEUE_URL is required "
                "to deliver Runtime Overlay snapshots"
            )
        try:
            if self.client is None:
                response = httpx.post(
                    self.endpoint,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            else:
                response = self.client.post(self.endpoint, json=payload)
        except httpx.HTTPError as exc:
            raise GeneratorRuntimePipelineUnavailable(
                f"Generator runtime enqueue request failed: {exc}"
            ) from exc

        try:
            body = response.json()
        except ValueError:
            body = None
        code = self._error_code(body)
        if response.status_code == 409 and code in _DUPLICATE_CODES:
            return {
                "job_id": str(payload["job_id"]),
                "status": "reused",
                "duplicate_code": code,
            }
        if response.is_error:
            raise GeneratorRuntimePipelineUnavailable(
                "Generator runtime enqueue rejected the Overlay snapshot: "
                f"status={response.status_code} code={code or 'unknown'}"
            )
        if not isinstance(body, dict):
            raise GeneratorRuntimePipelineUnavailable(
                "Generator runtime enqueue returned a non-object response"
            )
        return body


__all__ = [
    "GeneratorRuntimePipelineClient",
    "GeneratorRuntimePipelineUnavailable",
]

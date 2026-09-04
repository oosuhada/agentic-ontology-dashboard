"""Resilient typed HTTP client for the Project 3 graph/RAG service boundary."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from .models import (
    Project3AgentRun,
    Project3GraphProjectionRequest,
    Project3GraphProjectionResponse,
    Project3GraphSchema,
    Project3Health,
    Project3NodeSearch,
    Project3Query,
    Project3RagResult,
    Project3Readiness,
    Project3Subgraph,
)

TModel = TypeVar("TModel", bound=BaseModel)


class Project3Error(RuntimeError):
    """Base integration error with a stable machine-readable category."""

    def __init__(self, message: str, *, code: str, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class Project3Unavailable(Project3Error):
    def __init__(self, message: str = "Project 3 service is unavailable") -> None:
        super().__init__(message, code="project3_unavailable", retryable=True)


class Project3ContractError(Project3Error):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="project3_contract_error", retryable=False)


@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float | None = None


class Project3Client:
    """Typed synchronous client with bounded retries and a small circuit breaker.

    Project 2 owns authentication, tenant/project/workspace authorization and object identity.
    Project 3 owns graph ETL, validated Text-to-Cypher, graph traversal and RAG execution.
    This client never exposes a method for submitting arbitrary Cypher.
    """

    def __init__(
        self,
        *,
        base_url: str,
        project_mapping: dict[str, str] | None = None,
        timeout_seconds: float = 4.0,
        max_retries: int = 1,
        circuit_failure_threshold: int = 3,
        circuit_reset_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.project_mapping = dict(project_mapping or {})
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.circuit_failure_threshold = max(1, circuit_failure_threshold)
        self.circuit_reset_seconds = max(1.0, circuit_reset_seconds)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "ontology-dashboard-project3-client/1"},
        )
        self._circuit = _CircuitState()
        self._circuit_lock = Lock()

    @classmethod
    def from_environment(cls) -> "Project3Client":
        return cls(
            base_url=os.getenv("ONTOLOGY_DASHBOARD_PROJECT3_URL", "http://127.0.0.1:8001"),
            project_mapping=parse_project_mapping(
                os.getenv(
                    "ONTOLOGY_DASHBOARD_PROJECT3_PROJECT_MAP",
                    '{"manufacturing-demo-project":"cip-dmd"}',
                )
            ),
            timeout_seconds=float(os.getenv("ONTOLOGY_DASHBOARD_PROJECT3_TIMEOUT_SECONDS", "4")),
            max_retries=int(os.getenv("ONTOLOGY_DASHBOARD_PROJECT3_MAX_RETRIES", "1")),
            circuit_failure_threshold=int(
                os.getenv("ONTOLOGY_DASHBOARD_PROJECT3_CIRCUIT_FAILURES", "3")
            ),
            circuit_reset_seconds=float(
                os.getenv("ONTOLOGY_DASHBOARD_PROJECT3_CIRCUIT_RESET_SECONDS", "30")
            ),
        )

    def close(self) -> None:
        self._client.close()

    def map_project_id(self, project_id: str) -> str:
        normalized = project_id.strip()
        if not normalized:
            raise Project3ContractError("project_id must not be blank")
        return self.project_mapping.get(normalized, normalized)

    def health(self, *, project_id: str | None = None) -> Project3Health:
        started = time.perf_counter()
        mapped = self.map_project_id(project_id) if project_id else None
        try:
            payload = self._request_json("GET", "/api/v1/health")
            payload["available"] = True
            payload["mapped_project_id"] = mapped
            payload["latency_ms"] = int((time.perf_counter() - started) * 1000)
            return Project3Health.model_validate(payload)
        except Project3Error as error:
            return Project3Health(
                status="unavailable",
                available=False,
                mapped_project_id=mapped,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=str(error),
            )

    def readiness(self, project_id: str) -> Project3Readiness:
        mapped = self.map_project_id(project_id)
        return self._model(
            Project3Readiness,
            "GET",
            f"/api/v1/projects/{mapped}/readiness",
        )

    def graph_schema(self, project_id: str) -> Project3GraphSchema:
        mapped = self.map_project_id(project_id)
        return self._model(
            Project3GraphSchema,
            "GET",
            "/api/v1/graph/schema",
            params={"project_id": mapped},
        )

    def graph_search(
        self,
        project_id: str,
        *,
        label: str,
        query: str,
        limit: int = 12,
        dataset_version_id: str | None = None,
    ) -> Project3NodeSearch:
        mapped = self.map_project_id(project_id)
        return self._model(
            Project3NodeSearch,
            "GET",
            "/api/v1/graph/search",
            params={
                "project_id": mapped,
                "label": label,
                "q": query,
                "limit": min(max(limit, 1), 50),
                **(
                    {"dataset_version_id": dataset_version_id}
                    if dataset_version_id
                    else {}
                ),
            },
        )

    def subgraph(
        self,
        project_id: str,
        *,
        label: str,
        identity: str,
        depth: int = 2,
        limit: int = 50,
        dataset_version_id: str | None = None,
    ) -> Project3Subgraph:
        mapped = self.map_project_id(project_id)
        return self._model(
            Project3Subgraph,
            "GET",
            "/api/v1/graph/subgraph",
            params={
                "project_id": mapped,
                "label": label,
                "identity": identity,
                "depth": min(max(depth, 1), 3),
                "limit": min(max(limit, 1), 100),
                **(
                    {"dataset_version_id": dataset_version_id}
                    if dataset_version_id
                    else {}
                ),
            },
        )

    def query(self, project_id: str, *, question: str) -> Project3Query:
        mapped = self.map_project_id(project_id)
        return self._model(
            Project3Query,
            "POST",
            "/api/v1/query",
            json_body={"project_id": mapped, "question": question.strip()},
        )

    def rag_search(
        self,
        project_id: str,
        *,
        query: str,
        top_k: int = 5,
        current_only: bool = True,
        document_types: list[str] | None = None,
    ) -> Project3RagResult:
        mapped = self.map_project_id(project_id)
        return self._model(
            Project3RagResult,
            "POST",
            "/api/v1/rag/search",
            json_body={
                "project_id": mapped,
                "query": query.strip(),
                "top_k": min(max(top_k, 1), 20),
                "current_only": current_only,
                "document_types": document_types or [],
            },
        )

    def rag_query(
        self,
        project_id: str,
        *,
        query: str,
        top_k: int = 5,
        current_only: bool = True,
        document_types: list[str] | None = None,
    ) -> Project3RagResult:
        mapped = self.map_project_id(project_id)
        return self._model(
            Project3RagResult,
            "POST",
            "/api/v1/rag/query",
            json_body={
                "project_id": mapped,
                "query": query.strip(),
                "top_k": min(max(top_k, 1), 20),
                "current_only": current_only,
                "document_types": document_types or [],
            },
        )

    def agent_run(self, run_id: str) -> Project3AgentRun:
        return self._model(Project3AgentRun, "GET", f"/api/v1/agent/runs/{run_id}")

    def resume_agent_run(self, run_id: str, *, payload: dict[str, Any]) -> Project3AgentRun:
        return self._model(
            Project3AgentRun,
            "POST",
            f"/api/v1/agent/runs/{run_id}/resume",
            json_body=payload,
        )

    def project_graph(
        self,
        request: Project3GraphProjectionRequest,
    ) -> Project3GraphProjectionResponse:
        mapped = self.map_project_id(request.project_id)
        if mapped != request.project_id:
            raise Project3ContractError(
                "graph projection project mappings must preserve the payload project_id"
            )
        headers = {
            "X-Organization-ID": request.organization_id,
            "X-Project-ID": request.project_id,
            "X-Workspace-ID": request.workspace_id,
        }
        projection_secret = os.getenv(
            "ONTOLOGY_DASHBOARD_PROJECT3_PROJECTION_SECRET"
        )
        if projection_secret:
            headers["X-Projection-Secret"] = projection_secret
        return self._model(
            Project3GraphProjectionResponse,
            "POST",
            f"/api/v1/projects/{mapped}/graph/projections",
            json_body=request.model_dump(mode="json", by_alias=True),
            headers=headers,
        )

    def _model(
        self,
        model: type[TModel],
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> TModel:
        payload = self._request_json(
            method,
            path,
            params=params,
            json_body=json_body,
            headers=headers,
        )
        try:
            return model.model_validate(payload)
        except Exception as error:
            raise Project3ContractError(
                f"Project 3 response contract mismatch for {path}: {error}"
            ) from error

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self._ensure_circuit_allows_request()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
                if response.status_code >= 500:
                    raise Project3Unavailable(
                        f"Project 3 returned HTTP {response.status_code} for {path}"
                    )
                if response.status_code >= 400:
                    detail = response.text[:500]
                    raise Project3ContractError(
                        f"Project 3 rejected {path} with HTTP {response.status_code}: {detail}"
                    )
                payload = response.json()
                if not isinstance(payload, dict):
                    raise Project3ContractError(
                        f"Project 3 returned a non-object JSON payload for {path}"
                    )
                self._record_success()
                return payload
            except Project3ContractError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError, Project3Unavailable) as error:
                last_error = error
                if attempt < self.max_retries:
                    time.sleep(min(0.05 * (2**attempt), 0.2))
                    continue
        self._record_failure()
        if isinstance(last_error, Project3Unavailable):
            raise last_error
        raise Project3Unavailable(f"Project 3 request failed for {path}: {last_error}")

    def _ensure_circuit_allows_request(self) -> None:
        with self._circuit_lock:
            if self._circuit.opened_at is None:
                return
            if time.monotonic() - self._circuit.opened_at >= self.circuit_reset_seconds:
                self._circuit = _CircuitState()
                return
            raise Project3Unavailable("Project 3 circuit breaker is open")

    def _record_success(self) -> None:
        with self._circuit_lock:
            self._circuit = _CircuitState()

    def _record_failure(self) -> None:
        with self._circuit_lock:
            self._circuit.failures += 1
            if self._circuit.failures >= self.circuit_failure_threshold:
                self._circuit.opened_at = time.monotonic()


def parse_project_mapping(raw: str) -> dict[str, str]:
    value = raw.strip()
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return {
            str(source).strip(): str(target).strip()
            for source, target in parsed.items()
            if str(source).strip() and str(target).strip()
        }

    mapping: dict[str, str] = {}
    for item in value.split(","):
        if "=" not in item:
            raise ValueError(
                "ONTOLOGY_DASHBOARD_PROJECT3_PROJECT_MAP must be JSON or comma-separated source=target pairs"
            )
        source, target = item.split("=", 1)
        source = source.strip()
        target = target.strip()
        if not source or not target:
            raise ValueError("Project 3 project mappings must not contain blank IDs")
        mapping[source] = target
    return mapping

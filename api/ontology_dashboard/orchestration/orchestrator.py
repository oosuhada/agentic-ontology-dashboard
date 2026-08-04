"""Checkpointed multi-store evidence orchestration for Ontology Dashboard.

Project 2 owns routing, authorization, evidence merging and audit.  Graph ETL,
Text-to-Cypher and graph RAG remain inside Project 3 and are reached only through
its typed API client.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable
from typing import Any

from ..identity import AuthError, Principal
from .models import (
    AgentQueryRequest,
    AgentRoute,
    AgentRunPage,
    AgentRunResponse,
    AgentState,
    EvidenceItem,
    GroundedClaim,
    OrchestrationStep,
)
from .ports import EvidencePort
from .repository import AgentRunRepository


class MultiStoreOrchestrator:
    def __init__(
        self,
        repository: AgentRunRepository,
        *,
        relational_port: EvidencePort,
        graph_port: EvidencePort,
        vector_port: EvidencePort,
    ) -> None:
        self.repository = repository
        self.ports: dict[str, EvidencePort] = {
            "relational": relational_port,
            "graph": graph_port,
            "vector": vector_port,
        }

    def run(self, *, principal: Principal, request: AgentQueryRequest) -> AgentRunResponse:
        self._require_scope(principal, request)
        route = request.route if request.route != "auto" else self.classify(request.question)
        state = AgentState(
            run_id=f"agent-{uuid.uuid4()}",
            organization_id=principal.organization_id,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            user_id=principal.user_id,
            question=request.question,
            route=route,
            object_type=request.object_type,
            object_id=request.object_id,
        )
        state = self.repository.create(state)
        try:
            state = self.repository.checkpoint(state, "route")
            state = self._collect(state, route=route, top_k=request.top_k)
            state = self.repository.checkpoint(state, "merge_evidence")
            state = self._ground(state)
            state = self.repository.checkpoint(state, "validate_claims")
            state = state.model_copy(update={"status": "succeeded"})
            state = self.repository.finish(state)
        except Exception as error:
            state = state.model_copy(
                update={
                    "status": "failed",
                    "error": f"{type(error).__name__}: {error}",
                    "caveats": [*state.caveats, "The orchestration run failed before a grounded answer was completed."],
                }
            )
            self.repository.trace(
                state,
                step_name="orchestration_failure",
                store_kind=None,
                status="failed",
                input_payload={"route": route, "question": request.question},
                output_payload={"error": state.error},
                latency_ms=None,
            )
            state = self.repository.finish(state)
        return AgentRunResponse(
            state=state,
            traces=self.repository.traces(
                organization_id=principal.organization_id,
                project_id=request.project_id,
                run_id=state.run_id,
            ),
        )

    def list_runs(
        self,
        *,
        principal: Principal,
        project_id: str,
        workspace_id: str,
        offset: int = 0,
        limit: int = 25,
        status: str | None = None,
        route: str | None = None,
        search: str | None = None,
    ) -> AgentRunPage:
        request = AgentQueryRequest(
            project_id=project_id,
            workspace_id=workspace_id,
            question="scope validation",
        )
        self._require_scope(principal, request)
        return self.repository.list_run_page(
            organization_id=principal.organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            offset=offset,
            limit=limit,
            status=status,
            route=route,
            search=search,
        )

    def inspect(
        self,
        *,
        principal: Principal,
        project_id: str,
        run_id: str,
        workspace_id: str | None = None,
    ) -> AgentRunResponse:
        if project_id not in principal.project_scopes:
            raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 요청입니다.")
        state = self.repository.get(
            organization_id=principal.organization_id,
            project_id=project_id,
            run_id=run_id,
        )
        if state.workspace_id not in principal.workspace_scopes:
            raise AuthError(403, "workspace_scope_denied", "허용된 Workspace 범위를 벗어난 요청입니다.")
        if workspace_id is not None and state.workspace_id != workspace_id:
            raise AuthError(403, "workspace_scope_denied", "Agent run은 요청한 Workspace에 속하지 않습니다.")
        return AgentRunResponse(
            state=state,
            traces=self.repository.traces(
                organization_id=principal.organization_id,
                project_id=project_id,
                run_id=run_id,
            ),
        )

    @staticmethod
    def classify(question: str) -> AgentRoute:
        normalized = question.lower()
        graph_terms = (
            "relationship",
            "related",
            "connected",
            "path",
            "upstream",
            "downstream",
            "관계",
            "연결",
            "영향 경로",
        )
        vector_terms = (
            "document",
            "manual",
            "procedure",
            "policy",
            "similar",
            "evidence",
            "문서",
            "매뉴얼",
            "절차",
            "정책",
            "유사",
        )
        relational_terms = (
            "count",
            "list",
            "status",
            "latest",
            "table",
            "how many",
            "목록",
            "상태",
            "개수",
            "최신",
        )
        graph = any(term in normalized for term in graph_terms)
        vector = any(term in normalized for term in vector_terms)
        relational = any(term in normalized for term in relational_terms)
        selected = sum((graph, vector, relational))
        if selected >= 2:
            return "hybrid"
        if graph:
            return "graph"
        if vector:
            return "vector"
        if relational:
            return "relational"
        return "hybrid"

    def _collect(self, state: AgentState, *, route: AgentRoute, top_k: int) -> AgentState:
        routes = {
            "relational": ["relational"],
            "graph": ["graph"],
            "vector": ["vector"],
            "hybrid": ["relational", "graph", "vector"],
        }[route]
        evidence = list(state.evidence)
        steps = list(state.steps)
        caveats = list(state.caveats)
        successful_store_count = 0
        for port_name in routes:
            port = self.ports[port_name]
            started = time.perf_counter()
            try:
                found = port.search(state, top_k=top_k)
                latency_ms = int((time.perf_counter() - started) * 1000)
                evidence.extend(found)
                successful_store_count += 1
                steps.append(
                    OrchestrationStep(
                        name=f"collect_{port_name}",
                        store=self._evidence_store(port_name),
                        status="succeeded",
                        latency_ms=latency_ms,
                        detail=f"{len(found)} evidence items",
                    )
                )
                self.repository.trace(
                    state,
                    step_name=f"collect_{port_name}",
                    store_kind=port_name,
                    status="succeeded",
                    input_payload={"question": state.question, "top_k": top_k},
                    output_payload={
                        "evidence_count": len(found),
                        "evidence_ids": [item.evidence_id for item in found],
                    },
                    latency_ms=latency_ms,
                )
            except Exception as error:
                latency_ms = int((time.perf_counter() - started) * 1000)
                detail = f"{type(error).__name__}: {error}"
                caveats.append(f"{port_name} evidence was unavailable: {detail}")
                steps.append(
                    OrchestrationStep(
                        name=f"collect_{port_name}",
                        store=self._evidence_store(port_name),
                        status="failed",
                        latency_ms=latency_ms,
                        detail=detail,
                    )
                )
                self.repository.trace(
                    state,
                    step_name=f"collect_{port_name}",
                    store_kind=port_name,
                    status="failed",
                    input_payload={"question": state.question, "top_k": top_k},
                    output_payload={"error": detail},
                    latency_ms=latency_ms,
                )
        if successful_store_count == 0:
            raise RuntimeError("all selected evidence stores are unavailable")
        merged = self._merge_evidence(evidence)
        return state.model_copy(update={"evidence": merged, "steps": steps, "caveats": caveats})

    @staticmethod
    def _merge_evidence(items: Iterable[EvidenceItem]) -> list[EvidenceItem]:
        by_key: dict[tuple[str, str, str | None], EvidenceItem] = {}
        for item in items:
            key = (item.project_id, item.reference, item.dataset_version_id)
            current = by_key.get(key)
            if current is None or (item.score or 0) > (current.score or 0):
                by_key[key] = item
        return sorted(
            by_key.values(),
            key=lambda item: (-(item.score or 0), item.store, item.reference),
        )

    def _ground(self, state: AgentState) -> AgentState:
        if not state.evidence:
            return state.model_copy(
                update={
                    "answer": "검증 가능한 근거를 찾지 못했습니다.",
                    "claims": [],
                    "caveats": [*state.caveats, "No evidence items matched the scoped query."],
                }
            )
        claims: list[GroundedClaim] = []
        for index, item in enumerate(state.evidence[:8], start=1):
            content = " ".join(item.content.split())
            if len(content) > 260:
                content = content[:257].rstrip() + "..."
            claims.append(
                GroundedClaim(
                    claim_id=f"claim-{index}",
                    text=f"{item.title}: {content}",
                    evidence_ids=[item.evidence_id],
                    confidence="high" if (item.score or 0) >= 0.85 else "medium" if (item.score or 0) >= 0.5 else "low",
                )
            )
        self._validate_claims(claims, state.evidence)
        answer_lines = [f"- {claim.text} [{claim.evidence_ids[0]}]" for claim in claims]
        answer = "\n".join(answer_lines)
        return state.model_copy(update={"claims": claims, "answer": answer})

    @staticmethod
    def _validate_claims(claims: list[GroundedClaim], evidence: list[EvidenceItem]) -> None:
        evidence_ids = {item.evidence_id for item in evidence}
        for claim in claims:
            if not claim.evidence_ids or not set(claim.evidence_ids).issubset(evidence_ids):
                raise RuntimeError("ungrounded claim detected")
            if not claim.text.strip():
                raise RuntimeError("empty grounded claim detected")

    @staticmethod
    def _evidence_store(port_name: str):
        return {
            "relational": "postgresql",
            "graph": "neo4j",
            "vector": "pgvector",
        }[port_name]

    @staticmethod
    def _require_scope(principal: Principal, request: AgentQueryRequest) -> None:
        if request.project_id not in principal.project_scopes:
            raise AuthError(403, "project_scope_denied", "허용된 Project 범위를 벗어난 요청입니다.")
        if principal.active_project_id and request.project_id != principal.active_project_id:
            raise AuthError(409, "active_project_mismatch", "먼저 해당 Project를 활성화해야 합니다.")
        if request.workspace_id not in principal.workspace_scopes:
            raise AuthError(403, "workspace_scope_denied", "허용된 Workspace 범위를 벗어난 요청입니다.")

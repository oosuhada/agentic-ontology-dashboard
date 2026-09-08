from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.infra.external.project3.models import Project3GraphProjectionRequest
from .store import Neo4jGraphStore


ASSET_PATTERN = re.compile(r"(?:선택된\s+설비\s+)?([A-Za-z][A-Za-z0-9_.:#-]{3,})")


def _interests(question: str) -> set[str]:
    lower = question.lower()
    result: set[str] = set()
    if any(token in lower for token in ("부품", "component", "bearing", "베어링")):
        result.add("component")
    if any(token in lower for token in ("sop", "절차", "점검", "procedure")):
        result.add("sop")
    if any(token in lower for token in ("제품", "생산", "product")):
        result.update({"product", "production_cycle"})
    if any(token in lower for token in ("라인", "셀", "line", "cell")):
        result.add("production_cell")
    if any(token in lower for token in ("위험", "리스크", "risk", "event")):
        result.update({"risk_event", "prediction_result"})
    if any(token in lower for token in ("정비", "maintenance", "work order", "workorder")):
        result.update({"maintenance_case", "work_order", "maintenance_action"})
    if any(token in lower for token in ("유사", "비슷", "과거 사례", "similar", "case", "history")):
        result.add("maintenance_case")
    return result


def _asset_identity(question: str) -> str | None:
    match = re.search(r"선택된\s+설비\s+([A-Za-z0-9_.:#-]+)", question)
    if match:
        return match.group(1)
    for token in ASSET_PATTERN.findall(question):
        if "-" in token and any(char.isdigit() for char in token):
            return token
    return None


class GraphRuntimeService:
    def __init__(self, store: Neo4jGraphStore) -> None:
        self.store = store

    def initialize(self) -> None:
        self.store.ensure_schema()

    def health(self) -> dict[str, Any]:
        ready = self.store.ping()
        return {
            "status": "ready" if ready else "degraded",
            "checks": [{"check": "neo4j", "status": "ready" if ready else "failed", "detail": "bounded graph projection store", "required": True}],
        }

    def readiness(self, project_id: str) -> dict[str, Any]:
        state = self.store.readiness(project_id)
        return {
            "project_id": project_id,
            "lifecycle_status": "ready" if state["can_query"] else "projected_empty",
            "source_type": "neo4j",
            "upload_count": 1 if state["can_query"] else 0,
            "mapping_approved": state["can_query"],
            "schema_available": state["can_query"],
            "node_count": state["node_count"],
            "relationship_count": state["relationship_count"],
            "can_query": state["can_query"],
            "can_load": True,
            "eligible_for_ready": state["can_query"],
            "next_action": "query" if state["can_query"] else "project",
            "checks": {},
            "versions": {},
            "artifacts": {},
            "transitions": [],
        }

    def project(self, request: Project3GraphProjectionRequest) -> dict[str, Any]:
        result = self.store.project(request)
        return {
            "contract_version": "1.0",
            "message_type": "graph_projection_response",
            "projection_id": request.projection_id,
            "project_id": request.project_id,
            "dataset_version_id": request.dataset_version_id,
            "status": "completed",
            "project3_run_id": f"graph-run-{uuid.uuid4()}",
            "projection_checksum_sha256": result["projection_checksum_sha256"],
            "idempotent_replay": result["idempotent_replay"],
            "counts": {
                "nodes_received": len(request.nodes),
                "relationships_received": len(request.relationships),
                "nodes_written": result["nodes_written"],
                "relationships_written": result["relationships_written"],
            },
            "error": None,
            "updated_at": datetime.now(timezone.utc),
        }

    def query(self, project_id: str, question: str) -> dict[str, Any]:
        identity = _asset_identity(question)
        interests = _interests(question)
        rows = self.store.relationship_query(
            project_id=project_id,
            identity=identity,
            interests=interests,
            limit=20,
        )
        if rows:
            preview = ", ".join(
                f"{row['related_type']} {row['related_label']}"
                for row in rows[:4]
            )
            subject = identity or "현재 설비 범위"
            answer = f"{subject}에서 {len(rows)}개의 검증된 Ontology 관계를 찾았습니다. 주요 연결은 {preview}입니다."
        else:
            answer = "현재 versioned Ontology projection에서 질문과 일치하는 관계를 찾지 못했습니다."
        run_id = f"graph-query-{uuid.uuid4()}"
        return {
            "question": question,
            "answer": answer,
            "status": "succeeded",
            "cypher": "",
            "rows": rows,
            "row_count": len(rows),
            "metadata": {"identity": identity, "interests": sorted(interests), "query_mode": "bounded_pattern"},
            "evidence": {"source": "neo4j", "validated": True},
            "validation": {"raw_cypher_exposed": False, "bounded_depth": 3},
            "usage": {},
            "caveat": None,
            "provider": "neo4j-bounded-patterns",
            "fallback_reason": None,
            "run_id": run_id,
            "thread_id": None,
        }

"""Evidence ports: relational objects in Project 2 and graph/RAG capabilities in Project 3."""

from __future__ import annotations

import hashlib
from typing import Protocol

from ..integrations.project3 import Project3Client
from ..ontology_service import OntologyService
from .models import AgentState, EvidenceItem


class EvidencePort(Protocol):
    store_name: str

    def search(self, state: AgentState, *, top_k: int) -> list[EvidenceItem]: ...


def evidence_id(store: str, reference: str) -> str:
    digest = hashlib.sha256(f"{store}:{reference}".encode("utf-8")).hexdigest()[:20]
    return f"ev-{store}-{digest}"


class RelationalOntologyPort:
    store_name = "postgresql"

    def __init__(self, ontology: OntologyService) -> None:
        self.ontology = ontology

    def search(self, state: AgentState, *, top_k: int) -> list[EvidenceItem]:
        payload = self.ontology.query_objects(
            workspace_id=state.workspace_id,
            object_type=state.object_type,
            search=state.object_id or state.question,
            offset=0,
            limit=top_k,
        )
        evidence: list[EvidenceItem] = []
        for item in payload["items"]:
            properties = item.get("properties", {})
            reference = f"ontology:{item['object_type']}:{item['id']}:v{item.get('version', 1)}"
            dataset_version_id = None
            source_refs = item.get("source_refs", [])
            for source_ref in source_refs:
                if isinstance(source_ref, str) and source_ref.startswith("dsv-"):
                    dataset_version_id = source_ref
                    break
            evidence.append(
                EvidenceItem(
                    evidence_id=evidence_id(self.store_name, reference),
                    store="postgresql",
                    reference=reference,
                    project_id=state.project_id,
                    workspace_id=state.workspace_id,
                    dataset_version_id=dataset_version_id,
                    object_id=item.get("id"),
                    title=f"{item['object_type']} · {item['id']}",
                    content="; ".join(
                        f"{key}={value}" for key, value in list(properties.items())[:16]
                    ),
                    score=1.0,
                    metadata={
                        "object_type": item["object_type"],
                        "version": item.get("version"),
                        "source_refs": source_refs,
                    },
                )
            )
        return evidence


class Project3GraphPort:
    store_name = "neo4j"

    def __init__(self, client: Project3Client) -> None:
        self.client = client

    def search(self, state: AgentState, *, top_k: int) -> list[EvidenceItem]:
        result = self.client.query(state.project_id, question=state.question)
        evidence: list[EvidenceItem] = []
        for index, row in enumerate(result.rows[:top_k]):
            object_id = None
            for key in ("object_id", "equipment_id", "event_id", "id", "identity"):
                value = row.get(key)
                if value is not None:
                    object_id = str(value)
                    break
            reference = f"project3-query:{result.run_id or 'direct'}:row:{index}"
            evidence.append(
                EvidenceItem(
                    evidence_id=evidence_id(self.store_name, reference),
                    store="neo4j",
                    reference=reference,
                    project_id=state.project_id,
                    workspace_id=state.workspace_id,
                    object_id=object_id,
                    title=f"Graph result {index + 1}",
                    content="; ".join(f"{key}={value}" for key, value in row.items()),
                    score=1.0,
                    metadata={
                        "provider": result.provider,
                        "validation": result.validation,
                        "run_id": result.run_id,
                        "row_index": index,
                    },
                )
            )
        if not evidence and result.answer:
            reference = f"project3-query:{result.run_id or 'direct'}:answer"
            evidence.append(
                EvidenceItem(
                    evidence_id=evidence_id(self.store_name, reference),
                    store="neo4j",
                    reference=reference,
                    project_id=state.project_id,
                    workspace_id=state.workspace_id,
                    object_id=state.object_id,
                    title="Validated graph answer",
                    content=result.answer,
                    score=0.8,
                    metadata={
                        "provider": result.provider,
                        "validation": result.validation,
                        "run_id": result.run_id,
                        "caveat": result.caveat,
                    },
                )
            )
        return evidence


class Project3VectorPort:
    store_name = "pgvector"

    def __init__(self, client: Project3Client) -> None:
        self.client = client

    def search(self, state: AgentState, *, top_k: int) -> list[EvidenceItem]:
        result = self.client.rag_search(
            state.project_id,
            query=state.question,
            top_k=top_k,
            current_only=True,
        )
        evidence: list[EvidenceItem] = []
        for index, row in enumerate(result.results[:top_k]):
            reference = str(
                row.get("reference")
                or row.get("chunk_id")
                or row.get("id")
                or f"project3-rag:{index}"
            )
            content = str(
                row.get("content")
                or row.get("text")
                or row.get("snippet")
                or row
            )
            metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            dataset_version_id = metadata.get("dataset_version_id")
            object_id = metadata.get("object_id")
            score = row.get("score")
            evidence.append(
                EvidenceItem(
                    evidence_id=evidence_id(self.store_name, reference),
                    store="pgvector",
                    reference=reference,
                    project_id=state.project_id,
                    workspace_id=state.workspace_id,
                    dataset_version_id=str(dataset_version_id) if dataset_version_id else None,
                    object_id=str(object_id) if object_id else None,
                    title=str(row.get("title") or f"Document evidence {index + 1}"),
                    content=content,
                    score=float(score) if isinstance(score, (int, float)) else None,
                    metadata=metadata,
                )
            )
        return evidence

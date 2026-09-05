"""Application service for governed enterprise knowledge ingestion/search."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from app.infra.observability.runtime import METRICS

from .embedding import EmbeddingProvider
from .repository import KnowledgeRepository


_TOKEN = re.compile(r"[0-9A-Za-z가-힣_.:-]+")
INDEX_SCHEMA_VERSION = "enterprise-knowledge-hybrid-v2"


def chunk_text(content: str, *, max_chars: int = 900, overlap_chars: int = 140) -> list[str]:
    text = re.sub(r"\r\n?", "\n", content).strip()
    if not text:
        return []
    paragraphs = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [text]:
        pieces = [paragraph[index : index + max_chars] for index in range(0, len(paragraph), max_chars)] or [paragraph]
        for piece in pieces:
            candidate = f"{current}\n\n{piece}".strip() if current else piece
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
                prefix = current[-overlap_chars:] if overlap_chars else ""
                current = f"{prefix}\n{piece}".strip()
            else:
                chunks.append(piece[:max_chars])
                current = piece[max(0, max_chars - overlap_chars) :]
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk.strip()]


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(value) if len(token) > 1}


def _default_roles(document_type: str) -> list[str]:
    if document_type in {"financial_statement", "financial_actual"}:
        return ["tenant_admin", "executive_viewer", "process_manager", "quality_auditor", "fde"]
    if document_type in {"quality_incident", "capa_record", "safety_event"}:
        return ["tenant_admin", "process_manager", "process_engineer", "quality_auditor", "fde"]
    return []


class KnowledgeService:
    def __init__(self, repository: KnowledgeRepository, embedding_provider: EmbeddingProvider) -> None:
        self.repository = repository
        self.embedding_provider = embedding_provider

    def ingest(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        actor_user_id: str,
        title: str,
        document_type: str,
        content: str,
        source_ref: str,
        source_updated_at: str | None = None,
        allowed_roles: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document, changed = self.repository.upsert_document(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            title=title.strip(),
            document_type=document_type.strip(),
            content=content.strip(),
            source_ref=source_ref.strip(),
            source_updated_at=source_updated_at,
            allowed_roles=list(allowed_roles if allowed_roles is not None else _default_roles(document_type)),
            metadata=dict(metadata or {}),
            actor_user_id=actor_user_id,
        )
        METRICS.inc("ontology_knowledge_ingestion_total", labels={"changed": "true" if changed else "false"})
        return {**document, "changed": changed, "index_status": "dirty" if changed else "unchanged"}

    def bootstrap(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        documents: list[dict[str, Any]],
    ) -> dict[str, int]:
        normalized = []
        for item in documents:
            normalized.append({
                **item,
                "allowed_roles": list(item.get("allowed_roles") or _default_roles(str(item.get("document_type") or ""))),
            })
        return self.repository.seed_documents(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            documents=normalized,
        )

    def reindex(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        actor_user_id: str,
        force: bool = True,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        target_generation = self.repository.begin_index(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            force=force,
        )
        if target_generation is None:
            return self.repository.index_state(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        documents = self.repository.active_documents(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        digest = hashlib.sha256()
        digest.update(INDEX_SCHEMA_VERSION.encode("utf-8"))
        chunks: list[dict[str, Any]] = []
        for document in documents:
            digest.update(str(document["id"]).encode())
            digest.update(str(document["checksum_sha256"]).encode())
            title = str(document.get("title") or "")
            content = str(document.get("content") or "")
            for chunk_index, chunk in enumerate(chunk_text(content)):
                embedding_input = f"{title}\n{document.get('document_type','')}\n{chunk}"
                stored_content = f"{title}\n{chunk}".strip()
                chunks.append({
                    "document_id": str(document["id"]),
                    "version_id": str(document["version_id"]),
                    "title": title,
                    "document_type": str(document.get("document_type") or "reference"),
                    "source_ref": str(document.get("source_ref") or document["id"]),
                    "checksum_sha256": str(document["checksum_sha256"]),
                    "source_updated_at": document.get("source_updated_at"),
                    "chunk_index": chunk_index,
                    "content": stored_content,
                    "allowed_roles": list(document.get("allowed_roles") or []),
                    "metadata": dict(document.get("metadata") or {}),
                    "embedding": self.embedding_provider.embed(embedding_input),
                })
        try:
            state = self.repository.replace_index(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                provider_name=self.embedding_provider.name,
                corpus_checksum=digest.hexdigest(),
                documents=documents,
                chunks=chunks,
                actor_user_id=actor_user_id,
                target_generation=target_generation,
            )
        except Exception as exc:
            self.repository.mark_index_failed(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                error=f"{type(exc).__name__}: {exc}",
            )
            METRICS.inc("ontology_knowledge_index_failures_total", labels={"provider": self.embedding_provider.name})
            raise
        elapsed = max(0.0, time.perf_counter() - started)
        METRICS.inc("ontology_knowledge_index_runs_total", labels={"provider": self.embedding_provider.name})
        METRICS.observe("ontology_knowledge_index_duration_seconds", elapsed, labels={"provider": self.embedding_provider.name})
        METRICS.set_gauge("ontology_knowledge_index_chunks", len(chunks), labels={"project": "scoped"})
        return state

    def search(
        self,
        query: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        roles: list[str] | None = None,
        asset_id: str | None = None,
        top_k: int = 8,
        actor_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        started = time.perf_counter()
        query_embedding = self.embedding_provider.embed(query)
        query_token_list = sorted(_tokens(query))
        vector_candidates = self.repository.vector_candidates(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            query_embedding=query_embedding,
            limit=max(120, top_k * 20),
        )
        lexical_candidates = self.repository.lexical_candidates(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            query_tokens=query_token_list,
            limit=max(120, top_k * 20),
        )
        candidate_by_id: dict[str, dict[str, Any]] = {}
        for candidate in vector_candidates:
            candidate_by_id[str(candidate.get("id") or "")] = candidate
        for candidate in lexical_candidates:
            key = str(candidate.get("id") or "")
            existing = candidate_by_id.get(key)
            if existing is None:
                candidate_by_id[key] = candidate
            else:
                existing["lexical_rank"] = max(
                    float(existing.get("lexical_rank") or 0.0),
                    float(candidate.get("lexical_rank") or 0.0),
                )
        candidates = list(candidate_by_id.values())
        query_tokens = _tokens(query)
        query_lower = query.lower()
        role_set = set(roles or [])
        ranked: list[tuple[float, dict[str, Any]]] = []
        for item in candidates:
            allowed = set(str(role) for role in item.get("allowed_roles") or [])
            if allowed and not (allowed & role_set):
                continue
            metadata = dict(item.get("metadata") or {})
            content = str(item.get("content") or "")
            title = str(metadata.get("title") or "")
            lexical_overlap = len(query_tokens & _tokens(f"{title} {content}"))
            lexical_score = max(
                min(1.0, lexical_overlap / max(1, min(6, len(query_tokens)))),
                min(1.0, float(item.get("lexical_rank") or 0.0)),
            )
            related_assets = {str(value) for value in metadata.get("related_asset_ids") or []}
            asset_score = 1.0 if asset_id and asset_id in related_assets else 0.0
            freshness_score = 0.08 if metadata.get("source_updated_at") else 0.0
            vector_score = max(0.0, float(item.get("vector_score") or 0.0))
            kind = str(metadata.get("document_type") or "reference")
            intent_groups: dict[str, tuple[str, ...]] = {
                "maintenance_history": ("정비", "수리", "고장", "maintenance", "repair"),
                "maintenance_report": ("정비", "수리", "고장", "maintenance", "repair"),
                "material_master": ("부품", "자재", "재고", "조달", "bearing", "part", "inventory"),
                "purchase_order": ("부품", "입고", "eta", "발주", "구매", "조달", "purchase", "inbound"),
                "financial_actual": ("재무", "손익", "매출", "영업이익", "opex", "capex", "finance", "p&l"),
                "financial_statement": ("재무", "손익", "매출", "영업이익", "opex", "capex", "finance", "p&l"),
                "kpi_actual": ("kpi", "oee", "mtbf", "mttr", "가동률", "downtime", "lead time"),
                "quality_incident": ("품질", "불량", "결함", "scrap", "yield", "defect", "quality"),
                "capa_record": ("capa", "rca", "원인", "재발", "시정", "예방", "corrective"),
                "shift_handoff": ("교대", "인계", "handoff", "shift"),
                "calibration_record": ("교정", "calibration", "계측", "센서 정확도"),
                "safety_event": ("안전", "loto", "작업허가", "near miss", "safety"),
                "site_sop": ("sop", "절차", "매뉴얼", "점검 방법", "procedure"),
            }
            intent_score = 1.0 if any(token in query_lower for token in intent_groups.get(kind, ())) else 0.0
            # Monthly operations reports are useful corroborating narratives,
            # but should not outrank the actual KPI ledger when a query names
            # specific KPI metrics.
            if kind == "operations_report" and any(
                token in query_lower for token in ("kpi", "oee", "mtbf", "mttr", "downtime")
            ):
                intent_score = 0.45
            score = (
                vector_score * 0.50
                + lexical_score * 0.25
                + asset_score * 0.09
                + freshness_score * 0.02
                + intent_score * 0.14
            )
            ranked.append((score, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        selected: list[dict[str, Any]] = []
        kind_counts: dict[str, int] = {}
        for score, item in ranked:
            metadata = dict(item.get("metadata") or {})
            kind = str(metadata.get("document_type") or "reference")
            if kind_counts.get(kind, 0) >= 2:
                continue
            selected.append({
                "id": str(item.get("id") or ""),
                "document_id": str(item.get("object_id") or ""),
                "title": str(metadata.get("title") or "Knowledge evidence"),
                "document_type": kind,
                "content": str(item.get("content") or ""),
                "source_ref": str(metadata.get("source_ref") or item.get("object_id") or ""),
                "source_sha256": metadata.get("checksum_sha256"),
                "source_updated_at": metadata.get("source_updated_at"),
                "related_asset_ids": list(metadata.get("related_asset_ids") or []),
                "retrieval_score": round(score, 6),
                "vector_score": round(float(item.get("vector_score") or 0.0), 6),
                "retrieval_mode": "hybrid_pgvector_lexical" if candidates else "unindexed",
                "context_kind": "enterprise_knowledge",
            })
            kind_counts[kind] = kind_counts.get(kind, 0) + 1
            if len(selected) >= max(1, top_k):
                break
        latency_ms = max(0, int((time.perf_counter() - started) * 1000))
        METRICS.inc("ontology_knowledge_search_total", labels={"mode": "hybrid" if candidates else "unindexed"})
        METRICS.observe("ontology_knowledge_search_duration_seconds", latency_ms / 1000.0)
        self.repository.record_retrieval(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            query=query,
            mode="hybrid_pgvector_lexical" if candidates else "unindexed",
            results=selected,
            latency_ms=latency_ms,
        )
        return selected

    def search_project(
        self,
        query: str,
        *,
        project_id: str,
        workspace_id: str,
        roles: list[str] | None = None,
        asset_id: str | None = None,
        top_k: int = 8,
        actor_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        organization_id = self.repository.resolve_organization(
            project_id=project_id,
            workspace_id=workspace_id,
        )
        return self.search(
            query,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            roles=roles,
            asset_id=asset_id,
            top_k=top_k,
            actor_user_id=actor_user_id,
        )

    def stats(self, *, organization_id: str, project_id: str, workspace_id: str) -> dict[str, Any]:
        return {
            **self.repository.stats(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            ),
            "embedding_provider": self.embedding_provider.name,
            "embedding_dimensions": self.embedding_provider.dimensions,
        }


__all__ = ["KnowledgeService", "chunk_text"]

"""Persistence for versioned knowledge sources and vector index snapshots."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.infra.db.postgresql_compat import PostgreSQLProjectContextResolver, postgres_repository_connection
from app.infra.db.postgresql_repositories import is_postgresql


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    if len(text) == 4 and text.isdigit():
        return f"{text}-01-01T00:00:00+00:00"
    if len(text) == 7 and text[:4].isdigit() and text[4:] in {"-H1", "-H2"}:
        month = "01" if text.endswith("H1") else "07"
        return f"{text[:4]}-{month}-01T00:00:00+00:00"
    if len(text) == 7 and text[:4].isdigit() and text[4] == "-" and text[5:].isdigit():
        month = int(text[5:])
        if 1 <= month <= 12:
            return f"{text}-01T00:00:00+00:00"
        return None
    if len(text) == 10:
        try:
            datetime.fromisoformat(text)
        except ValueError:
            return None
        return f"{text}T00:00:00+00:00"
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return text


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (left_norm * right_norm)


class KnowledgeRepository:
    def __init__(self, database_target: str | Path) -> None:
        self.target = str(database_target)
        self._postgres = is_postgresql(self.target)
        self._resolver = PostgreSQLProjectContextResolver(self.target) if self._postgres else None

    def _connect(self, *, project_id: str | None = None):
        if self._postgres:
            organization_id = None
            if project_id and self._resolver:
                organization_id, _ = self._resolver.resolve_project(project_id)
            return postgres_repository_connection(
                self.target,
                organization_id=organization_id,
                project_id=project_id,
                resolver=self._resolver,
            )
        path = Path(self.target)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @staticmethod
    def _row(row: Any) -> dict[str, Any]:
        return dict(row) if row is not None else {}

    def resolve_organization(self, *, project_id: str, workspace_id: str) -> str:
        if self._postgres and self._resolver:
            context = self._resolver.resolve(workspace_id, expected_project_id=project_id)
            return str(context.organization_id)
        return "org-ontology-demo"

    def _upsert_document(
        self,
        connection: Any,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        title: str,
        document_type: str,
        content: str,
        source_ref: str,
        source_updated_at: str | None,
        allowed_roles: list[str],
        metadata: dict[str, Any],
        actor_user_id: str | None,
    ) -> tuple[dict[str, Any], bool]:
        now = _now()
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = connection.execute(
            """
            SELECT * FROM knowledge_documents
            WHERE organization_id=? AND project_id=? AND workspace_id=? AND source_ref=?
            """,
            (organization_id, project_id, workspace_id, source_ref),
        ).fetchone()
        if existing is None:
            document_id = f"kdoc-{hashlib.sha256(f'{project_id}:{workspace_id}:{source_ref}'.encode()).hexdigest()[:24]}"
            connection.execute(
                """
                INSERT INTO knowledge_documents(
                    id,organization_id,project_id,workspace_id,title,document_type,source_ref,
                    allowed_roles_json,metadata_json,status,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    document_id,
                    organization_id,
                    project_id,
                    workspace_id,
                    title,
                    document_type,
                    source_ref,
                    _json(allowed_roles),
                    _json(metadata),
                    "active",
                    now,
                    now,
                ),
            )
            next_version = 1
        else:
            document_id = str(existing["id"])
            same = connection.execute(
                "SELECT * FROM knowledge_document_versions WHERE document_id=? AND checksum_sha256=?",
                (document_id, checksum),
            ).fetchone()
            connection.execute(
                """
                UPDATE knowledge_documents
                SET title=?,document_type=?,allowed_roles_json=?,metadata_json=?,status='active',updated_at=?
                WHERE id=?
                """,
                (title, document_type, _json(allowed_roles), _json(metadata), now, document_id),
            )
            if same is not None:
                return self._document_payload(connection, document_id), False
            row = connection.execute(
                "SELECT COALESCE(MAX(version_number),0)+1 AS next_version FROM knowledge_document_versions WHERE document_id=?",
                (document_id,),
            ).fetchone()
            next_version = int(row["next_version"])
            connection.execute(
                "UPDATE knowledge_document_versions SET status='superseded' WHERE document_id=? AND status='approved'",
                (document_id,),
            )

        version_id = f"kver-{uuid.uuid4()}"
        connection.execute(
            """
            INSERT INTO knowledge_document_versions(
                id,organization_id,project_id,workspace_id,document_id,version_number,content,
                checksum_sha256,source_updated_at,effective_from,effective_to,status,created_by,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                version_id,
                organization_id,
                project_id,
                workspace_id,
                document_id,
                next_version,
                content,
                checksum,
                _timestamp(source_updated_at),
                _timestamp(metadata.get("effective_from")),
                _timestamp(metadata.get("effective_to")),
                "approved",
                actor_user_id,
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO knowledge_index_state(
                organization_id,project_id,workspace_id,status,requested_generation,indexed_generation,updated_at
            ) VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(organization_id,project_id,workspace_id)
            DO UPDATE SET
                status='dirty',
                requested_generation=knowledge_index_state.requested_generation+1,
                updated_at=excluded.updated_at,
                last_error=NULL
            """,
            (organization_id, project_id, workspace_id, "dirty", 1, 0, now),
        )
        return self._document_payload(connection, document_id), True

    def upsert_document(self, **values: Any) -> tuple[dict[str, Any], bool]:
        with self._connect(project_id=str(values["project_id"])) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(str(values["organization_id"]), str(values["project_id"]))
            return self._upsert_document(connection, **values)

    def seed_documents(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        documents: Iterable[dict[str, Any]],
    ) -> dict[str, int]:
        inserted = 0
        unchanged = 0
        with self._connect(project_id=project_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(organization_id, project_id)
            for item in documents:
                _, changed = self._upsert_document(
                    connection,
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    title=str(item.get("title") or item.get("id") or "Knowledge document"),
                    document_type=str(item.get("document_type") or "reference"),
                    content=str(item.get("content") or ""),
                    source_ref=str(item.get("source_ref") or item.get("id") or uuid.uuid4()),
                    source_updated_at=str(item.get("source_updated_at") or "") or None,
                    allowed_roles=list(item.get("allowed_roles") or []),
                    metadata={
                        **dict(item.get("metadata") or {}),
                        "related_asset_ids": list(item.get("related_asset_ids") or []),
                        "source_sha256": item.get("source_sha256"),
                        "tags": list(item.get("tags") or []),
                    },
                    actor_user_id="bootstrap",
                )
                inserted += int(changed)
                unchanged += int(not changed)
        return {"inserted_or_versioned": inserted, "unchanged": unchanged}

    def _document_payload(self, connection: Any, document_id: str) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT d.*,v.id AS version_id,v.version_number,v.content,v.checksum_sha256,
                   v.source_updated_at,v.effective_from,v.effective_to,v.status AS version_status
            FROM knowledge_documents d
            JOIN knowledge_document_versions v ON v.document_id=d.id AND v.status='approved'
            WHERE d.id=?
            ORDER BY v.version_number DESC LIMIT 1
            """,
            (document_id,),
        ).fetchone()
        payload = self._row(row)
        payload["allowed_roles"] = _load_json(payload.pop("allowed_roles_json", "[]"), [])
        payload["metadata"] = _load_json(payload.pop("metadata_json", "{}"), {})
        return payload

    def active_documents(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect(project_id=project_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(organization_id, project_id)
            rows = connection.execute(
                """
                SELECT d.*,v.id AS version_id,v.version_number,v.content,v.checksum_sha256,
                       v.source_updated_at,v.effective_from,v.effective_to
                FROM knowledge_documents d
                JOIN knowledge_document_versions v ON v.document_id=d.id AND v.status='approved'
                WHERE d.organization_id=? AND d.project_id=? AND d.workspace_id=? AND d.status='active'
                ORDER BY d.document_type,d.source_ref
                """,
                (organization_id, project_id, workspace_id),
            ).fetchall()
        result = []
        for row in rows:
            item = self._row(row)
            item["allowed_roles"] = _load_json(item.pop("allowed_roles_json", "[]"), [])
            item["metadata"] = _load_json(item.pop("metadata_json", "{}"), {})
            result.append(item)
        return result

    def index_state(self, *, organization_id: str, project_id: str, workspace_id: str) -> dict[str, Any]:
        with self._connect(project_id=project_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(organization_id, project_id)
            row = connection.execute(
                """
                SELECT * FROM knowledge_index_state
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                """,
                (organization_id, project_id, workspace_id),
            ).fetchone()
        return self._row(row)

    def begin_index(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        force: bool,
    ) -> int | None:
        now = _now()
        with self._connect(project_id=project_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(organization_id, project_id)
            state = connection.execute(
                """
                SELECT requested_generation,status FROM knowledge_index_state
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                """,
                (organization_id, project_id, workspace_id),
            ).fetchone()
            if state is None:
                return None
            if not force and str(state["status"]) != "dirty":
                return None
            generation = int(state["requested_generation"] or 0)
            cursor = connection.execute(
                """
                UPDATE knowledge_index_state
                SET status='indexing',updated_at=?,last_error=NULL
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                  AND status=?
                """,
                (
                    now,
                    organization_id,
                    project_id,
                    workspace_id,
                    str(state["status"]),
                ),
            )
            if int(getattr(cursor, "rowcount", 0)) != 1:
                return None
            return generation

    def mark_index_failed(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        error: str,
    ) -> None:
        with self._connect(project_id=project_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(organization_id, project_id)
            connection.execute(
                """
                UPDATE knowledge_index_state
                SET status='failed',last_error=?,updated_at=?
                WHERE organization_id=? AND project_id=? AND workspace_id=?
                """,
                (error[:1000], _now(), organization_id, project_id, workspace_id),
            )

    def replace_index(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        provider_name: str,
        corpus_checksum: str,
        documents: list[dict[str, Any]],
        chunks: list[dict[str, Any]],
        actor_user_id: str,
        target_generation: int,
    ) -> dict[str, Any]:
        requested_dataset_id = f"knowledge-{hashlib.sha256(f'{project_id}:{workspace_id}'.encode()).hexdigest()[:20]}"
        version_id = f"knowledge-index-{corpus_checksum[:24]}"
        now = _now()
        with self._connect(project_id=project_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(organization_id, project_id)
            # Some upgraded deployments predate the newer composite UNIQUE
            # constraints from the Dataset Catalog migrations. Resolve an
            # existing row explicitly instead of relying on an ON CONFLICT
            # target that may not exist on those historical databases.
            dataset_row = connection.execute(
                "SELECT id FROM datasets WHERE project_id=? AND slug=? ORDER BY created_at LIMIT 1",
                (project_id, "enterprise-knowledge"),
            ).fetchone()
            if dataset_row is None:
                connection.execute(
                    """
                    INSERT INTO datasets(id,organization_id,project_id,workspace_id,slug,display_name,description,source_type,status,created_by,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        requested_dataset_id, organization_id, project_id, workspace_id, "enterprise-knowledge",
                        "Enterprise Knowledge Corpus", "Versioned RAG document corpus", "knowledge", "active",
                        actor_user_id, now, now,
                    ),
                )
                dataset_id = requested_dataset_id
            else:
                dataset_id = str(dataset_row["id"])

            source_version = f"knowledge:{corpus_checksum}"
            version_row = connection.execute(
                "SELECT id FROM dataset_versions WHERE dataset_id=? AND source_version=?",
                (dataset_id, source_version),
            ).fetchone()
            if version_row is None:
                number_row = connection.execute(
                    "SELECT COALESCE(MAX(version_number),0)+1 AS next_version FROM dataset_versions WHERE dataset_id=?",
                    (dataset_id,),
                ).fetchone()
                version_number = int(number_row["next_version"])
                connection.execute(
                    """
                    INSERT INTO dataset_versions(
                        id,organization_id,project_id,workspace_id,dataset_id,version_number,version_label,
                        source_version,manifest_id,checksum_sha256,schema_json,profile_json,record_count,status,created_by,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        version_id, organization_id, project_id, workspace_id, dataset_id, version_number,
                        f"index-{corpus_checksum[:12]}", source_version, None, corpus_checksum,
                        _json({"kind": "enterprise_knowledge_chunks", "embedding_dimensions": 1536}),
                        _json({"embedding_provider": provider_name, "document_count": len(documents)}),
                        len(chunks), "ready", actor_user_id, now,
                    ),
                )
            else:
                version_id = str(version_row["id"])
            connection.execute("DELETE FROM vector_document_chunks WHERE dataset_version_id=?", (version_id,))
            for chunk in chunks:
                metadata = dict(chunk["metadata"])
                metadata.update({
                    "knowledge_document_id": chunk["document_id"],
                    "knowledge_version_id": chunk["version_id"],
                    "title": chunk["title"],
                    "document_type": chunk["document_type"],
                    "source_ref": chunk["source_ref"],
                    "checksum_sha256": chunk["checksum_sha256"],
                    "source_updated_at": chunk.get("source_updated_at"),
                })
                embedding_json = _json(chunk["embedding"])
                chunk_id = f"kchunk-{hashlib.sha256(f'{version_id}:{chunk['document_id']}:{chunk['chunk_index']}'.encode()).hexdigest()[:28]}"
                if self._postgres:
                    connection.execute(
                        """
                        INSERT INTO vector_document_chunks(
                            id,organization_id,project_id,workspace_id,dataset_id,dataset_version_id,
                            object_id,chunk_index,content,metadata_json,embedding_json,allowed_roles,created_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?::text[],?)
                        """,
                        (
                            chunk_id, organization_id, project_id, workspace_id, dataset_id, version_id,
                            chunk["document_id"], chunk["chunk_index"], chunk["content"], _json(metadata),
                            embedding_json, "{" + ",".join(chunk["allowed_roles"]) + "}", now,
                        ),
                    )
                    connection.execute(
                        "UPDATE vector_document_chunks SET embedding=CAST(? AS vector) WHERE id=?",
                        ("[" + ",".join(f"{value:.8f}" for value in chunk["embedding"]) + "]", chunk_id),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO vector_document_chunks(
                            id,organization_id,project_id,workspace_id,dataset_id,dataset_version_id,
                            object_id,chunk_index,content,metadata_json,embedding_json,allowed_roles_json,created_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            chunk_id, organization_id, project_id, workspace_id, dataset_id, version_id,
                            chunk["document_id"], chunk["chunk_index"], chunk["content"], _json(metadata),
                            embedding_json, _json(chunk["allowed_roles"]), now,
                        ),
                    )
            connection.execute(
                "DELETE FROM store_projections WHERE dataset_version_id=? AND store_kind='vector'",
                (version_id,),
            )
            connection.execute(
                """
                INSERT INTO store_projections(
                    id,organization_id,project_id,workspace_id,dataset_id,dataset_version_id,store_kind,status,
                    object_namespace,source_version,record_count,attempt_count,started_at,completed_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    f"projection-{uuid.uuid4()}", organization_id, project_id, workspace_id, dataset_id, version_id,
                    "vector", "ready", f"{project_id}:{dataset_id}:{version_id}", f"knowledge:{corpus_checksum}",
                    len(chunks), 1, now, now, now,
                ),
            )
            connection.execute(
                """
                INSERT INTO knowledge_index_state(
                    organization_id,project_id,workspace_id,dataset_id,dataset_version_id,embedding_provider,
                    corpus_checksum_sha256,document_count,chunk_count,status,last_indexed_at,last_error,
                    requested_generation,indexed_generation,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(organization_id,project_id,workspace_id) DO UPDATE SET
                    dataset_id=excluded.dataset_id,dataset_version_id=excluded.dataset_version_id,
                    embedding_provider=excluded.embedding_provider,corpus_checksum_sha256=excluded.corpus_checksum_sha256,
                    document_count=excluded.document_count,chunk_count=excluded.chunk_count,
                    status=CASE
                        WHEN knowledge_index_state.requested_generation>excluded.indexed_generation THEN 'dirty'
                        ELSE 'ready'
                    END,
                    last_indexed_at=excluded.last_indexed_at,last_error=NULL,
                    indexed_generation=excluded.indexed_generation,updated_at=excluded.updated_at
                """,
                (
                    organization_id, project_id, workspace_id, dataset_id, version_id, provider_name,
                    corpus_checksum, len(documents), len(chunks), "ready", now, None,
                    target_generation, target_generation, now,
                ),
            )
        return self.index_state(organization_id=organization_id, project_id=project_id, workspace_id=workspace_id)

    def vector_candidates(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        query_embedding: list[float],
        limit: int,
    ) -> list[dict[str, Any]]:
        state = self.index_state(organization_id=organization_id, project_id=project_id, workspace_id=workspace_id)
        version_id = str(state.get("dataset_version_id") or "")
        if not version_id or state.get("status") != "ready":
            return []
        with self._connect(project_id=project_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(organization_id, project_id)
            if self._postgres:
                vector_literal = "[" + ",".join(f"{value:.8f}" for value in query_embedding) + "]"
                rows = connection.execute(
                    """
                    SELECT id,object_id,chunk_index,content,metadata_json,allowed_roles,
                           1 - (embedding <=> CAST(? AS vector)) AS vector_score
                    FROM vector_document_chunks
                    WHERE organization_id=? AND project_id=? AND workspace_id=? AND dataset_version_id=?
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> CAST(? AS vector)
                    LIMIT ?
                    """,
                    (vector_literal, organization_id, project_id, workspace_id, version_id, vector_literal, limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id,object_id,chunk_index,content,metadata_json,embedding_json,allowed_roles_json
                    FROM vector_document_chunks
                    WHERE organization_id=? AND project_id=? AND workspace_id=? AND dataset_version_id=?
                    """,
                    (organization_id, project_id, workspace_id, version_id),
                ).fetchall()
        candidates = []
        for row in rows:
            item = self._row(row)
            if self._postgres:
                roles = list(item.pop("allowed_roles", []) or [])
                vector_score = float(item.get("vector_score") or 0.0)
            else:
                roles = _load_json(item.pop("allowed_roles_json", "[]"), [])
                vector_score = _cosine(query_embedding, [float(v) for v in _load_json(item.pop("embedding_json", "[]"), [])])
            item["allowed_roles"] = roles
            item["metadata"] = _load_json(item.pop("metadata_json", "{}"), {})
            item["vector_score"] = max(-1.0, min(1.0, vector_score))
            candidates.append(item)
        candidates.sort(key=lambda item: float(item["vector_score"]), reverse=True)
        return candidates[:limit]

    def lexical_candidates(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        query_tokens: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        state = self.index_state(organization_id=organization_id, project_id=project_id, workspace_id=workspace_id)
        version_id = str(state.get("dataset_version_id") or "")
        tokens = [token.lower() for token in query_tokens if token.strip()][:10]
        if not version_id or state.get("status") != "ready" or not tokens:
            return []
        with self._connect(project_id=project_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(organization_id, project_id)
            if self._postgres:
                vector_expr = "to_tsvector('simple', content)"
                predicates = " OR ".join(
                    f"{vector_expr} @@ plainto_tsquery('simple', ?)" for _ in tokens
                )
                rank_expr = " + ".join(
                    f"ts_rank_cd({vector_expr}, plainto_tsquery('simple', ?))" for _ in tokens
                )
                parameters: list[Any] = [*tokens, *tokens, organization_id, project_id, workspace_id, version_id, limit]
                rows = connection.execute(
                    f"""
                    SELECT id,object_id,chunk_index,content,metadata_json,allowed_roles,
                           ({rank_expr}) AS lexical_rank
                    FROM vector_document_chunks
                    WHERE ({predicates})
                      AND organization_id=? AND project_id=? AND workspace_id=? AND dataset_version_id=?
                    ORDER BY lexical_rank DESC, id
                    LIMIT ?
                    """,
                    tuple(parameters),
                ).fetchall()
            else:
                predicates = " OR ".join(
                    "(LOWER(content) LIKE ? OR LOWER(CAST(metadata_json AS TEXT)) LIKE ?)"
                    for _ in tokens
                )
                patterns = [value for token in tokens for value in (f"%{token}%", f"%{token}%")]
                rows = connection.execute(
                    f"""
                    SELECT id,object_id,chunk_index,content,metadata_json,allowed_roles_json
                    FROM vector_document_chunks
                    WHERE ({predicates})
                      AND organization_id=? AND project_id=? AND workspace_id=? AND dataset_version_id=?
                    ORDER BY id
                    LIMIT ?
                    """,
                    (*patterns, organization_id, project_id, workspace_id, version_id, limit),
                ).fetchall()
        candidates: list[dict[str, Any]] = []
        token_set = set(tokens)
        for row in rows:
            item = self._row(row)
            if self._postgres:
                roles = list(item.pop("allowed_roles", []) or [])
                lexical_rank = float(item.pop("lexical_rank", 0.0) or 0.0)
            else:
                roles = _load_json(item.pop("allowed_roles_json", "[]"), [])
                lexical_rank = 0.0
            item["allowed_roles"] = roles
            item["metadata"] = _load_json(item.pop("metadata_json", "{}"), {})
            matched = len(token_set & {
                token.lower()
                for token in re.findall(r"[0-9A-Za-z가-힣_.:-]+", f"{item.get('content','')} {item['metadata'].get('title','')}")
                if len(token) > 1
            })
            item["lexical_rank"] = max(lexical_rank, matched / max(1, len(token_set)))
            item["vector_score"] = 0.0
            candidates.append(item)
        candidates.sort(key=lambda item: float(item.get("lexical_rank") or 0.0), reverse=True)
        return candidates[:limit]

    def record_retrieval(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        actor_user_id: str | None,
        query: str,
        mode: str,
        results: list[dict[str, Any]],
        latency_ms: int,
    ) -> None:
        now = _now()
        with self._connect(project_id=project_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(organization_id, project_id)
            connection.execute(
                """
                INSERT INTO knowledge_retrieval_audit(
                    id,organization_id,project_id,workspace_id,actor_user_id,query_sha256,retrieval_mode,
                    result_count,latency_ms,result_refs_json,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    f"kra-{uuid.uuid4()}", organization_id, project_id, workspace_id, actor_user_id,
                    hashlib.sha256(query.encode("utf-8")).hexdigest(), mode, len(results), latency_ms,
                    _json([str(item.get("source_ref") or item.get("id") or "") for item in results[:20]]), now,
                ),
            )

    def stats(self, *, organization_id: str, project_id: str, workspace_id: str) -> dict[str, Any]:
        with self._connect(project_id=project_id) as connection:
            if self._postgres and hasattr(connection, "bind_scope"):
                connection.bind_scope(organization_id, project_id)
            doc = connection.execute(
                "SELECT COUNT(*) AS count FROM knowledge_documents WHERE organization_id=? AND project_id=? AND workspace_id=? AND status='active'",
                (organization_id, project_id, workspace_id),
            ).fetchone()
            versions = connection.execute(
                "SELECT COUNT(*) AS count FROM knowledge_document_versions WHERE organization_id=? AND project_id=? AND workspace_id=?",
                (organization_id, project_id, workspace_id),
            ).fetchone()
            audits = connection.execute(
                "SELECT COUNT(*) AS count FROM knowledge_retrieval_audit WHERE organization_id=? AND project_id=? AND workspace_id=?",
                (organization_id, project_id, workspace_id),
            ).fetchone()
        return {
            "document_count": int(doc["count"]),
            "version_count": int(versions["count"]),
            "retrieval_audit_count": int(audits["count"]),
            "index": self.index_state(organization_id=organization_id, project_id=project_id, workspace_id=workspace_id),
        }


__all__ = ["KnowledgeRepository"]

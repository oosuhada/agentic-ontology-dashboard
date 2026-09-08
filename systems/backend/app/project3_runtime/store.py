from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

from app.infra.external.project3.models import Project3GraphProjectionRequest


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list) and all(item is None or isinstance(item, (str, int, float, bool)) for item in value):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _safe_properties(values: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _safe_value(value) for key, value in values.items() if value is not None}


def projection_checksum(request: Project3GraphProjectionRequest) -> str:
    payload = request.model_dump(mode="json", exclude={"requested_at"})
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


class Neo4jGraphStore:
    """Versioned read projection store.

    PostgreSQL remains authoritative. Every projection keeps its Dataset Version
    identity while only the newest projection for a project is marked current.
    """

    def __init__(self, *, uri: str, username: str, password: str, database: str = "neo4j") -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:  # pragma: no cover - production extra guard
            raise RuntimeError("Project 3 runtime requires the backend production/polyglot extra") from exc
        self.database = database
        self._driver = GraphDatabase.driver(uri, auth=(username, password))

    @classmethod
    def from_environment(cls) -> "Neo4jGraphStore":
        uri = os.getenv("ONTOLOGY_DASHBOARD_NEO4J_URI", "bolt://neo4j:7687")
        username = os.getenv("ONTOLOGY_DASHBOARD_NEO4J_USERNAME", "neo4j")
        password = os.getenv("ONTOLOGY_DASHBOARD_NEO4J_PASSWORD", "")
        if not password:
            raise RuntimeError("ONTOLOGY_DASHBOARD_NEO4J_PASSWORD is required")
        return cls(
            uri=uri,
            username=username,
            password=password,
            database=os.getenv("ONTOLOGY_DASHBOARD_NEO4J_DATABASE", "neo4j"),
        )

    def close(self) -> None:
        self._driver.close()

    def ping(self) -> bool:
        with self._driver.session(database=self.database) as session:
            return bool(session.run("RETURN 1 AS ok").single()["ok"])

    def ensure_schema(self) -> None:
        statements = (
            "CREATE CONSTRAINT graph_node_key IF NOT EXISTS FOR (n:GraphNode) REQUIRE n.node_key IS UNIQUE",
            "CREATE CONSTRAINT graph_projection_key IF NOT EXISTS FOR (p:GraphProjection) REQUIRE p.projection_id IS UNIQUE",
            "CREATE INDEX graph_node_project_current IF NOT EXISTS FOR (n:GraphNode) ON (n.project_id, n.is_current)",
            "CREATE INDEX graph_node_identity IF NOT EXISTS FOR (n:GraphNode) ON (n.project_id, n.source_identity)",
            "CREATE INDEX graph_node_type IF NOT EXISTS FOR (n:GraphNode) ON (n.project_id, n.object_type)",
        )
        with self._driver.session(database=self.database) as session:
            for statement in statements:
                session.run(statement).consume()

    @staticmethod
    def _node_key(project_id: str, dataset_version_id: str, object_type: str, source_identity: str) -> str:
        return f"{project_id}|{dataset_version_id}|{object_type}|{source_identity}"

    def project(self, request: Project3GraphProjectionRequest) -> dict[str, Any]:
        checksum = projection_checksum(request)
        projected_at = datetime.now(timezone.utc).isoformat()
        nodes = []
        for item in request.nodes:
            identity = item.identity
            properties = _safe_properties(item.properties)
            nodes.append({
                "node_key": self._node_key(
                    identity.project_id,
                    identity.dataset_version_id,
                    identity.object_type,
                    identity.source_identity,
                ),
                "organization_id": identity.organization_id,
                "project_id": identity.project_id,
                "dataset_id": identity.dataset_id,
                "dataset_version_id": identity.dataset_version_id,
                "object_type": identity.object_type,
                "source_identity": identity.source_identity,
                "source_reference": item.source_reference,
                "source_sha256": item.source_sha256,
                "projection_id": request.projection_id,
                "projected_at": projected_at,
                "properties": properties,
            })
        relationships = []
        for item in request.relationships:
            relationships.append({
                "relationship_type": item.relationship_type,
                "from_key": self._node_key(
                    item.from_identity.project_id,
                    item.from_identity.dataset_version_id,
                    item.from_identity.object_type,
                    item.from_identity.source_identity,
                ),
                "to_key": self._node_key(
                    item.to_identity.project_id,
                    item.to_identity.dataset_version_id,
                    item.to_identity.object_type,
                    item.to_identity.source_identity,
                ),
                "source_reference": item.source_reference,
                "source_sha256": item.source_sha256,
                "properties": _safe_properties(item.properties),
            })

        def write(tx):
            existing = tx.run(
                "MATCH (p:GraphProjection {projection_id:$projection_id}) RETURN p.projection_checksum AS checksum, p.status AS status",
                projection_id=request.projection_id,
            ).single()
            if existing is not None and existing["status"] == "completed":
                if existing["checksum"] != checksum:
                    raise ValueError("projection_id already exists with a different checksum")
                return {"idempotent_replay": True}

            tx.run(
                "MATCH (n:GraphNode {project_id:$project_id}) SET n.is_current=false",
                project_id=request.project_id,
            ).consume()
            tx.run(
                "MATCH (n:GraphNode {project_id:$project_id, dataset_version_id:$dataset_version_id}) DETACH DELETE n",
                project_id=request.project_id,
                dataset_version_id=request.dataset_version_id,
            ).consume()
            tx.run(
                """
                MERGE (p:GraphProjection {projection_id:$projection_id})
                SET p.project_id=$project_id,
                    p.dataset_version_id=$dataset_version_id,
                    p.idempotency_key=$idempotency_key,
                    p.projection_checksum=$checksum,
                    p.status='processing',
                    p.updated_at=$projected_at
                """,
                projection_id=request.projection_id,
                project_id=request.project_id,
                dataset_version_id=request.dataset_version_id,
                idempotency_key=request.idempotency_key,
                checksum=checksum,
                projected_at=projected_at,
            ).consume()
            tx.run(
                """
                UNWIND $nodes AS item
                CREATE (n:GraphNode)
                SET n = item.properties,
                    n.node_key=item.node_key,
                    n.organization_id=item.organization_id,
                    n.project_id=item.project_id,
                    n.dataset_id=item.dataset_id,
                    n.dataset_version_id=item.dataset_version_id,
                    n.object_type=item.object_type,
                    n.source_identity=item.source_identity,
                    n.source_reference=item.source_reference,
                    n.source_sha256=item.source_sha256,
                    n.projection_id=item.projection_id,
                    n.projected_at=item.projected_at,
                    n.is_current=true
                """,
                nodes=nodes,
            ).consume()
            # Relationship types are supplied by a strict projection model and
            # additionally validated here before becoming Cypher identifiers.
            for relationship in relationships:
                relationship_type = relationship["relationship_type"]
                if not relationship_type.replace("_", "").isalnum() or relationship_type.upper() != relationship_type:
                    raise ValueError(f"unsafe relationship type: {relationship_type}")
                tx.run(
                    f"""
                    MATCH (a:GraphNode {{node_key:$from_key}}), (b:GraphNode {{node_key:$to_key}})
                    CREATE (a)-[r:{relationship_type}]->(b)
                    SET r = $properties,
                        r.source_reference=$source_reference,
                        r.source_sha256=$source_sha256,
                        r.projection_id=$projection_id
                    """,
                    from_key=relationship["from_key"],
                    to_key=relationship["to_key"],
                    properties=relationship["properties"],
                    source_reference=relationship["source_reference"],
                    source_sha256=relationship["source_sha256"],
                    projection_id=request.projection_id,
                ).consume()
            tx.run(
                """
                MATCH (p:GraphProjection {projection_id:$projection_id})
                SET p.status='completed', p.updated_at=$projected_at,
                    p.node_count=$node_count, p.relationship_count=$relationship_count
                """,
                projection_id=request.projection_id,
                projected_at=projected_at,
                node_count=len(nodes),
                relationship_count=len(relationships),
            ).consume()
            return {"idempotent_replay": False}

        with self._driver.session(database=self.database) as session:
            result = session.execute_write(write)
        return {
            "projection_checksum_sha256": checksum,
            "nodes_written": len(nodes),
            "relationships_written": len(relationships),
            "idempotent_replay": bool(result["idempotent_replay"]),
        }

    def readiness(self, project_id: str) -> dict[str, Any]:
        with self._driver.session(database=self.database) as session:
            row = session.run(
                """
                MATCH (n:GraphNode {project_id:$project_id, is_current:true})
                WITH count(n) AS nodes
                OPTIONAL MATCH (:GraphNode {project_id:$project_id, is_current:true})-[r]->(:GraphNode {project_id:$project_id, is_current:true})
                RETURN nodes, count(r) AS relationships
                """,
                project_id=project_id,
            ).single()
        nodes = int(row["nodes"] if row else 0)
        relationships = int(row["relationships"] if row else 0)
        return {"node_count": nodes, "relationship_count": relationships, "can_query": nodes > 0}

    def schema(self, project_id: str) -> dict[str, Any]:
        with self._driver.session(database=self.database) as session:
            node_rows = session.run(
                "MATCH (n:GraphNode {project_id:$project_id, is_current:true}) RETURN n.object_type AS object_type, count(*) AS count ORDER BY object_type",
                project_id=project_id,
            ).data()
            rel_rows = session.run(
                "MATCH (:GraphNode {project_id:$project_id, is_current:true})-[r]->(:GraphNode {project_id:$project_id, is_current:true}) RETURN DISTINCT type(r) AS relationship_type ORDER BY relationship_type",
                project_id=project_id,
            ).data()
        return {
            "nodes": node_rows,
            "relationship_types": [str(row["relationship_type"]) for row in rel_rows],
        }

    def search(self, *, project_id: str, label: str, query: str, limit: int, dataset_version_id: str | None = None) -> list[dict[str, Any]]:
        with self._driver.session(database=self.database) as session:
            return session.run(
                """
                MATCH (n:GraphNode {project_id:$project_id, is_current:true})
                WHERE ($dataset_version_id IS NULL OR n.dataset_version_id=$dataset_version_id)
                  AND ($label='' OR toLower(n.object_type)=toLower($label))
                  AND (toLower(n.source_identity) CONTAINS toLower($search_query)
                    OR toLower(coalesce(n.display_name,'')) CONTAINS toLower($search_query)
                    OR toLower(coalesce(n.asset_id,'')) CONTAINS toLower($search_query)
                    OR toLower(coalesce(n.product_id,'')) CONTAINS toLower($search_query))
                RETURN properties(n) AS node ORDER BY n.source_identity LIMIT $limit
                """,
                project_id=project_id,
                dataset_version_id=dataset_version_id,
                label=label,
                search_query=query,
                limit=limit,
            ).data()

    def subgraph(self, *, project_id: str, identity: str, depth: int, limit: int, dataset_version_id: str | None = None) -> dict[str, Any]:
        with self._driver.session(database=self.database) as session:
            rows = session.run(
                f"""
                MATCH (root:GraphNode {{project_id:$project_id, is_current:true, source_identity:$identity}})
                WHERE ($dataset_version_id IS NULL OR root.dataset_version_id=$dataset_version_id)
                MATCH p=(root)-[*0..{depth}]-(n:GraphNode)
                WHERE n.project_id=$project_id AND n.is_current=true
                WITH p LIMIT $limit
                RETURN [node IN nodes(p) | properties(node)] AS nodes,
                       [rel IN relationships(p) | {{type:type(rel), properties:properties(rel),
                         source:startNode(rel).node_key, target:endNode(rel).node_key}}] AS relationships
                """,
                project_id=project_id,
                identity=identity,
                dataset_version_id=dataset_version_id,
                limit=limit,
            ).data()
        nodes: dict[str, dict[str, Any]] = {}
        relationships: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            for node in row.get("nodes") or []:
                nodes[str(node.get("node_key"))] = dict(node)
            for rel in row.get("relationships") or []:
                key = (str(rel.get("source")), str(rel.get("type")), str(rel.get("target")))
                relationships[key] = dict(rel)
        return {"nodes": list(nodes.values()), "relationships": list(relationships.values())}

    def relationship_query(self, *, project_id: str, identity: str | None, interests: set[str], limit: int = 20) -> list[dict[str, Any]]:
        if identity:
            root_clause = "root.source_identity=$identity"
        else:
            root_clause = "root.object_type='equipment'"
        with self._driver.session(database=self.database) as session:
            return session.run(
                f"""
                MATCH (root:GraphNode {{project_id:$project_id, is_current:true}})
                WHERE {root_clause}
                MATCH p=(root)-[*1..3]-(n:GraphNode)
                WHERE n.project_id=$project_id AND n.is_current=true
                  AND (size($interests)=0 OR n.object_type IN $interests)
                RETURN root.source_identity AS root_id,
                       n.object_type AS related_type,
                       n.source_identity AS related_id,
                       coalesce(n.display_name,n.component_label,n.product_type,n.title,n.source_identity) AS related_label,
                       [rel IN relationships(p) | type(rel)] AS relationship_path,
                       length(p) AS depth,
                       n.dataset_version_id AS dataset_version_id
                ORDER BY depth, related_type, related_id
                LIMIT $limit
                """,
                project_id=project_id,
                identity=identity,
                interests=sorted(interests),
                limit=limit,
            ).data()

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any

from .analysis_models import (
    AnalysisCreateRequest,
    AnalysisNodeResultResponse,
    AnalysisRunRequest,
    AnalysisRunResult,
    AnalysisSnapshot,
    AnalysisUpdateRequest,
)
from .analysis_repository import AnalysisRepository
from .identity import Principal
from .ontology import LinkRecord, ObjectRecord
from .ontology_service import OntologyService


class AnalysisNotFound(KeyError):
    pass


class AnalysisService:
    ALLOWED_JOIN_RELATIONSHIPS = {
        "risk_event_equipment": "RiskEvent ↔ Equipment",
        "risk_event_evidence": "RiskEvent ↔ Evidence",
        "equipment_work_order": "Equipment ↔ WorkOrder",
    }

    def __init__(
        self,
        database_target: str,
        *,
        repository: AnalysisRepository | None = None,
    ) -> None:
        self.repository = repository or AnalysisRepository(database_target)

    @staticmethod
    def _scope(principal: Principal, workspace_id: str) -> tuple[str, str]:
        if workspace_id not in principal.workspace_scopes:
            raise ValueError("workspace is outside the authenticated principal scope")
        project_id = principal.active_project_id
        if not project_id or project_id not in principal.project_scopes:
            raise ValueError("an active project scope is required")
        return principal.organization_id, project_id

    def create(self, request: AnalysisCreateRequest, principal: Principal) -> AnalysisSnapshot:
        organization_id, project_id = self._scope(principal, request.workspace_id)
        self._validate_definition(request.nodes, request.edges)
        analysis_id = request.id or self.repository.new_id("analysis")
        return self.repository.create(
            analysis_id=analysis_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=request.workspace_id,
            display_name=request.display_name,
            nodes=request.nodes,
            edges=request.edges,
            actor_user_id=principal.user_id,
            publish=request.publish,
        )

    def get(
        self,
        *,
        analysis_id: str,
        workspace_id: str,
        principal: Principal,
        version: int | None = None,
    ) -> AnalysisSnapshot:
        organization_id, project_id = self._scope(principal, workspace_id)
        snapshot = self.repository.get(
            analysis_id=analysis_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            version=version,
        )
        if snapshot is None:
            raise AnalysisNotFound(analysis_id)
        return snapshot

    def update(
        self,
        *,
        analysis_id: str,
        request: AnalysisUpdateRequest,
        principal: Principal,
    ) -> AnalysisSnapshot:
        organization_id, project_id = self._scope(principal, request.workspace_id)
        self._validate_definition(request.nodes, request.edges)
        return self.repository.update(
            analysis_id=analysis_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=request.workspace_id,
            display_name=request.display_name,
            nodes=request.nodes,
            edges=request.edges,
            actor_user_id=principal.user_id,
            base_version=request.base_version,
            publish=request.publish,
        )

    def run(
        self,
        *,
        analysis_id: str,
        request: AnalysisRunRequest,
        principal: Principal,
        ontology: OntologyService,
    ) -> AnalysisRunResult:
        organization_id, project_id = self._scope(principal, request.workspace_id)
        current = self.repository.get(
            analysis_id=analysis_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=request.workspace_id,
        )
        if current is None:
            raise AnalysisNotFound(analysis_id)
        version = self._resolve_version(current, request.version_policy, request.version)
        snapshot = self.repository.get(
            analysis_id=analysis_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=request.workspace_id,
            version=version,
        )
        if snapshot is None:
            raise AnalysisNotFound(f"{analysis_id}:v{version}")

        run_id = self.repository.new_id("analysis-run")
        started_at = self._now()
        node_results: dict[str, dict[str, Any]] = {}
        try:
            node_results = self._execute(snapshot, ontology, request.preview_limit)
            finished_at = self._now()
            payload = self.repository.record_run(
                run_id=run_id,
                analysis_id=analysis_id,
                analysis_version=version,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=request.workspace_id,
                requested_by=principal.user_id,
                status="succeeded",
                parameters=request.parameters,
                node_results=node_results,
                started_at=started_at,
                finished_at=finished_at,
            )
        except Exception as exc:
            finished_at = self._now()
            payload = self.repository.record_run(
                run_id=run_id,
                analysis_id=analysis_id,
                analysis_version=version,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=request.workspace_id,
                requested_by=principal.user_id,
                status="failed",
                parameters=request.parameters,
                node_results=node_results,
                started_at=started_at,
                finished_at=finished_at,
                error={"code": type(exc).__name__, "message": str(exc)},
            )
            return AnalysisRunResult.model_validate(payload)
        return AnalysisRunResult.model_validate(payload)

    def get_run(
        self,
        *,
        run_id: str,
        workspace_id: str,
        principal: Principal,
    ) -> AnalysisRunResult:
        organization_id, project_id = self._scope(principal, workspace_id)
        payload = self.repository.get_run(
            run_id=run_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if payload is None:
            raise AnalysisNotFound(run_id)
        return AnalysisRunResult.model_validate(payload)

    def node_result(
        self,
        *,
        analysis_id: str,
        node_id: str,
        workspace_id: str,
        version_policy: str,
        version: int | None,
        principal: Principal,
        ontology: OntologyService,
    ) -> AnalysisNodeResultResponse:
        organization_id, project_id = self._scope(principal, workspace_id)
        current = self.repository.get(
            analysis_id=analysis_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if current is None:
            raise AnalysisNotFound(analysis_id)
        resolved_version = self._resolve_version(current, version_policy, version)
        run = self.repository.latest_successful_run(
            analysis_id=analysis_id,
            analysis_version=resolved_version,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if run is None:
            run_result = self.run(
                analysis_id=analysis_id,
                request=AnalysisRunRequest(
                    workspace_id=workspace_id,
                    version_policy="pinned",
                    version=resolved_version,
                ),
                principal=principal,
                ontology=ontology,
            )
            if run_result.status != "succeeded":
                raise ValueError(run_result.error or "analysis run failed")
            run = run_result.model_dump(mode="json")
        node_result = run["node_results"].get(node_id)
        if node_result is None:
            raise AnalysisNotFound(f"{analysis_id}:{node_id}")
        return AnalysisNodeResultResponse(
            analysis_id=analysis_id,
            analysis_version=resolved_version,
            node_id=node_id,
            version_policy=version_policy,
            render_spec=node_result.get("render_spec") or {"kind": "table"},
            result=node_result,
            run_id=run["id"],
            generated_at=node_result.get("generated_at") or run.get("finished_at") or self._now(),
        )

    @staticmethod
    def _resolve_version(snapshot: AnalysisSnapshot, policy: str, version: int | None) -> int:
        if policy == "latest_published":
            if snapshot.published_version is None:
                raise ValueError("analysis has no published version")
            return snapshot.published_version
        if version is None:
            return snapshot.current_version
        if version < 1 or version > snapshot.current_version:
            raise ValueError(f"analysis version is unavailable: {version}")
        return version

    def _execute(
        self,
        snapshot: AnalysisSnapshot,
        ontology: OntologyService,
        preview_limit: int,
    ) -> dict[str, dict[str, Any]]:
        nodes = {node.id: node for node in snapshot.nodes}
        order = self._topological_order(nodes, snapshot.edges)
        predecessors: dict[str, list[str]] = defaultdict(list)
        for edge in snapshot.edges:
            predecessors[edge.target].append(edge.source)

        results: dict[str, dict[str, Any]] = {}
        for node_id in order:
            started = time.perf_counter()
            node = nodes[node_id]
            data = node.data
            kind = str(data.get("kind") or "input")
            config = data.get("config") if isinstance(data.get("config"), dict) else {}
            upstream_ids = predecessors.get(node_id, [])
            upstream_rows = self._upstream_rows(results, upstream_ids)

            if kind == "input":
                source = str(config.get("source") or "risk_event")
                object_type = "risk_event" if source in {"risk_event", "events"} else source
                rows, source_freshness = self._load_object_rows(
                    ontology,
                    workspace_id=snapshot.workspace_id,
                    object_type=object_type,
                )
            else:
                rows = upstream_rows
                source_freshness = self._oldest_freshness(results, upstream_ids)

            warnings: list[str] = []
            render_spec: dict[str, Any] = {"kind": "table"}
            if kind == "filter":
                rows = self._filter_rows(rows, config)
            elif kind == "formula":
                rows = self._formula_rows(rows, config)
                if any("now" in str(value).lower() for value in config.values()):
                    warnings.append("현재 시각에 의존하는 식은 실행 시점마다 결과가 달라질 수 있습니다.")
            elif kind == "group":
                rows = self._group_rows(rows, str(config.get("field") or "line"))
                warnings.append("Group 결과 순서는 명시적 Sort Board가 없으면 안정적으로 보장되지 않습니다.")
            elif kind == "aggregate":
                rows = self._aggregate_rows(rows, str(config.get("metric") or "average_risk"))
            elif kind in {"evidence", "join"}:
                relationship = str(config.get("relationship") or "risk_event_evidence")
                rows = self._join_rows(rows, relationship, ontology, snapshot.workspace_id)
            elif kind == "chart":
                render_spec = {
                    "kind": str(config.get("chart") or "bar"),
                    "x_field": str(config.get("x") or "line"),
                    "y_field": str(config.get("y") or "average_risk"),
                    "selectable": True,
                    "brushable": True,
                }
            elif kind == "table":
                limit = max(1, min(preview_limit, int(config.get("limit") or preview_limit)))
                rows = rows[:limit]
                render_spec = {"kind": "table", "page_size": min(limit, 100)}

            elapsed_ms = max(1, round((time.perf_counter() - started) * 1000))
            generated_at = self._now()
            result = {
                "status": "succeeded",
                "kind": kind,
                "title": str(data.get("title") or node_id),
                "rows": rows[:preview_limit],
                "row_count": len(rows),
                "columns": self._columns(rows),
                "profile": self._profile(rows),
                "quality": self._quality_summary(rows),
                "render_spec": render_spec,
                "elapsed_ms": elapsed_ms,
                "cache_hit": False,
                "generated_at": generated_at,
                "source_freshness_at": source_freshness,
                "timezone": "UTC",
                "warnings": warnings,
            }
            results[node_id] = result
        return results

    def _validate_definition(self, nodes: list[Any], edges: list[Any]) -> None:
        nodes_by_id = {node.id: node for node in nodes}
        if len(nodes_by_id) != len(nodes):
            raise ValueError("analysis node ids must be unique")
        self._topological_order(nodes_by_id, edges)
        for node in nodes:
            kind = str(node.data.get("kind") or "input")
            if kind not in {"join", "evidence"}:
                continue
            config = node.data.get("config") if isinstance(node.data.get("config"), dict) else {}
            relationship = str(config.get("relationship") or "risk_event_evidence")
            if relationship not in self.ALLOWED_JOIN_RELATIONSHIPS:
                raise ValueError(f"join relationship is not allowed: {relationship}")

    @staticmethod
    def _topological_order(nodes: dict[str, Any], edges: list[Any]) -> list[str]:
        indegree = {node_id: 0 for node_id in nodes}
        outgoing: dict[str, list[str]] = defaultdict(list)
        for edge in edges:
            if edge.source not in nodes or edge.target not in nodes:
                raise ValueError("analysis edge references an unknown node")
            outgoing[edge.source].append(edge.target)
            indegree[edge.target] += 1
        queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
        ordered: list[str] = []
        while queue:
            node_id = queue.popleft()
            ordered.append(node_id)
            for target in outgoing[node_id]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)
        if len(ordered) != len(nodes):
            raise ValueError("analysis graph must be acyclic")
        return ordered

    @staticmethod
    def _upstream_rows(results: dict[str, dict[str, Any]], upstream_ids: list[str]) -> list[dict[str, Any]]:
        if not upstream_ids:
            return []
        rows: list[dict[str, Any]] = []
        for upstream_id in upstream_ids:
            rows.extend(results.get(upstream_id, {}).get("rows", []))
        return rows

    def _load_object_rows(
        self,
        ontology: OntologyService,
        *,
        workspace_id: str,
        object_type: str,
    ) -> tuple[list[dict[str, Any]], str | None]:
        payload = ontology.query_objects(
            workspace_id=workspace_id,
            object_type=object_type,
            offset=0,
            limit=5000,
        )
        rows: list[dict[str, Any]] = []
        freshness_values: list[str] = []
        for item_payload in payload["items"]:
            item = ObjectRecord.model_validate(item_payload)
            row = {
                "object_id": item.id,
                "id": item.id,
                "object_type": item.object_type,
                "version": item.version,
                **item.properties,
            }
            if item.object_type == "risk_event":
                row["event_id"] = item.id.split(":", 1)[-1]
                traversal = ontology.traverse(
                    workspace_id=workspace_id,
                    object_id=item.id,
                    direction="incoming",
                    depth=1,
                    link_type="equipment_has_risk_event",
                )
                equipment = next((node for node in traversal.nodes if node.object_type == "equipment"), None)
                if equipment is not None:
                    row.update(
                        {
                            "equipment_id": equipment.id.split(":", 1)[-1],
                            "equipment": equipment.properties.get("display_name"),
                            "line": equipment.properties.get("line"),
                            "downtime": equipment.properties.get("estimated_downtime_minutes") or 0,
                        }
                    )
                row["risk"] = row.get("failure_probability") or 0
                row["failure_type"] = row.get("predicted_failure_type")
                row["priority_score"] = float(row.get("risk") or 0) * float(row.get("downtime") or 0)
            for key in ("observed_at", "generated_at", "created_at"):
                if isinstance(row.get(key), str):
                    freshness_values.append(row[key])
            rows.append(row)
        return rows, max(freshness_values) if freshness_values else None

    @staticmethod
    def _filter_rows(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
        field = str(config.get("field") or "status")
        operator = str(config.get("operator") or "equals")
        expected = config.get("value", "critical")

        def matches(row: dict[str, Any]) -> bool:
            current = row.get(field)
            if operator == "not_equals":
                return str(current) != str(expected)
            if operator == "greater_than":
                return AnalysisService._number(current) > AnalysisService._number(expected)
            if operator == "less_than":
                return AnalysisService._number(current) < AnalysisService._number(expected)
            if operator == "contains":
                return str(expected).lower() in str(current).lower()
            return str(current) == str(expected)

        return [row for row in rows if matches(row)]

    @staticmethod
    def _formula_rows(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
        left = str(config.get("left") or "risk")
        right = str(config.get("right") or "downtime")
        operator = str(config.get("operator") or "multiply")
        output = str(config.get("output") or "priority_score")
        result: list[dict[str, Any]] = []
        for row in rows:
            left_value = AnalysisService._number(row.get(left))
            right_value = AnalysisService._number(row.get(right))
            if operator == "add":
                value = left_value + right_value
            elif operator == "subtract":
                value = left_value - right_value
            elif operator == "divide":
                value = left_value / right_value if right_value else None
            else:
                value = left_value * right_value
            result.append({**row, output: value})
        return result

    @staticmethod
    def _group_rows(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            value = row.get(field)
            groups[str(value if value is not None else "unknown")].append(row)
        return [
            {
                "key": key,
                field: key,
                "count": len(members),
                "average_risk": sum(AnalysisService._number(item.get("risk")) for item in members) / len(members),
                "downtime": sum(AnalysisService._number(item.get("downtime")) for item in members),
            }
            for key, members in groups.items()
        ]

    @staticmethod
    def _aggregate_rows(rows: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
        if not rows:
            return []
        if metric == "count":
            return [{"metric": "count", "value": len(rows), "count": len(rows)}]
        if metric in {"average_risk", "avg_risk"}:
            value = sum(AnalysisService._number(row.get("risk", row.get("average_risk"))) for row in rows) / len(rows)
            return [{"metric": "average_risk", "value": value, "average_risk": value, "count": len(rows)}]
        if metric in {"total_downtime", "downtime"}:
            value = sum(AnalysisService._number(row.get("downtime")) for row in rows)
            return [{"metric": "total_downtime", "value": value, "downtime": value, "count": len(rows)}]
        if all("key" in row for row in rows):
            return rows
        values = [AnalysisService._number(row.get(metric)) for row in rows]
        return [{"metric": metric, "value": sum(values), metric: sum(values), "count": len(values)}]

    def _join_rows(
        self,
        rows: list[dict[str, Any]],
        relationship: str,
        ontology: OntologyService,
        workspace_id: str,
    ) -> list[dict[str, Any]]:
        if relationship not in self.ALLOWED_JOIN_RELATIONSHIPS:
            raise ValueError(f"join relationship is not allowed: {relationship}")
        enriched: list[dict[str, Any]] = []
        for row in rows:
            event_id = str(row.get("object_id") or (f"risk_event:{row.get('event_id')}" if row.get("event_id") else ""))
            if not event_id:
                continue
            if relationship == "risk_event_equipment":
                traversal = ontology.traverse(
                    workspace_id=workspace_id,
                    object_id=event_id,
                    direction="incoming",
                    depth=1,
                    link_type="equipment_has_risk_event",
                )
                targets = [node for node in traversal.nodes if node.object_type == "equipment"]
                enriched.extend({**row, **self._prefixed_properties(node, "equipment")} for node in targets)
            elif relationship == "risk_event_evidence":
                traversal = ontology.traverse(
                    workspace_id=workspace_id,
                    object_id=event_id,
                    direction="outgoing",
                    depth=1,
                    link_type="risk_event_has_evidence",
                )
                targets = [node for node in traversal.nodes if node.object_type == "evidence_package"]
                enriched.extend({**row, **self._prefixed_properties(node, "evidence")} for node in targets)
            else:
                event_traversal = ontology.traverse(
                    workspace_id=workspace_id,
                    object_id=event_id,
                    direction="outgoing",
                    depth=1,
                    link_type="risk_event_requires_inspection",
                )
                targets = [node for node in event_traversal.nodes if node.object_type == "inspection"]
                enriched.extend({**row, **self._prefixed_properties(node, "work_order")} for node in targets)
        return enriched

    @staticmethod
    def _prefixed_properties(item: ObjectRecord, prefix: str) -> dict[str, Any]:
        return {
            f"{prefix}_object_id": item.id,
            **{f"{prefix}_{key}": value for key, value in item.properties.items()},
        }

    @staticmethod
    def _columns(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        if not rows:
            return []
        keys = list(dict.fromkeys(key for row in rows[:50] for key in row))
        columns: list[dict[str, str]] = []
        for key in keys:
            value = next((row.get(key) for row in rows if row.get(key) is not None), None)
            value_type = "null"
            if isinstance(value, bool):
                value_type = "boolean"
            elif isinstance(value, (int, float)):
                value_type = "number"
            elif isinstance(value, (dict, list)):
                value_type = "object"
            elif value is not None:
                value_type = "string"
            columns.append({"name": key, "value_type": value_type})
        return columns

    @staticmethod
    def _profile(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        profile: dict[str, dict[str, Any]] = {}
        for column in AnalysisService._columns(rows):
            key = column["name"]
            values = [row.get(key) for row in rows]
            non_null = [value for value in values if value is not None]
            distinct = {AnalysisService._hashable(value) for value in non_null}
            profile[key] = {
                "null_count": len(values) - len(non_null),
                "null_rate": (len(values) - len(non_null)) / len(values) if values else 0,
                "distinct_count": len(distinct),
            }
        return profile

    @staticmethod
    def _quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        profile = AnalysisService._profile(rows)
        null_cells = sum(int(item["null_count"]) for item in profile.values())
        cell_count = len(rows) * len(profile)
        identities = [
            AnalysisService._hashable(
                row.get("event_id")
                or row.get("object_id")
                or row.get("id")
                or row
            )
            for row in rows
        ]
        return {
            "row_count": len(rows),
            "column_count": len(profile),
            "null_cell_count": null_cells,
            "null_rate": null_cells / cell_count if cell_count else 0,
            "duplicate_key_count": len(identities) - len(set(identities)),
            "computed_by": "server",
        }

    @staticmethod
    def _hashable(value: Any) -> str:
        return str(value) if not isinstance(value, (dict, list)) else repr(value)

    @staticmethod
    def _number(value: Any) -> float:
        try:
            number = float(value or 0)
            return number if math.isfinite(number) else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _oldest_freshness(results: dict[str, dict[str, Any]], node_ids: list[str]) -> str | None:
        values = [results[node_id].get("source_freshness_at") for node_id in node_ids if results.get(node_id, {}).get("source_freshness_at")]
        return min(values) if values else None

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

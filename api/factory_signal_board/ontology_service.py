from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from .contracts import DecisionRequest, NoteRequest
from .identity import AuthError, Principal
from .ontology import (
    ACTION_TYPE_BY_ID,
    LINK_TYPE_BY_ID,
    OBJECT_TYPE_BY_ID,
    ActionExecutionResult,
    ActionInvocation,
    ActionParameter,
    LinkRecord,
    ObjectRecord,
    OntologyTraversal,
)
from .ontology_adapter import (
    ManufacturingOntologyAdapter,
    source_identifier,
)
from .ontology_repository import OntologyActionRepository
from .role_workflow_repository import RoleWorkflowRepository
from .service import EventNotFound, FactorySignalService
from ontology_dashboard.ontology_instance_repository import OntologyInstanceRepository

TraversalDirection = Literal["outgoing", "incoming", "both"]


class OntologyService:
    def __init__(
        self,
        legacy_service: FactorySignalService,
        *,
        action_repository: OntologyActionRepository | None = None,
        instance_repository: OntologyInstanceRepository | None = None,
        role_workflow_repository: RoleWorkflowRepository | None = None,
    ) -> None:
        self.legacy_service = legacy_service
        repository_location = legacy_service.repository.path
        self.action_repository = action_repository or OntologyActionRepository(repository_location)
        self.instance_repository = instance_repository or OntologyInstanceRepository(repository_location)
        self.role_workflow_repository = role_workflow_repository or RoleWorkflowRepository(
            repository_location
        )
        self.adapter = ManufacturingOntologyAdapter(
            legacy_service,
            role_workflow_repository=self.role_workflow_repository,
        )

    def _require_workspace(self, workspace_id: str) -> None:
        if not self.adapter.supports_workspace(workspace_id):
            raise EventNotFound(workspace_id)

    def _sync_workspace(self, workspace_id: str) -> None:
        """Materialize the domain adapter snapshot into the persistent instance store."""
        self._require_workspace(workspace_id)
        snapshot = self.adapter.snapshot()
        self.instance_repository.replace_source_snapshot(
            workspace_id=workspace_id,
            source_system="manufacturing-predictive-maintenance-pack",
            source_revision="fixture-and-operational-v1",
            objects=snapshot.objects,
            links=snapshot.links,
        )

    def query_objects(
        self,
        *,
        workspace_id: str,
        object_type: str | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, Any]:
        self._require_workspace(workspace_id)
        if object_type is not None and object_type not in OBJECT_TYPE_BY_ID:
            raise ValueError(f"unknown object_type: {object_type}")

        self._sync_workspace(workspace_id)
        items = self.instance_repository.list_objects(
            workspace_id=workspace_id,
            object_type=object_type,
        )
        if search:
            needle = search.strip().lower()
            if needle:
                items = [item for item in items if self._matches_search(item, needle)]

        items.sort(key=lambda item: (item.object_type, item.id))
        total = len(items)
        page = items[offset : offset + limit]
        return {
            "workspace_id": workspace_id,
            "domain_pack": self.adapter.domain_pack,
            "object_type": object_type,
            "search": search,
            "offset": offset,
            "limit": limit,
            "total": total,
            "items": [item.model_dump(mode="json") for item in page],
        }

    def aggregate_objects(
        self,
        *,
        workspace_id: str,
        object_type: str,
        group_by: list[str] | None = None,
        metrics: list[str] | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate a workspace-scoped Object Set without exposing arbitrary SQL.

        Metric expressions use ``count`` or ``<operator>:<field>`` where operator is
        one of ``count``, ``sum``, ``avg``, ``min`` or ``max``. Fields are limited to
        the selected Object Type's declared properties plus ``id`` and ``object_type``.
        """
        self._require_workspace(workspace_id)
        definition = OBJECT_TYPE_BY_ID.get(object_type)
        if definition is None:
            raise ValueError(f"unknown object_type: {object_type}")

        allowed_fields = {"id", "object_type", *[item.id for item in definition.properties]}
        groups = list(dict.fromkeys(group_by or []))
        for field in groups:
            if field not in allowed_fields:
                raise ValueError(f"unknown group_by field for {object_type}: {field}")

        metric_specs = metrics or ["count"]
        parsed_metrics: list[tuple[str, str | None, str]] = []
        for raw_metric in metric_specs:
            operator, separator, field = raw_metric.partition(":")
            operator = operator.strip().lower()
            field = field.strip() if separator else ""
            if operator not in {"count", "sum", "avg", "min", "max"}:
                raise ValueError(f"unsupported aggregate operator: {operator}")
            if operator == "count" and not field:
                parsed_metrics.append((operator, None, "count"))
                continue
            if not field or field not in allowed_fields:
                raise ValueError(f"unknown aggregate field for {object_type}: {field or raw_metric}")
            parsed_metrics.append((operator, field, f"{operator}_{field}"))

        self._sync_workspace(workspace_id)
        items = self.instance_repository.list_objects(
            workspace_id=workspace_id,
            object_type=object_type,
        )
        if search:
            needle = search.strip().lower()
            if needle:
                items = [item for item in items if self._matches_search(item, needle)]

        grouped: dict[tuple[Any, ...], list[ObjectRecord]] = {}
        for item in items:
            key = tuple(self._object_field(item, field) for field in groups)
            grouped.setdefault(key, []).append(item)
        if not groups and not grouped:
            grouped[()] = []

        rows: list[dict[str, Any]] = []
        for key, members in sorted(grouped.items(), key=lambda pair: tuple(str(value) for value in pair[0])):
            row = {field: key[index] for index, field in enumerate(groups)}
            for operator, field, alias in parsed_metrics:
                if operator == "count":
                    if field is None:
                        row[alias] = len(members)
                    else:
                        row[alias] = sum(self._object_field(item, field) is not None for item in members)
                    continue
                numeric_values = [
                    value
                    for item in members
                    if isinstance((value := self._object_field(item, field or "")), (int, float))
                    and not isinstance(value, bool)
                ]
                if not numeric_values:
                    row[alias] = None
                elif operator == "sum":
                    row[alias] = sum(numeric_values)
                elif operator == "avg":
                    row[alias] = sum(numeric_values) / len(numeric_values)
                elif operator == "min":
                    row[alias] = min(numeric_values)
                else:
                    row[alias] = max(numeric_values)
            rows.append(row)

        return {
            "workspace_id": workspace_id,
            "object_type": object_type,
            "group_by": groups,
            "metrics": metric_specs,
            "source_rows": len(items),
            "row_count": len(rows),
            "rows": rows,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        }

    @staticmethod
    def _object_field(item: ObjectRecord, field: str) -> Any:
        if field == "id":
            return item.id
        if field == "object_type":
            return item.object_type
        return item.properties.get(field)

    @staticmethod
    def _matches_search(item: ObjectRecord, needle: str) -> bool:
        haystack = json.dumps(
            {"id": item.id, "object_type": item.object_type, "properties": item.properties},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).lower()
        return needle in haystack

    def get_object(self, *, workspace_id: str, object_id: str) -> ObjectRecord:
        self._sync_workspace(workspace_id)
        item = self.instance_repository.get_object(
            workspace_id=workspace_id,
            object_id=object_id,
        )
        if item is None:
            raise EventNotFound(object_id)
        return item

    def traverse(
        self,
        *,
        workspace_id: str,
        object_id: str,
        direction: TraversalDirection = "outgoing",
        depth: int = 1,
        link_type: str | None = None,
    ) -> OntologyTraversal:
        self._require_workspace(workspace_id)
        if link_type is not None and link_type not in LINK_TYPE_BY_ID:
            raise ValueError(f"unknown link_type: {link_type}")

        self._sync_workspace(workspace_id)
        objects = self.instance_repository.list_objects(workspace_id=workspace_id)
        object_index = {item.id: item for item in objects}
        try:
            root = object_index[object_id]
        except KeyError as exc:
            raise EventNotFound(object_id) from exc

        candidate_edges = self.instance_repository.list_links(
            workspace_id=workspace_id,
            link_type=link_type,
        )
        visited_ids = {root.id}
        frontier = {root.id}
        selected_edges: dict[str, LinkRecord] = {}

        for _ in range(depth):
            next_frontier: set[str] = set()
            for edge in candidate_edges:
                neighbor_id = self._neighbor(edge, frontier, direction)
                if neighbor_id is None:
                    continue
                selected_edges[edge.id] = edge
                if neighbor_id not in visited_ids:
                    visited_ids.add(neighbor_id)
                    next_frontier.add(neighbor_id)
            if not next_frontier:
                break
            frontier = next_frontier

        nodes = [object_index[item_id] for item_id in visited_ids if item_id != root.id]
        nodes.sort(key=lambda item: (item.object_type, item.id))
        edges = sorted(selected_edges.values(), key=lambda item: item.id)
        return OntologyTraversal(
            root=root,
            nodes=nodes,
            edges=edges,
            direction=direction,
            depth=depth,
        )

    @staticmethod
    def _neighbor(
        edge: LinkRecord,
        frontier: set[str],
        direction: TraversalDirection,
    ) -> str | None:
        if direction in {"outgoing", "both"} and edge.source_object_id in frontier:
            return edge.target_object_id
        if direction in {"incoming", "both"} and edge.target_object_id in frontier:
            return edge.source_object_id
        return None

    def invoke(self, invocation: ActionInvocation, principal: Principal) -> ActionExecutionResult:
        self._require_workspace(invocation.workspace_id)
        scope = self.action_repository.project_context.resolve(invocation.workspace_id)
        if scope.organization_id != principal.organization_id:
            raise AuthError(403, "tenant_scope_denied", "다른 조직의 resource에는 접근할 수 없습니다.")
        if scope.project_id not in principal.project_scopes:
            raise AuthError(403, "project_scope_denied", "해당 Project에 접근할 수 없습니다.")
        if principal.active_project_id and scope.project_id != principal.active_project_id:
            raise AuthError(409, "active_project_mismatch", "먼저 해당 Project를 활성화해야 합니다.")
        if invocation.workspace_id not in principal.workspace_scopes:
            raise AuthError(403, "workspace_scope_denied", "해당 workspace에 접근할 수 없습니다.")

        action_type = ACTION_TYPE_BY_ID.get(invocation.action_type)
        if action_type is None:
            raise ValueError(f"unknown action_type: {invocation.action_type}")
        for permission in action_type.required_permissions:
            if permission not in principal.permissions:
                raise AuthError(403, "permission_denied", f"권한이 필요합니다: {permission}")

        target_type = self._target_object_type(invocation)
        if target_type != action_type.object_type:
            raise ValueError(
                f"action {action_type.id} requires object_type {action_type.object_type}, "
                f"received {target_type}"
            )
        self._validate_parameters(action_type.parameters, invocation.parameters)

        canonical_request = {
            "action_type": invocation.action_type,
            "object_id": invocation.object_id,
            "workspace_id": invocation.workspace_id,
            "parameters": invocation.parameters,
        }
        request_hash = hashlib.sha256(
            json.dumps(canonical_request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        reserved, created = self.action_repository.reserve(
            idempotency_key=invocation.idempotency_key,
            workspace_id=invocation.workspace_id,
            action_type=invocation.action_type,
            object_id=invocation.object_id,
            actor_user_id=principal.user_id,
            actor_display_name=principal.display_name,
            request_hash=request_hash,
            request=canonical_request,
        )
        if not created:
            return self._replay_or_reject(reserved, request_hash)

        try:
            event_id, result = self._execute(invocation, principal)
            audit = self.legacy_service.repository.record_audit(
                event_id=event_id,
                run_id=reserved["id"],
                action=f"ontology.action.{invocation.action_type}",
                model_version=None,
                payload={
                    "invocation_id": reserved["id"],
                    "workspace_id": invocation.workspace_id,
                    "object_id": invocation.object_id,
                    "actor_user_id": principal.user_id,
                    "actor_display_name": principal.display_name,
                    "parameters": invocation.parameters,
                    "result": result,
                },
            )
            completed = self.action_repository.succeed(
                reserved["id"],
                project_id=reserved["project_id"],
                result=result,
                audit_id=audit["id"],
            )
        except Exception as exc:
            self.action_repository.fail(
                reserved["id"],
                project_id=reserved["project_id"],
                code=type(exc).__name__,
                message=str(exc),
            )
            raise

        return self._execution_result(completed, replayed=False)

    def _target_object_type(self, invocation: ActionInvocation) -> str:
        try:
            return self.get_object(
                workspace_id=invocation.workspace_id,
                object_id=invocation.object_id,
            ).object_type
        except EventNotFound:
            work_order_actions = {
                "record_work_order_note",
                "complete_work_order",
                "report_work_order_issue",
                "mark_work_order_blocked",
            }
            inspection_actions = {
                "record_inspection_note",
                "complete_inspection",
                "report_inspection_issue",
                "mark_inspection_blocked",
            }
            if invocation.action_type in work_order_actions:
                event_id = source_identifier(invocation.object_id, "work_order")
                object_type = "work_order"
            elif invocation.action_type in inspection_actions:
                event_id = source_identifier(invocation.object_id, "inspection")
                object_type = "inspection"
            else:
                raise
            self.get_object(
                workspace_id=invocation.workspace_id,
                object_id=f"risk_event:{event_id}",
            )
            return object_type

    def _execute(
        self,
        invocation: ActionInvocation,
        principal: Principal,
    ) -> tuple[str, dict[str, Any]]:
        if invocation.action_type == "record_operational_decision":
            event_id = source_identifier(invocation.object_id, "risk_event")
            result = self.legacy_service.decide(
                event_id,
                DecisionRequest(
                    actor=principal.display_name,
                    decision=invocation.parameters["decision"],
                    note=invocation.parameters.get("note", ""),
                ),
            )
            return event_id, result

        note_action_types = {
            "record_work_order_note": "work_order",
            "record_inspection_note": "inspection",
        }
        if invocation.action_type in note_action_types:
            event_id = source_identifier(invocation.object_id, note_action_types[invocation.action_type])
            result = self.legacy_service.note(
                event_id,
                NoteRequest(
                    actor=principal.display_name,
                    body=invocation.parameters["body"],
                ),
            )
            return event_id, result

        field_action_by_type = {
            "complete_work_order": ("complete", "work_order"),
            "report_work_order_issue": ("issue_found", "work_order"),
            "mark_work_order_blocked": ("blocked", "work_order"),
            "complete_inspection": ("complete", "inspection"),
            "report_inspection_issue": ("issue_found", "inspection"),
            "mark_inspection_blocked": ("blocked", "inspection"),
        }
        if invocation.action_type in field_action_by_type:
            action, object_type = field_action_by_type[invocation.action_type]
            event_id = source_identifier(invocation.object_id, object_type)
            self.legacy_service._fixture(event_id)
            checklist = invocation.parameters.get("checklist", [])
            note = invocation.parameters.get("note", "")
            if action == "complete" and not checklist:
                raise ValueError("complete_inspection requires at least one checklist item")
            if action in {"issue_found", "blocked"} and not note.strip():
                raise ValueError(f"{invocation.action_type} requires a note")
            result = self.role_workflow_repository.record_field_action(
                workspace_id=invocation.workspace_id,
                event_id=event_id,
                action=action,
                actor_user_id=principal.user_id,
                actor_display_name=principal.display_name,
                payload={
                    "workspace_id": invocation.workspace_id,
                    "event_id": event_id,
                    "action": action,
                    "checklist": checklist,
                    "measurements": invocation.parameters.get("measurements", {}),
                    "photo_metadata": invocation.parameters.get("photo_metadata", []),
                    "note": note,
                    "location": invocation.parameters.get("location"),
                    "safety_risk": invocation.parameters.get("safety_risk", False),
                },
            )
            return event_id, result

        raise ValueError(f"action executor is not registered: {invocation.action_type}")

    @staticmethod
    def _validate_parameters(
        definitions: list[ActionParameter],
        parameters: dict[str, Any],
    ) -> None:
        definition_by_id = {item.id: item for item in definitions}
        unknown = sorted(set(parameters) - set(definition_by_id))
        if unknown:
            raise ValueError(f"unknown action parameters: {', '.join(unknown)}")

        missing = sorted(
            item.id for item in definitions if item.required and item.id not in parameters
        )
        if missing:
            raise ValueError(f"missing action parameters: {', '.join(missing)}")

        for parameter_id, value in parameters.items():
            OntologyService._validate_parameter_type(definition_by_id[parameter_id], value)

    @staticmethod
    def _validate_parameter_type(definition: ActionParameter, value: Any) -> None:
        valid = False
        if definition.value_type == "string":
            valid = isinstance(value, str)
        elif definition.value_type == "number":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif definition.value_type == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif definition.value_type == "boolean":
            valid = isinstance(value, bool)
        elif definition.value_type == "datetime":
            valid = isinstance(value, str)
            if valid:
                try:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    valid = False
        elif definition.value_type == "object":
            valid = isinstance(value, dict)
        elif definition.value_type == "array":
            valid = isinstance(value, list)

        if not valid:
            raise ValueError(
                f"action parameter {definition.id} must be {definition.value_type}"
            )

    def _replay_or_reject(
        self,
        existing: dict[str, Any],
        request_hash: str,
    ) -> ActionExecutionResult:
        if existing["request_hash"] != request_hash:
            raise AuthError(
                409,
                "idempotency_key_conflict",
                "같은 idempotency_key가 다른 Action 요청에 이미 사용되었습니다.",
            )
        if existing["state"] == "succeeded":
            return self._execution_result(existing, replayed=True)
        if existing["state"] == "running":
            raise AuthError(409, "action_in_progress", "동일한 Action 요청이 처리 중입니다.")
        raise AuthError(
            409,
            "prior_action_failed",
            "동일한 idempotency_key의 이전 Action 실행이 실패했습니다.",
        )

    @staticmethod
    def _execution_result(
        record: dict[str, Any],
        *,
        replayed: bool,
    ) -> ActionExecutionResult:
        result = record.get("result")
        audit_id = record.get("audit_id")
        completed_at = record.get("completed_at")
        if result is None or audit_id is None or completed_at is None:
            raise RuntimeError("succeeded Action invocation is missing its persisted result")
        return ActionExecutionResult(
            invocation_id=record["id"],
            action_type=record["action_type"],
            object_id=record["object_id"],
            workspace_id=record["workspace_id"],
            replayed=replayed,
            result=result,
            audit_id=audit_id,
            created_at=record["created_at"],
            completed_at=completed_at,
        )

    def list_action_invocations(
        self,
        *,
        workspace_id: str,
        object_id: str,
    ) -> list[dict[str, Any]]:
        self.get_object(workspace_id=workspace_id, object_id=object_id)
        records = self.action_repository.list_for_object(
            workspace_id=workspace_id,
            object_id=object_id,
        )
        return [
            {
                "invocation_id": item["id"],
                "action_type": item["action_type"],
                "object_id": item["object_id"],
                "workspace_id": item["workspace_id"],
                "actor_user_id": item["actor_user_id"],
                "actor_display_name": item["actor_display_name"],
                "state": item["state"],
                "result": item["result"],
                "error": item["error"],
                "audit_id": item["audit_id"],
                "created_at": item["created_at"],
                "completed_at": item["completed_at"],
            }
            for item in records
        ]

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from .catalog import (
    BOARD_CATALOG,
    BOARD_DEFINITION_BY_ID,
    PARAMETER_DEFINITIONS,
)
from .dashboard_schema import (
    BoardCatalogDefinition,
    DashboardBoard,
    DashboardBoardQueryRequest,
    DashboardCatalogResponse,
    DashboardPreferenceSaveRequest,
    DashboardShareCreateRequest,
    DashboardShareCreated,
    DashboardSharePayload,
    DashboardTab,
    DashboardTemplatePublishRequest,
    DashboardTemplateSnapshot,
    DependencyEdge,
    ResolvedDashboard,
    SavedViewCreateRequest,
    SavedViewRecord,
)
from .dashboard_exception import (
    DashboardAccessError,
    DashboardNotFoundError,
    DashboardPreferenceConflict,
)
from .ports import DashboardPrincipal, DashboardRepositoryPort, OntologyQueryPort
from .visualizations import recommend_visualization

UNSAFE_TEXT = re.compile(r"<[^>]+>|javascript\s*:|on[a-z]+\s*=", re.IGNORECASE)


@dataclass(slots=True)
class _PreviewPrincipal:
    user_id: str
    roles: list[str]
    permissions: list[str] = field(default_factory=list)
    workspace_scopes: list[str] = field(default_factory=list)
    active_project_id: str | None = None


class DashboardService:
    def __init__(
        self,
        *,
        repository: DashboardRepositoryPort,
    ) -> None:
        self.repository = repository

    @staticmethod
    def role_for(principal: DashboardPrincipal) -> str:
        if not principal.roles:
            raise DashboardAccessError(403, "role_context_denied", "Dashboard 역할이 지정되지 않았습니다.")
        return principal.roles[0]

    def current_template(self, *, workspace_id: str, role_code: str) -> DashboardTemplateSnapshot:
        template = self.repository.get_current_template(
            workspace_id=workspace_id,
            role_code=role_code,
        )
        if template is None:
            raise DashboardNotFoundError(f"dashboard template {workspace_id}:{role_code}")
        return template

    def resolve(self, *, principal: DashboardPrincipal, workspace_id: str) -> ResolvedDashboard:
        role_code = self.role_for(principal)
        template = self.current_template(workspace_id=workspace_id, role_code=role_code)
        preference = self.repository.get_preferences(
            user_id=principal.user_id,
            workspace_id=workspace_id,
            template_id=template.template_id,
        )
        return self._resolve_template(
            principal=principal,
            template=template,
            preference=preference,
        )

    def query_board(
        self,
        *,
        principal: DashboardPrincipal,
        dashboard_id: str,
        board_id: str,
        request: DashboardBoardQueryRequest,
        ontology: OntologyQueryPort,
        event_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        resolved = self.resolve(principal=principal, workspace_id=request.workspace_id)
        if dashboard_id != resolved.dashboard_id:
            raise DashboardNotFoundError(dashboard_id)
        board = next(
            (item for tab in resolved.tabs for item in tab.boards if item.id == board_id),
            None,
        )
        if board is None:
            raise DashboardNotFoundError(board_id)
        definition = BOARD_DEFINITION_BY_ID.get(board.definition_id)
        if definition is None:
            raise ValueError(f"unknown board definition: {board.definition_id}")
        if board.source is not None:
            raise ValueError("analysis-backed boards must use the Analysis node-result API")

        object_type = str(board.bindings.get("object_type") or "")
        if not object_type and definition.default_data_binding:
            object_type = str(definition.default_data_binding.get("object_type") or "")
        if not object_type:
            object_type = "risk_event" if "risk_event" in definition.object_types else (definition.object_types[0] if definition.object_types else "risk_event")
        render_spec = copy.deepcopy(definition.default_render_spec) if definition.default_render_spec else self._default_render_spec(definition.renderer)
        status_filter = request.parameter_state.get("status_filter")
        requires_filter_scan = (
            (isinstance(status_filter, str) and status_filter not in {"", "all"})
            or bool(request.selection_filters)
            or render_spec.get("kind") != "table"
        )
        payload = ontology.query_objects(
            workspace_id=request.workspace_id,
            object_type=object_type,
            search=request.search,
            offset=0 if requires_filter_scan else request.offset,
            limit=5000 if requires_filter_scan else request.limit,
        )
        rows = [self._dashboard_object_row(item, ontology, request.workspace_id) for item in payload["items"]]
        if object_type == "risk_event" and event_rows is not None and not rows:
            rows = [self._dashboard_event_row(item) for item in event_rows]
            if request.search:
                needle = request.search.casefold()
                rows = [row for row in rows if needle in json.dumps(row, ensure_ascii=False).casefold()]
            requires_filter_scan = True

        if isinstance(status_filter, str) and status_filter not in {"", "all"}:
            rows = [row for row in rows if str(row.get("status")) == status_filter]
        for selection in request.selection_filters:
            rows = [row for row in rows if self._selection_matches(row, selection.field, selection.operator, selection.values)]

        total = len(rows) if requires_filter_scan else int(payload["total"])
        matching_object_ids = [
            str(row.get("event_id") or row.get("object_id") or row.get("id"))
            for row in rows
            if row.get("event_id") or row.get("object_id") or row.get("id")
        ]
        page = rows[request.offset : request.offset + request.limit] if requires_filter_scan else rows
        freshness_values = [
            str(row[key])
            for row in page
            for key in ("observed_at", "generated_at", "created_at")
            if isinstance(row.get(key), str)
        ]
        visualization = recommend_visualization(page, render_spec)
        return {
            "board_id": board_id,
            "rows": page,
            "row_count": total,
            "matching_object_ids": matching_object_ids,
            "offset": request.offset,
            "limit": request.limit,
            "render_spec": render_spec,
            "field_profile": [item.model_dump(mode="json") for item in visualization.profile],
            "visualization_recommendation": visualization.model_dump(mode="json"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_freshness_at": max(freshness_values) if freshness_values else None,
            "timezone": "UTC",
            "warnings": [],
        }

    @staticmethod
    def _dashboard_event_row(event: dict[str, Any]) -> dict[str, Any]:
        equipment = event.get("equipment") or {}
        event_id = str(event.get("event_id") or "")
        return {
            "object_id": f"risk_event:{event_id}",
            "id": f"risk_event:{event_id}",
            "object_type": "risk_event",
            "event_id": event_id,
            "equipment_id": equipment.get("equipment_id"),
            "equipment": equipment.get("display_name"),
            "line": equipment.get("line"),
            "status": event.get("status"),
            "failure_probability": event.get("failure_probability"),
            "risk": event.get("failure_probability") or 0,
            "predicted_failure_type": event.get("predicted_failure_type"),
            "failure_type": event.get("predicted_failure_type"),
            "confidence": event.get("confidence"),
            "recommended_decision": event.get("recommended_decision"),
            "downtime": equipment.get("estimated_downtime_minutes") or 0,
        }

    @staticmethod
    def _dashboard_object_row(item_payload: dict[str, Any], ontology: OntologyQueryPort, workspace_id: str) -> dict[str, Any]:
        row = {
            "object_id": item_payload["id"],
            "id": item_payload["id"],
            "object_type": item_payload["object_type"],
            **item_payload.get("properties", {}),
        }
        if item_payload["object_type"] == "risk_event":
            row["event_id"] = item_payload["id"].split(":", 1)[-1]
            row["risk"] = row.get("failure_probability") or 0
            row["failure_type"] = row.get("predicted_failure_type")
            traversal = ontology.traverse(
                workspace_id=workspace_id,
                object_id=item_payload["id"],
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
        return row

    @staticmethod
    def _selection_matches(row: dict[str, Any], field: str, operator: str, values: list[Any]) -> bool:
        current = row.get(field)
        if operator == "eq":
            return bool(values) and str(current) == str(values[0])
        if operator == "in":
            return str(current) in {str(value) for value in values}
        try:
            numeric = float(current)
            if operator == "gte":
                return bool(values) and numeric >= float(values[0])
            if operator == "lte":
                return bool(values) and numeric <= float(values[0])
            if operator == "between":
                return len(values) >= 2 and float(values[0]) <= numeric <= float(values[1])
        except (TypeError, ValueError):
            return False
        return True

    @staticmethod
    def _default_render_spec(renderer: str) -> dict[str, Any]:
        if renderer == "RiskTrendWorkbench":
            return {"kind": "bar", "x_field": "equipment", "y_field": "risk", "selectable": True, "brushable": True}
        if renderer == "OperationsKpi":
            return {"kind": "metric", "value_field": "risk"}
        return {"kind": "table", "page_size": 100}

    def preview(
        self,
        *,
        workspace_id: str,
        role_code: str,
        version: int | None = None,
    ) -> ResolvedDashboard:
        template = (
            self.repository.get_template_version(
                workspace_id=workspace_id,
                role_code=role_code,
                version=version,
            )
            if version is not None
            else self.repository.get_current_template(
                workspace_id=workspace_id,
                role_code=role_code,
            )
        )
        if template is None:
            raise DashboardNotFoundError(f"dashboard template {workspace_id}:{role_code}:{version or 'current'}")
        preview_principal = _PreviewPrincipal(
            user_id="template-preview",
            roles=[role_code],
            permissions=[],
            workspace_scopes=[workspace_id],
            active_project_id=None,
        )
        return self._resolve_template(principal=preview_principal, template=template, preference=None)

    def _resolve_template(
        self,
        *,
        principal: DashboardPrincipal,
        template: DashboardTemplateSnapshot,
        preference: dict[str, Any] | None,
    ) -> ResolvedDashboard:
        tabs = [DashboardTab.model_validate(tab.model_dump(mode="python")) for tab in template.tabs]
        parameter_state = {
            item.id: copy.deepcopy(item.default_value) for item in template.parameter_definitions
        }
        active_tab_id = tabs[0].id if tabs else ""
        revision = 0
        preference_template_version: int | None = None
        merge_notices: list[str] = []

        if preference is not None:
            revision = int(preference["revision"])
            preference_template_version = int(preference["template_version"])
            payload = preference["payload"]
            tabs = self._apply_preference_payload(tabs=tabs, payload=payload)
            parameter_state.update(copy.deepcopy(payload.get("parameter_state", {})))
            active_tab_id = str(payload.get("active_tab_id") or active_tab_id)
            if preference_template_version < template.version:
                merge_notices.append(
                    f"역할 template v{preference_template_version}의 사용자 override를 v{template.version}에 병합했습니다."
                )

        tabs = self._normalize_orders(tabs)
        visible_tabs = [tab for tab in tabs if not tab.hidden]
        if active_tab_id not in {tab.id for tab in visible_tabs}:
            active_tab_id = visible_tabs[0].id if visible_tabs else ""
        self._validate_parameter_state(template, parameter_state)
        graph = self._dependency_graph(tabs)
        return ResolvedDashboard(
            dashboard_id=f"dashboard:{principal.user_id}:{template.workspace_id}",
            template_id=template.template_id,
            template_version=template.version,
            preference_revision=revision,
            preference_template_version=preference_template_version,
            workspace_id=template.workspace_id,
            role_code=template.role_code,
            display_name=template.display_name,
            tabs=tabs,
            active_tab_id=active_tab_id,
            parameter_state=parameter_state,
            parameter_definitions=template.parameter_definitions,
            dependency_graph=graph,
            merge_notices=merge_notices,
        )

    def save_preferences(
        self,
        *,
        principal: DashboardPrincipal,
        request: DashboardPreferenceSaveRequest,
    ) -> ResolvedDashboard:
        role_code = self.role_for(principal)
        template = self.current_template(workspace_id=request.workspace_id, role_code=role_code)
        normalized_tabs = self._validate_submitted_dashboard(
            role_code=role_code,
            template=template,
            tabs=request.tabs,
            active_tab_id=request.active_tab_id,
            parameter_state=request.parameter_state,
            enforce_mandatory=True,
        )
        payload = self._preference_payload_from_tabs(
            template=template,
            tabs=normalized_tabs,
            active_tab_id=request.active_tab_id,
            parameter_state=request.parameter_state,
        )
        try:
            preference = self.repository.save_preferences(
                user_id=principal.user_id,
                workspace_id=request.workspace_id,
                template_id=template.template_id,
                template_version=template.version,
                base_revision=request.base_revision,
                payload=payload,
            )
        except DashboardPreferenceConflict as exc:
            raise DashboardAccessError(
                409,
                "dashboard_revision_conflict",
                "다른 세션에서 Dashboard 설정이 변경되었습니다. 최신 상태를 다시 불러오세요.",
            ) from exc
        return self._resolve_template(principal=principal, template=template, preference=preference)

    def restore_defaults(self, *, principal: DashboardPrincipal, workspace_id: str) -> ResolvedDashboard:
        role_code = self.role_for(principal)
        template = self.current_template(workspace_id=workspace_id, role_code=role_code)
        self.repository.delete_preferences(
            user_id=principal.user_id,
            workspace_id=workspace_id,
            template_id=template.template_id,
        )
        return self._resolve_template(principal=principal, template=template, preference=None)

    def catalog(
        self,
        *,
        principal: DashboardPrincipal,
        query: str | None = None,
        category: str | None = None,
        role_code: str | None = None,
    ) -> DashboardCatalogResponse:
        principal_role = self.role_for(principal)
        role_code = role_code or principal_role
        if role_code != principal_role and "dashboards.templates.manage" not in principal.permissions:
            raise DashboardAccessError(403, "role_context_denied", "다른 역할의 Board Catalog를 조회할 수 없습니다.")
        needle = (query or "").strip().lower()
        items: list[BoardCatalogDefinition] = []
        for definition in BOARD_CATALOG:
            if role_code not in definition.allowed_roles:
                continue
            if category and definition.category != category:
                continue
            if needle:
                haystack = f"{definition.display_name} {definition.description} {definition.id}".lower()
                if needle not in haystack:
                    continue
            items.append(definition)
        categories = list(dict.fromkeys(item.category for item in items))
        return DashboardCatalogResponse(items=items, categories=categories)

    def create_saved_view(
        self,
        *,
        principal: DashboardPrincipal,
        request: SavedViewCreateRequest,
    ) -> SavedViewRecord:
        role_code = self.role_for(principal)
        template = self.current_template(workspace_id=request.workspace_id, role_code=role_code)
        tabs = self._validate_submitted_dashboard(
            role_code=role_code,
            template=template,
            tabs=request.tabs,
            active_tab_id=request.active_tab_id,
            parameter_state=request.parameter_state,
            enforce_mandatory=False,
        )
        return self.repository.create_saved_view(
            user_id=principal.user_id,
            workspace_id=request.workspace_id,
            name=request.name,
            payload={
                "active_tab_id": request.active_tab_id,
                "tabs": [tab.model_dump(mode="json") for tab in tabs],
                "parameter_state": request.parameter_state,
            },
        )

    def list_saved_views(self, *, principal: DashboardPrincipal, workspace_id: str) -> list[SavedViewRecord]:
        return self.repository.list_saved_views(
            user_id=principal.user_id,
            workspace_id=workspace_id,
        )

    def get_saved_view(self, *, principal: DashboardPrincipal, view_id: str) -> SavedViewRecord:
        record = self.repository.get_saved_view(
            view_id=view_id,
            user_id=principal.user_id,
            project_id=principal.active_project_id,
        )
        if record is None or record.workspace_id not in principal.workspace_scopes:
            raise DashboardNotFoundError(view_id)
        return record

    def delete_saved_view(self, *, principal: DashboardPrincipal, view_id: str) -> None:
        if not self.repository.delete_saved_view(
            view_id=view_id,
            user_id=principal.user_id,
            project_id=principal.active_project_id,
        ):
            raise DashboardNotFoundError(view_id)

    def validate_template_draft(
        self,
        *,
        role_code: str,
        template: DashboardTemplateSnapshot,
        request: DashboardTemplatePublishRequest,
    ) -> list[DashboardTab]:
        return self._validate_submitted_dashboard(
            role_code=role_code,
            template=template,
            tabs=request.tabs,
            active_tab_id=request.tabs[0].id if request.tabs else "",
            parameter_state={},
            enforce_mandatory=True,
        )

    def publish_template(
        self,
        *,
        principal: DashboardPrincipal,
        target_role: str,
        request: DashboardTemplatePublishRequest,
    ) -> DashboardTemplateSnapshot:
        current = self.repository.get_current_template(
            workspace_id=request.workspace_id,
            role_code=target_role,
        )
        if current is None:
            raise DashboardNotFoundError(f"dashboard template {request.workspace_id}:{target_role}")
        tabs = self.validate_template_draft(
            role_code=target_role,
            template=current,
            request=request,
        )
        published_tabs = [
            DashboardTab.model_validate(
                {
                    **tab.model_dump(mode="python"),
                    "custom": False,
                    "boards": [
                        {**board.model_dump(mode="python"), "custom": False}
                        for board in tab.boards
                    ],
                }
            )
            for tab in tabs
        ]
        mandatory_board_ids = [
            board.id for tab in published_tabs for board in tab.boards if board.mandatory
        ]
        parameter_definitions = request.parameter_definitions or current.parameter_definitions
        return self.repository.publish_template(
            workspace_id=request.workspace_id,
            role_code=target_role,
            display_name=request.display_name,
            actor_user_id=principal.user_id,
            snapshot_payload={
                "tabs": [tab.model_dump(mode="json") for tab in published_tabs],
                "mandatory_board_ids": mandatory_board_ids,
                "parameter_definitions": [
                    item.model_dump(mode="json") for item in parameter_definitions
                ],
            },
        )

    def create_share(
        self,
        *,
        principal: DashboardPrincipal,
        request: DashboardShareCreateRequest,
        validate_event: Callable[[str], None] | None = None,
    ) -> DashboardShareCreated:
        role_code = self.role_for(principal)
        template = self.current_template(workspace_id=request.workspace_id, role_code=role_code)
        self._validate_parameter_state(template, request.parameter_state)
        self._validate_shared_objects(request.parameter_state, validate_event)
        tab_ids = {tab.id for tab in template.tabs}
        if request.active_tab_id not in tab_ids:
            preference = self.repository.get_preferences(
                user_id=principal.user_id,
                workspace_id=request.workspace_id,
                template_id=template.template_id,
            )
            resolved = self._resolve_template(principal=principal, template=template, preference=preference)
            if request.active_tab_id not in {tab.id for tab in resolved.tabs}:
                raise ValueError("share active_tab_id does not exist")
        token, record = self.repository.create_share(
            owner_user_id=principal.user_id,
            workspace_id=request.workspace_id,
            payload={
                "active_tab_id": request.active_tab_id,
                "parameter_state": request.parameter_state,
            },
            expires_in_hours=request.expires_in_hours,
        )
        return DashboardShareCreated(
            token=token,
            path=f"/app?share={token}",
            workspace_id=request.workspace_id,
            active_tab_id=request.active_tab_id,
            parameter_state=request.parameter_state,
            expires_at=record["expires_at"],
        )

    def resolve_share(
        self,
        *,
        token: str,
        validate_event: Callable[[str], None] | None = None,
    ) -> DashboardSharePayload:
        record = self.repository.get_share(token)
        if record is None:
            raise DashboardNotFoundError("dashboard share")
        payload = record["payload"]
        parameter_state = payload.get("parameter_state", {})
        self._validate_shared_objects(parameter_state, validate_event)
        return DashboardSharePayload(
            workspace_id=record["workspace_id"],
            active_tab_id=payload["active_tab_id"],
            parameter_state=parameter_state,
            owner_user_id=record["owner_user_id"],
            created_at=record["created_at"],
            expires_at=record["expires_at"],
        )

    @staticmethod
    def _validate_shared_objects(
        parameter_state: dict[str, Any],
        validate_event: Callable[[str], None] | None,
    ) -> None:
        if validate_event is None:
            return
        event_id = parameter_state.get("selected_event_id")
        if isinstance(event_id, str) and event_id:
            validate_event(event_id)

    def _validate_submitted_dashboard(
        self,
        *,
        role_code: str,
        template: DashboardTemplateSnapshot,
        tabs: list[DashboardTab],
        active_tab_id: str,
        parameter_state: dict[str, Any],
        enforce_mandatory: bool,
    ) -> list[DashboardTab]:
        normalized = self._normalize_orders(
            [DashboardTab.model_validate(tab.model_dump(mode="python")) for tab in tabs]
        )
        tab_ids = [tab.id for tab in normalized]
        if len(tab_ids) != len(set(tab_ids)):
            raise ValueError("dashboard tab IDs must be unique")
        board_ids = [board.id for tab in normalized for board in tab.boards]
        if len(board_ids) != len(set(board_ids)):
            raise ValueError("dashboard board IDs must be unique")
        if not normalized:
            raise ValueError("dashboard requires at least one tab")
        if active_tab_id and active_tab_id not in set(tab_ids):
            raise ValueError("active_tab_id does not exist")

        for tab in normalized:
            self._validate_plain_text(tab.title, field="tab title")
            for board in tab.boards:
                self._validate_board(role_code=role_code, board=board)

        if enforce_mandatory:
            submitted_by_id = {board.id: board for tab in normalized for board in tab.boards}
            missing = [
                board_id
                for board_id in template.mandatory_board_ids
                if board_id not in submitted_by_id or submitted_by_id[board_id].hidden
            ]
            if missing:
                raise DashboardAccessError(
                    409,
                    "mandatory_board_required",
                    f"필수 board는 삭제하거나 숨길 수 없습니다: {', '.join(missing)}",
                )

        self._validate_parameter_state(template, parameter_state)
        return normalized

    def _validate_board(self, *, role_code: str, board: DashboardBoard) -> None:
        definition = BOARD_DEFINITION_BY_ID.get(board.definition_id)
        if definition is None:
            raise ValueError(f"unknown board definition: {board.definition_id}")
        if role_code not in definition.allowed_roles:
            raise DashboardAccessError(
                403,
                "board_role_denied",
                f"역할 {role_code}에 허용되지 않은 board입니다: {board.definition_id}",
            )
        if not definition.minimum_width <= board.width <= definition.maximum_width:
            raise ValueError(f"board width is outside catalog limits: {board.id}")
        self._validate_plain_text(board.title, field="board title")
        self._validate_json_text(board.settings, field=f"board settings {board.id}")
        self._validate_json_text(board.bindings, field=f"board bindings {board.id}")
        unknown_bindings = sorted(set(board.bindings) - set(definition.binding_schema))
        if unknown_bindings:
            raise ValueError(
                f"unknown board bindings for {board.definition_id}: {', '.join(unknown_bindings)}"
            )
        for key, value in board.bindings.items():
            self._validate_value_type(value, definition.binding_schema[key], f"binding {key}")
        if board.definition_id == "text-board":
            text = board.settings.get("text", "")
            if not isinstance(text, str):
                raise ValueError("text-board settings.text must be a string")
            if len(text) > 4000:
                raise ValueError("text-board text must be 4000 characters or less")

    @staticmethod
    def _validate_plain_text(value: str, *, field: str) -> None:
        if UNSAFE_TEXT.search(value):
            raise ValueError(f"{field} must be plain text without HTML or script")

    @classmethod
    def _validate_json_text(cls, value: Any, *, field: str) -> None:
        if isinstance(value, str):
            cls._validate_plain_text(value, field=field)
        elif isinstance(value, dict):
            for child in value.values():
                cls._validate_json_text(child, field=field)
        elif isinstance(value, list):
            for child in value:
                cls._validate_json_text(child, field=field)

    @staticmethod
    def _validate_value_type(value: Any, value_type: str, field: str) -> None:
        if value is None:
            return
        valid = False
        if value_type in {"string", "datetime"}:
            valid = isinstance(value, str)
        elif value_type == "number":
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif value_type == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif value_type == "boolean":
            valid = isinstance(value, bool)
        elif value_type == "object":
            valid = isinstance(value, dict)
        elif value_type == "array":
            valid = isinstance(value, list)
        if not valid:
            raise ValueError(f"{field} must be {value_type}")

    def _validate_parameter_state(
        self,
        template: DashboardTemplateSnapshot,
        parameter_state: dict[str, Any],
    ) -> None:
        definitions = {item.id: item for item in template.parameter_definitions}
        unknown = sorted(set(parameter_state) - set(definitions))
        if unknown:
            raise ValueError(f"unknown dashboard parameters: {', '.join(unknown)}")
        for parameter_id, value in parameter_state.items():
            definition = definitions[parameter_id]
            self._validate_value_type(value, definition.value_type, f"parameter {parameter_id}")
            if definition.options and value not in definition.options:
                raise ValueError(f"parameter {parameter_id} is not an allowed option")
            self._validate_json_text(value, field=f"parameter {parameter_id}")

    @staticmethod
    def _normalize_orders(tabs: list[DashboardTab]) -> list[DashboardTab]:
        ordered_tabs = sorted(tabs, key=lambda item: (item.order, item.id))
        normalized: list[DashboardTab] = []
        for tab_order, tab in enumerate(ordered_tabs):
            boards = sorted(tab.boards, key=lambda item: (item.order, item.id))
            normalized.append(
                DashboardTab.model_validate(
                    {
                        **tab.model_dump(mode="python"),
                        "order": tab_order,
                        "boards": [
                            {**board.model_dump(mode="python"), "order": board_order}
                            for board_order, board in enumerate(boards)
                        ],
                    }
                )
            )
        return normalized

    def _preference_payload_from_tabs(
        self,
        *,
        template: DashboardTemplateSnapshot,
        tabs: list[DashboardTab],
        active_tab_id: str,
        parameter_state: dict[str, Any],
    ) -> dict[str, Any]:
        base_tabs = {tab.id: tab for tab in template.tabs}
        base_boards: dict[str, tuple[str, DashboardBoard]] = {
            board.id: (tab.id, board)
            for tab in template.tabs
            for board in tab.boards
        }
        submitted_boards: dict[str, tuple[str, DashboardBoard]] = {
            board.id: (tab.id, board)
            for tab in tabs
            for board in tab.boards
        }
        tab_overrides: dict[str, dict[str, Any]] = {}
        custom_tabs: list[dict[str, Any]] = []
        board_overrides: dict[str, dict[str, Any]] = {}
        custom_boards: list[dict[str, Any]] = []

        for tab in tabs:
            base_tab = base_tabs.get(tab.id)
            if base_tab is None:
                custom_tabs.append(
                    {
                        **tab.model_dump(mode="json"),
                        "custom": True,
                        "boards": [],
                    }
                )
            else:
                override = {
                    "title": tab.title,
                    "order": tab.order,
                    "hidden": tab.hidden,
                }
                if (
                    override["title"] != base_tab.title
                    or override["order"] != base_tab.order
                    or override["hidden"] != base_tab.hidden
                ):
                    tab_overrides[tab.id] = override

        for board_id, (base_tab_id, base_board) in base_boards.items():
            submitted = submitted_boards.get(board_id)
            if submitted is None:
                board_overrides[board_id] = {"hidden": True}
                continue
            submitted_tab_id, board = submitted
            override = {
                "tab_id": submitted_tab_id,
                "title": board.title,
                "width": board.width,
                "layout": board.layout.model_dump(mode="json") if board.layout else None,
                "source": board.source.model_dump(mode="json") if board.source else None,
                "order": board.order,
                "hidden": board.hidden,
                "bindings": board.bindings,
                "settings": board.settings,
            }
            base_values = {
                "tab_id": base_tab_id,
                "title": base_board.title,
                "width": base_board.width,
                "layout": base_board.layout.model_dump(mode="json") if base_board.layout else None,
                "source": base_board.source.model_dump(mode="json") if base_board.source else None,
                "order": base_board.order,
                "hidden": base_board.hidden,
                "bindings": base_board.bindings,
                "settings": base_board.settings,
            }
            if override != base_values:
                board_overrides[board_id] = override

        for tab in tabs:
            for board in tab.boards:
                if board.id not in base_boards:
                    custom_boards.append(
                        {
                            "tab_id": tab.id,
                            "board": {
                                **board.model_dump(mode="json"),
                                "custom": True,
                                "mandatory": False,
                            },
                        }
                    )

        return {
            "active_tab_id": active_tab_id,
            "parameter_state": parameter_state,
            "tab_overrides": tab_overrides,
            "custom_tabs": custom_tabs,
            "board_overrides": board_overrides,
            "custom_boards": custom_boards,
        }

    def _apply_preference_payload(
        self,
        *,
        tabs: list[DashboardTab],
        payload: dict[str, Any],
    ) -> list[DashboardTab]:
        tab_map = {tab.id: tab for tab in tabs}
        for tab_id, override in payload.get("tab_overrides", {}).items():
            tab = tab_map.get(tab_id)
            if tab is None:
                continue
            tab_map[tab_id] = DashboardTab.model_validate(
                {**tab.model_dump(mode="python"), **override}
            )

        for raw_tab in payload.get("custom_tabs", []):
            tab = DashboardTab.model_validate(raw_tab)
            tab_map[tab.id] = tab

        base_boards: dict[str, tuple[str, DashboardBoard]] = {
            board.id: (tab.id, board) for tab in tab_map.values() for board in tab.boards
        }
        for tab_id, tab in list(tab_map.items()):
            tab_map[tab_id] = DashboardTab.model_validate(
                {**tab.model_dump(mode="python"), "boards": []}
            )

        for board_id, (base_tab_id, board) in base_boards.items():
            override = payload.get("board_overrides", {}).get(board_id, {})
            target_tab_id = override.get("tab_id", base_tab_id)
            if target_tab_id not in tab_map:
                target_tab_id = base_tab_id
            merged = DashboardBoard.model_validate(
                {
                    **board.model_dump(mode="python"),
                    **{key: value for key, value in override.items() if key != "tab_id"},
                }
            )
            target = tab_map[target_tab_id]
            tab_map[target_tab_id] = DashboardTab.model_validate(
                {
                    **target.model_dump(mode="python"),
                    "boards": [*target.boards, merged],
                }
            )

        for item in payload.get("custom_boards", []):
            tab_id = item.get("tab_id")
            if tab_id not in tab_map:
                continue
            board = DashboardBoard.model_validate(item.get("board"))
            target = tab_map[tab_id]
            tab_map[tab_id] = DashboardTab.model_validate(
                {
                    **target.model_dump(mode="python"),
                    "boards": [*target.boards, board],
                }
            )
        return list(tab_map.values())

    @staticmethod
    def _dependency_graph(tabs: Iterable[DashboardTab]) -> list[DependencyEdge]:
        boards = [board for tab in tabs for board in tab.boards if not board.hidden]
        edges: list[DependencyEdge] = []
        for source in boards:
            source_definition = BOARD_DEFINITION_BY_ID.get(source.definition_id)
            if source_definition is None or not source_definition.emits:
                continue
            emitted = set(source_definition.emits)
            for target in boards:
                if source.id == target.id:
                    continue
                target_definition = BOARD_DEFINITION_BY_ID.get(target.definition_id)
                if target_definition is None:
                    continue
                shared = sorted(emitted & set(target_definition.accepts))
                if shared:
                    edges.append(
                        DependencyEdge(
                            source_board_id=source.id,
                            target_board_id=target.id,
                            parameter_ids=shared,
                        )
                    )
        return edges

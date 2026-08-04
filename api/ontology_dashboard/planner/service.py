from __future__ import annotations

import copy
import hashlib
import re
from typing import Any

from pydantic import ValidationError

from ..dashboard_models import DashboardBoard, DashboardTab, DashboardTemplatePublishRequest
from ..dashboard_service import DashboardService
from ..identity import AuthError, Principal
from ..llm import LLMProvider
from ..ontology import OBJECT_TYPE_BY_ID
from ..ontology_service import OntologyService
from ..predictive_maintenance_runtime.models import DatasetVersionRuntimeContext
from ..predictive_maintenance_runtime.service import (
    V3_1_MODEL_VERSION,
    V3_1_RESULT_SCHEMA,
    V3_1_SOURCE_VERSION,
)
from ..service import ManufacturingPredictiveMaintenanceService
from ..visualizations import (
    VISUALIZATION_REGISTRY,
    SemanticVisualizationPlanRequest,
    SemanticVisualizationPlanResponse,
    build_typed_query_plan,
    build_v3_1_semantic_catalog,
    compile_postgresql_query,
    context_from_source,
    validate_override,
    validate_override_channel_mapping,
)
from .models import (
    BoardRecommendationItem,
    BoardRecommendationRequest,
    BoardRecommendationResponse,
    DashboardDraftRequest,
    DashboardDraftResponse,
    GroundedNarrativeClaim,
    GroundedNarrativeRequest,
    GroundedNarrativeResponse,
    NaturalLanguageObjectQueryRequest,
    ObjectQueryFilter,
    ObjectQueryIntent,
    ObjectQueryPlanResponse,
    VisualizationPlannerResponse,
    VisualizationRecommendationRequest,
)

STATUS_TERMS = {
    "critical": ["critical", "치명", "긴급", "위급"],
    "warning": ["warning", "경고", "위험"],
    "attention": ["attention", "주의", "관심"],
    "data_quality_hold": ["data quality", "데이터 품질", "센서 오류", "품질 보류"],
    "normal": ["normal", "정상", "안정"],
}

OBJECT_TYPE_TERMS = {
    "equipment": ["equipment", "설비", "장비", "기계", "라인"],
    "risk_event": ["risk event", "위험 사건", "위험", "이벤트", "경고", "고장"],
    "evidence_package": ["evidence", "근거", "증거", "lineage", "리니지"],
    "work_order": ["work order", "작업 지시", "작업지시", "정비 오더", "점검", "검사", "현장 작업"],
    "inspection": ["inspection legacy", "legacy inspection"],
    "maintenance_action": ["maintenance action", "정비 행동", "조치", "작업 기록"],
}

ROLE_CATEGORY_PRIORITY: dict[str, list[str]] = {
    "tenant_admin": ["audit", "observe", "build", "act", "explore", "explain"],
    "executive_viewer": ["observe", "explore", "explain"],
    "process_manager": ["act", "observe", "explain", "explore"],
    "process_engineer": ["explore", "explain", "act", "audit"],
    "maintenance_technician": ["act", "observe", "explain"],
    "quality_auditor": ["audit", "explain", "observe"],
    "ml_validator": ["explore", "audit", "build", "explain"],
    "fde": ["build", "audit", "explore", "explain"],
}

FORBIDDEN_OPERATIONAL_CLAIMS = (
    "자동 정지 완료",
    "작업 지시가 실행",
    "근본 원인이 확정",
    "고장이 확정",
)


class OntologyDashboardPlannerService:
    """Catalog-bound planner used by object search, dashboard drafting and narrative generation.

    The class is intentionally deterministic-first. A provider may suggest typed values, but every
    suggestion is validated against the canonical ontology and board registries before execution.
    """

    def __init__(
        self,
        legacy_service: ManufacturingPredictiveMaintenanceService,
        *,
        provider: LLMProvider | None = None,
    ) -> None:
        self.legacy_service = legacy_service
        self.ontology = OntologyService(legacy_service)
        self.dashboards = DashboardService(str(legacy_service.repository.path))
        self.provider = provider

    @staticmethod
    def _provider_name(provider: LLMProvider | None) -> str:
        return getattr(provider, "name", "none") if provider is not None else "none"

    @staticmethod
    def _role(principal: Principal) -> str:
        return principal.roles[0] if principal.roles else "process_manager"

    @staticmethod
    def _normalized(text: str) -> str:
        return " ".join(text.strip().lower().split())

    @staticmethod
    def _keyword_score(goal: str, *texts: str) -> float:
        goal_tokens = {
            token
            for token in re.findall(r"[0-9a-zA-Z가-힣_]+", goal.lower())
            if len(token) >= 2
        }
        if not goal_tokens:
            return 0.0
        haystack = " ".join(texts).lower()
        matched = sum(token in haystack for token in goal_tokens)
        return min(1.0, matched / max(1, len(goal_tokens)))

    def _deterministic_intent(self, request: NaturalLanguageObjectQueryRequest) -> ObjectQueryIntent:
        query = self._normalized(request.query)
        object_type = "risk_event"
        matched_terms: list[str] = []
        best_count = 0
        for candidate, terms in OBJECT_TYPE_TERMS.items():
            count = sum(term in query for term in terms)
            if count > best_count:
                object_type = candidate
                best_count = count
                matched_terms = [term for term in terms if term in query]

        filters: list[ObjectQueryFilter] = []
        for status, terms in STATUS_TERMS.items():
            if any(term in query for term in terms):
                if object_type != "risk_event":
                    object_type = "risk_event"
                filters.append(ObjectQueryFilter(field="status", operator="eq", value=status))
                matched_terms.extend(term for term in terms if term in query)
                break

        probability_match = re.search(
            r"(?:확률|probability)\s*(?:이|가)?\s*(\d{1,3})(?:\s*%)?\s*(?:이상|over|above)",
            query,
        )
        if probability_match:
            value = min(100, int(probability_match.group(1))) / 100
            object_type = "risk_event"
            filters.append(ObjectQueryFilter(field="failure_probability", operator="gte", value=value))
            matched_terms.append(probability_match.group(0))

        identifier_match = re.search(
            r"\b(?:EVT-GS-\d{3}|GS-\d{3}|M-\d{3}|WO-[0-9A-Z-]+)\b",
            request.query,
            re.IGNORECASE,
        )
        search = identifier_match.group(0).upper() if identifier_match else None
        if search is None:
            line_match = re.search(r"(?:가공|조립|포장|생산)\s*\d*\s*라인", request.query)
            if line_match:
                search = line_match.group(0)
                matched_terms.append(search)

        return ObjectQueryIntent(
            object_type=object_type,
            search=search,
            filters=filters,
            limit=request.limit,
            rationale=(
                f"'{object_type}' Object를 대상으로 자연어의 Object·상태·식별자 표현을 "
                "허용된 registry field에 매핑했습니다."
            ),
            source_terms=list(dict.fromkeys(matched_terms)),
        )

    def _validate_query_intent(self, intent: ObjectQueryIntent) -> None:
        definition = OBJECT_TYPE_BY_ID.get(intent.object_type)
        if definition is None:
            raise ValueError(f"planner requested unknown object_type: {intent.object_type}")
        allowed_fields = {item.id for item in definition.properties}
        for item in intent.filters:
            if item.field not in allowed_fields:
                raise ValueError(
                    f"planner requested unauthorized or unknown field for {intent.object_type}: {item.field}"
                )

    @staticmethod
    def _match_filter(properties: dict[str, Any], item: ObjectQueryFilter) -> bool:
        value = properties.get(item.field)
        if item.operator == "eq":
            return value == item.value
        if item.operator == "contains":
            return str(item.value).lower() in str(value).lower()
        if value is None:
            return False
        try:
            left = float(value)
            right = float(item.value)
        except (TypeError, ValueError):
            return False
        return left >= right if item.operator == "gte" else left <= right

    def _execute_intent(self, workspace_id: str, intent: ObjectQueryIntent) -> list[dict[str, Any]]:
        payload = self.ontology.query_objects(
            workspace_id=workspace_id,
            object_type=intent.object_type,
            search=intent.search,
            limit=100,
        )
        items = payload["items"]
        for filter_item in intent.filters:
            items = [item for item in items if self._match_filter(item.get("properties", {}), filter_item)]
        return items[: intent.limit]

    def object_query_plan(
        self,
        *,
        principal: Principal,
        request: NaturalLanguageObjectQueryRequest,
    ) -> ObjectQueryPlanResponse:
        deterministic = self._deterministic_intent(request)
        mode = "deterministic"
        provider = "none"
        fallback_reason: str | None = None
        intent = deterministic
        if request.use_llm:
            if self.provider is None:
                mode = "deterministic_fallback"
                fallback_reason = "planner_provider_unavailable"
            else:
                try:
                    payload = self.provider.generate_json(
                        (
                            "Return JSON only. Map the request to one registered ontology object type and "
                            "registered properties. Never invent object types or properties. Return "
                            "object_type, search, filters, limit, rationale, source_terms."
                        ),
                        {
                            "query": request.query,
                            "workspace_id": request.workspace_id,
                            "registered_object_types": [
                                {"id": item.id, "properties": [prop.id for prop in item.properties]}
                                for item in OBJECT_TYPE_BY_ID.values()
                            ],
                            "deterministic_candidate": deterministic.model_dump(mode="json"),
                            "limit": request.limit,
                        },
                    )
                    payload["limit"] = min(request.limit, int(payload.get("limit", request.limit)))
                    intent = ObjectQueryIntent.model_validate(payload)
                    self._validate_query_intent(intent)
                    mode = "llm"
                    provider = self._provider_name(self.provider)
                except (Exception, ValidationError) as exc:
                    intent = deterministic
                    mode = "deterministic_fallback"
                    provider = self._provider_name(self.provider)
                    fallback_reason = type(exc).__name__
        self._validate_query_intent(intent)
        items = self._execute_intent(request.workspace_id, intent)
        return ObjectQueryPlanResponse(
            mode=mode,
            provider=provider,
            fallback_reason=fallback_reason,
            intent=intent,
            preview_total=len(items),
            preview_items=items,
            validation={
                "object_type_registered": True,
                "filter_fields_registered": True,
                "workspace_scope_enforced_by_api": True,
                "permission_enforced_by_api": True,
                "query_executed_through_ontology_service": True,
            },
        )

    def _deterministic_recommendations(
        self,
        *,
        principal: Principal,
        request: BoardRecommendationRequest,
        role_code: str,
    ) -> list[BoardRecommendationItem]:
        resolved = self.dashboards.resolve(principal=principal, workspace_id=request.workspace_id)
        current_boards = [board for tab in resolved.tabs for board in tab.boards]
        current_ids = {board.definition_id for board in current_boards}
        hidden_ids = {board.definition_id for board in current_boards if board.hidden}
        wide_ids = {board.definition_id for board in current_boards if board.width == 12}
        catalog = self.dashboards.catalog(principal=principal, role_code=role_code).items
        category_priority = ROLE_CATEGORY_PRIORITY.get(role_code, [])
        scored: list[tuple[float, BoardRecommendationItem]] = []
        for definition in catalog:
            keyword = self._keyword_score(
                request.goal,
                definition.id,
                definition.display_name,
                definition.description,
                definition.category,
                " ".join(definition.object_types),
            )
            category_bonus = 0.0
            if definition.category in category_priority:
                category_bonus = max(0.05, 0.25 - category_priority.index(definition.category) * 0.04)
            existing = definition.id in current_ids
            preference_signals: list[str] = []
            if existing:
                preference_signals.append("현재 Dashboard에 이미 존재")
            if definition.id in hidden_ids:
                preference_signals.append("사용자가 숨긴 Board")
            if definition.id in wide_ids:
                preference_signals.append("사용자가 넓게 배치한 Board")
            score = max(
                0.01,
                min(
                    1.0,
                    0.25
                    + keyword * 0.55
                    + category_bonus
                    + (0.08 if definition.id in wide_ids else 0.0)
                    - (0.15 if definition.id in hidden_ids else 0.0)
                    - (0.08 if existing else 0.0),
                ),
            )
            scored.append(
                (
                    score,
                    BoardRecommendationItem(
                        definition_id=definition.id,
                        display_name=definition.display_name,
                        category=definition.category,
                        score=round(score, 4),
                        reason=(
                            f"'{request.goal}' 목표와 {definition.category} 업무 성격, "
                            f"역할 {role_code}의 허용 Catalog를 기준으로 추천했습니다."
                        ),
                        already_present=existing,
                        preference_signals=preference_signals,
                    ),
                )
            )
        scored.sort(key=lambda item: (-item[0], item[1].definition_id))
        return [item for _, item in scored[: request.limit]]

    def board_recommendations(
        self,
        *,
        principal: Principal,
        request: BoardRecommendationRequest,
    ) -> BoardRecommendationResponse:
        role_code = self._role(principal)
        deterministic = self._deterministic_recommendations(
            principal=principal,
            request=request,
            role_code=role_code,
        )
        recommendations = deterministic
        mode = "deterministic"
        provider = "none"
        fallback_reason: str | None = None
        catalog = {
            item.id: item
            for item in self.dashboards.catalog(principal=principal, role_code=role_code).items
        }
        resolved = self.dashboards.resolve(principal=principal, workspace_id=request.workspace_id)
        current_ids = [board.definition_id for tab in resolved.tabs for board in tab.boards]
        if request.use_llm:
            if self.provider is None:
                mode = "deterministic_fallback"
                fallback_reason = "planner_provider_unavailable"
            else:
                try:
                    payload = self.provider.generate_json(
                        (
                            "Return JSON only with recommendations. Select only IDs from allowed_catalog. "
                            "Never create a board type. Each item needs definition_id, score and reason."
                        ),
                        {
                            "role_code": role_code,
                            "goal": request.goal,
                            "allowed_catalog": [item.model_dump(mode="json") for item in catalog.values()],
                            "current_dashboard": resolved.model_dump(mode="json"),
                            "deterministic_candidates": [item.model_dump(mode="json") for item in deterministic],
                            "limit": request.limit,
                        },
                    )
                    validated: list[BoardRecommendationItem] = []
                    for raw in payload.get("recommendations", [])[: request.limit]:
                        definition_id = str(raw["definition_id"])
                        definition = catalog.get(definition_id)
                        if definition is None:
                            raise ValueError(f"LLM selected board outside catalog: {definition_id}")
                        validated.append(
                            BoardRecommendationItem(
                                definition_id=definition_id,
                                display_name=definition.display_name,
                                category=definition.category,
                                score=float(raw.get("score", 0.5)),
                                reason=str(raw.get("reason", "역할과 목표에 맞는 Board입니다.")),
                                already_present=definition_id in current_ids,
                                preference_signals=next(
                                    (
                                        item.preference_signals
                                        for item in deterministic
                                        if item.definition_id == definition_id
                                    ),
                                    [],
                                ),
                            )
                        )
                    if not validated:
                        raise ValueError("LLM returned no valid recommendations")
                    recommendations = validated
                    mode = "llm"
                    provider = self._provider_name(self.provider)
                except Exception as exc:
                    recommendations = deterministic
                    mode = "deterministic_fallback"
                    provider = self._provider_name(self.provider)
                    fallback_reason = type(exc).__name__
        return BoardRecommendationResponse(
            mode=mode,
            provider=provider,
            fallback_reason=fallback_reason,
            role_code=role_code,
            goal=request.goal,
            recommendations=recommendations,
            current_board_ids=current_ids,
        )

    @staticmethod
    def _validate_visualization_candidates(request: VisualizationRecommendationRequest) -> None:
        registry = {item.kind for item in VISUALIZATION_REGISTRY}
        fields = {item.id for item in request.field_profile}
        seen: set[str] = set()
        for candidate in request.deterministic_candidates:
            if candidate.kind not in registry:
                raise ValueError(f"planner requested unregistered visualization: {candidate.kind}")
            if candidate.kind in seen:
                raise ValueError(f"duplicate visualization candidate: {candidate.kind}")
            seen.add(candidate.kind)
            mapped_fields = {
                value
                for value in candidate.field_mapping.model_dump().values()
                if isinstance(value, str) and value
            }
            unknown = mapped_fields - fields
            if unknown:
                raise ValueError(f"visualization candidate references unknown fields: {sorted(unknown)}")

    def visualization_recommendation(
        self,
        *,
        principal: Principal,
        request: VisualizationRecommendationRequest,
    ) -> VisualizationPlannerResponse:
        self._validate_visualization_candidates(request)
        candidates = sorted(request.deterministic_candidates, key=lambda item: item.score, reverse=True)
        selected_kind = candidates[0].kind
        selected_rationale = candidates[0].rationale
        mode = "deterministic"
        provider = "none"
        fallback_reason: str | None = None
        if request.use_llm:
            if self.provider is None:
                mode = "deterministic_fallback"
                fallback_reason = "planner_provider_unavailable"
            else:
                try:
                    payload = self.provider.generate_json(
                        (
                            "Return JSON only with kind and rationale. Choose exactly one kind from candidates. "
                            "Do not invent chart kinds, fields, aggregations, or query changes. The goal may only "
                            "reorder deterministic candidates and clarify the rationale."
                        ),
                        {
                            "goal": request.goal,
                            "workspace_id": request.workspace_id,
                            "dashboard_id": request.dashboard_id,
                            "board_id": request.board_id,
                            "field_profile": [item.model_dump(mode="json") for item in request.field_profile],
                            "candidates": [item.model_dump(mode="json") for item in candidates],
                        },
                    )
                    requested_kind = str(payload.get("kind") or "")
                    selected = next((item for item in candidates if item.kind == requested_kind), None)
                    if selected is None:
                        raise ValueError("provider selected a visualization outside deterministic candidates")
                    selected_kind = selected.kind
                    selected_rationale = str(payload.get("rationale") or selected.rationale)[:500]
                    mode = "llm"
                    provider = self._provider_name(self.provider)
                except Exception as exc:
                    mode = "deterministic_fallback"
                    provider = self._provider_name(self.provider)
                    fallback_reason = type(exc).__name__
        recommended = next(item for item in candidates if item.kind == selected_kind).model_copy(
            update={"rationale": selected_rationale}
        )
        alternatives = [item for item in candidates if item.kind != selected_kind]
        return VisualizationPlannerResponse(
            mode=mode,
            provider=provider,
            fallback_reason=fallback_reason,
            workspace_id=request.workspace_id,
            dashboard_id=request.dashboard_id,
            board_id=request.board_id,
            goal=request.goal,
            recommended=recommended,
            alternatives=alternatives[:5],
            validation={
                "registry_whitelist": True,
                "fields_exist": True,
                "deterministic_candidates_only": True,
                "workspace_scope_enforced_by_api": True,
                "permission_enforced_by_api": True,
                "query_rows_unchanged": True,
            },
        )

    def semantic_visualization_plan(
        self,
        *,
        principal: Principal,
        request: SemanticVisualizationPlanRequest,
        runtime_context: DatasetVersionRuntimeContext,
    ) -> SemanticVisualizationPlanResponse:
        source = request.source
        if source.organization_id != principal.organization_id:
            raise AuthError(403, "organization_scope_denied", "Organization 범위를 벗어난 source입니다.")
        if source.workspace_id not in principal.workspace_scopes:
            raise AuthError(403, "workspace_scope_denied", "Workspace 범위를 벗어난 source입니다.")
        allowed_projects = set(principal.project_scopes)
        if principal.active_project_id:
            allowed_projects.add(principal.active_project_id)
        if source.project_id not in allowed_projects:
            raise AuthError(403, "project_scope_denied", "Project 범위를 벗어난 source입니다.")
        expected_identity = {
            "organization_id": runtime_context.organization_id,
            "project_id": runtime_context.project_id,
            "workspace_id": runtime_context.workspace_id,
            "dataset_id": runtime_context.dataset_id,
            "dataset_version_id": runtime_context.dataset_version_id,
        }
        mismatches = [
            field_name
            for field_name, expected in expected_identity.items()
            if getattr(source, field_name) != expected
        ]
        if mismatches:
            raise ValueError(
                "semantic source identity does not match the server Dataset Version: "
                + ",".join(mismatches)
            )
        if source.dataset_version != runtime_context.source_version:
            raise ValueError("semantic source dataset_version does not match the server Dataset Version")
        if source.source_version != runtime_context.source_version:
            raise ValueError("semantic source source_version does not match the server Dataset Version")
        if source.bundle_checksum_sha256 != runtime_context.bundle_checksum_sha256:
            raise ValueError("semantic source checksum does not match the server Dataset Version")
        if runtime_context.source_version != V3_1_SOURCE_VERSION:
            raise ValueError("Semantic Visualization Planner only supports V3.1 Dataset Versions")
        if source.model_version not in {None, V3_1_MODEL_VERSION}:
            raise ValueError("semantic source model_version does not match the V3.1 model contract")
        if source.result_artifact_schema_version not in {None, V3_1_RESULT_SCHEMA}:
            raise ValueError(
                "semantic source Result Artifact schema does not match the V3.1 contract"
            )
        source = source.model_copy(
            update={
                "dataset_version": runtime_context.source_version,
                "source_version": runtime_context.source_version,
                "bundle_checksum_sha256": runtime_context.bundle_checksum_sha256,
                "model_version": V3_1_MODEL_VERSION,
                "result_artifact_schema_version": V3_1_RESULT_SCHEMA,
                "release_gates": runtime_context.governance.model_dump(mode="json"),
                "graph_readiness": runtime_context.graph.status,
                "relational_fallback_capability": not runtime_context.graph.required_for_runtime,
            }
        )
        request = request.model_copy(update={"source": source})
        if source.source_role == "result_artifact" and (
            source.result_artifact_schema_version != V3_1_RESULT_SCHEMA
        ):
            raise ValueError("Result Artifact schema version is incompatible with the V3.1 catalog")

        catalog = build_v3_1_semantic_catalog(context_from_source(source))
        deterministic_plan, candidates = build_typed_query_plan(request, catalog)
        base_plan = deterministic_plan
        base_candidates = candidates
        override = validate_override(request.saved_override, deterministic_plan, catalog)
        override_applied = False
        if request.saved_override is not None and override.status == "compatible":
            overridden_request = request.model_copy(
                update={
                    "dimensions": request.saved_override.dimensions,
                    "measures": request.saved_override.measures,
                    "chart_kind": request.saved_override.chart_kind,
                    "use_llm": False,
                }
            )
            try:
                deterministic_plan, candidates = build_typed_query_plan(
                    overridden_request,
                    catalog,
                )
                validate_override_channel_mapping(request.saved_override, deterministic_plan)
                deterministic_plan = deterministic_plan.model_copy(
                    update={
                        "channel_mapping": request.saved_override.channel_mapping,
                        "selection_reason": "Saved semantic visualization override applied.",
                    }
                )
                request = overridden_request
                override_applied = True
            except ValueError as exc:
                deterministic_plan = base_plan
                candidates = base_candidates
                override = override.model_copy(
                    update={
                        "status": "incompatible",
                        "reasons": [f"override_validation:{exc}"],
                    }
                )
        selected_kind = deterministic_plan.chart_kind
        selected_rationale = deterministic_plan.selection_reason
        mode = "deterministic"
        provider = "none"
        fallback_reason: str | None = None
        if request.use_llm and not override_applied:
            if self.provider is None:
                mode = "deterministic_fallback"
                fallback_reason = "planner_provider_unavailable"
            else:
                try:
                    payload = self.provider.generate_json(
                        (
                            "Return JSON only with kind and rationale. Choose exactly one kind from candidates. "
                            "Do not create or modify fields, SQL, aggregations, filters, derived expressions, "
                            "Dataset Version, scope, or channel mappings."
                        ),
                        {
                            "goal": request.goal,
                            "intent": request.intent,
                            "source_role": source.source_role,
                            "semantic_fields": [
                                catalog[field_id].model_dump(mode="json")
                                for field_id in dict.fromkeys(
                                    [
                                        *request.dimensions,
                                        *(item.field_id for item in request.measures),
                                        *([request.time.field_id] if request.time else []),
                                    ]
                                )
                            ],
                            "candidates": [item.model_dump(mode="json") for item in candidates],
                            "result_profile": [
                                item.model_dump(mode="json") for item in request.result_profile
                            ],
                        },
                    )
                    requested_kind = str(payload.get("kind") or "")
                    selected = next((item for item in candidates if item.kind == requested_kind), None)
                    if selected is None:
                        raise ValueError("provider selected a chart outside deterministic semantic candidates")
                    selected_kind = selected.kind
                    selected_rationale = str(payload.get("rationale") or selected.rationale)[:500]
                    mode = "llm"
                    provider = self._provider_name(self.provider)
                except Exception as exc:
                    mode = "deterministic_fallback"
                    provider = self._provider_name(self.provider)
                    fallback_reason = type(exc).__name__

        if override_applied:
            plan = deterministic_plan
        else:
            plan, candidates = build_typed_query_plan(
                request,
                catalog,
                selected_kind=selected_kind,
            )
            plan = plan.model_copy(update={"selection_reason": selected_rationale})
        compiled = compile_postgresql_query(
            plan,
            catalog,
            clamp_limits=request.clamp_limits,
        )
        return SemanticVisualizationPlanResponse(
            mode=mode,
            provider=provider,
            fallback_reason=fallback_reason,
            plan=plan,
            compiled_query=compiled,
            candidates=candidates,
            semantic_fields=list(catalog.values()),
            override_compatibility=override,
            validation={
                "catalog_version": plan.catalog_version,
                "field_registry_only": True,
                "derived_expression_allowlist_only": True,
                "parameterized_postgresql": True,
                "llm_sql_generation": False,
                "scope_enforced": True,
                "dataset_version_enforced": True,
                "result_artifact_schema_enforced": source.source_role != "result_artifact"
                or source.result_artifact_schema_version == V3_1_RESULT_SCHEMA,
                "release_gates_governance_only": True,
                "binary_failure_class_preserved": True,
                "evaluation_truth_available": False,
                "graph_readiness": source.graph_readiness,
                "relational_fallback": source.relational_fallback_capability,
                "query_clamped": compiled.clamped,
                "override_applied": override_applied,
                "result_profile_compatible": True,
                "server_authoritative_dataset_context": True,
            },
        )

    def dashboard_draft(
        self,
        *,
        principal: Principal,
        request: DashboardDraftRequest,
    ) -> DashboardDraftResponse:
        if "dashboards.templates.manage" not in principal.permissions:
            raise AuthError(403, "permission_denied", "Dashboard template 초안을 생성할 권한이 없습니다.")
        current = self.dashboards.current_template(
            workspace_id=request.workspace_id,
            role_code=request.target_role,
        )
        catalog_response = self.dashboards.catalog(principal=principal, role_code=request.target_role)
        catalog = {item.id: item for item in catalog_response.items}
        existing_definition_ids = {board.definition_id for tab in current.tabs for board in tab.boards}
        deterministic_candidates = sorted(
            catalog.values(),
            key=lambda item: (
                -self._keyword_score(
                    request.goal,
                    item.id,
                    item.display_name,
                    item.description,
                    item.category,
                ),
                item.id,
            ),
        )
        selected_ids = [
            item.id for item in deterministic_candidates if item.id not in existing_definition_ids
        ][: request.max_new_boards]
        mode = "deterministic"
        provider = "none"
        fallback_reason: str | None = None
        tab_title = "Planner 제안"
        if request.use_llm:
            if self.provider is None:
                mode = "deterministic_fallback"
                fallback_reason = "planner_provider_unavailable"
            else:
                try:
                    payload = self.provider.generate_json(
                        (
                            "Return JSON only with tab_title and board_definition_ids. Select only IDs "
                            "from allowed_catalog. Do not remove mandatory boards or persist data."
                        ),
                        {
                            "goal": request.goal,
                            "target_role": request.target_role,
                            "allowed_catalog": [item.model_dump(mode="json") for item in catalog.values()],
                            "current_template": current.model_dump(mode="json"),
                            "max_new_boards": request.max_new_boards,
                        },
                    )
                    proposed_ids = [str(item) for item in payload.get("board_definition_ids", [])]
                    invalid = [item for item in proposed_ids if item not in catalog]
                    if invalid:
                        raise ValueError(f"LLM selected board outside catalog: {invalid}")
                    selected_ids = [
                        item for item in proposed_ids if item not in existing_definition_ids
                    ][: request.max_new_boards]
                    tab_title = str(payload.get("tab_title") or tab_title).strip()[:80] or "Planner 제안"
                    mode = "llm"
                    provider = self._provider_name(self.provider)
                except Exception as exc:
                    mode = "deterministic_fallback"
                    provider = self._provider_name(self.provider)
                    fallback_reason = type(exc).__name__

        tabs = [DashboardTab.model_validate(item.model_dump(mode="python")) for item in current.tabs]
        if selected_ids:
            suffix = hashlib.sha256(
                f"{request.target_role}:{request.goal}".encode("utf-8")
            ).hexdigest()[:8]
            new_tab_id = f"planner:{request.target_role}:{suffix}"
            new_boards: list[DashboardBoard] = []
            for index, definition_id in enumerate(selected_ids):
                definition = catalog[definition_id]
                new_boards.append(
                    DashboardBoard(
                        id=f"{new_tab_id}:{definition_id}:{index}",
                        definition_id=definition_id,
                        title=definition.display_name,
                        width=definition.default_width,
                        order=index,
                        custom=True,
                        bindings=copy.deepcopy(definition.default_bindings),
                        settings=copy.deepcopy(definition.default_settings),
                    )
                )
            tabs.append(
                DashboardTab(
                    id=new_tab_id,
                    title=tab_title,
                    order=len(tabs),
                    custom=True,
                    parameter_ids=[item.id for item in current.parameter_definitions],
                    boards=new_boards,
                )
            )

        publish_request = DashboardTemplatePublishRequest(
            workspace_id=request.workspace_id,
            display_name=f"{request.target_role} Planner Draft",
            tabs=tabs,
            parameter_definitions=current.parameter_definitions,
        )
        validated_tabs = self.dashboards.validate_template_draft(
            role_code=request.target_role,
            template=current,
            request=publish_request,
        )
        return DashboardDraftResponse(
            mode=mode,
            provider=provider,
            fallback_reason=fallback_reason,
            workspace_id=request.workspace_id,
            target_role=request.target_role,
            display_name=publish_request.display_name,
            tabs=validated_tabs,
            parameter_definitions=current.parameter_definitions,
            recommended_definition_ids=selected_ids,
            validation={
                "catalog_whitelist": True,
                "target_role_permission": True,
                "mandatory_boards_preserved": True,
                "schema_valid": True,
                "persisted": False,
                "approval_required": True,
            },
        )

    @staticmethod
    def _allowed_evidence_refs(evidence: dict[str, Any]) -> set[str]:
        refs = {
            "status",
            "recommended_decision",
            "confidence",
            "failure_probability",
            "predicted_failure_type",
            "detected_interval.start",
            "detected_interval.end",
            "equipment.criticality",
            "equipment.estimated_downtime_minutes",
            "model.model_version",
            "model.policy_version",
            "threshold",
        }
        refs.update(factor["evidence_field_id"] for factor in evidence["top_factors"])
        refs.update(evidence["maintenance_context"]["source_refs"])
        refs.update(
            f"data_quality_warnings.{index}"
            for index, _ in enumerate(evidence["data_quality_warnings"])
        )
        return refs

    def _deterministic_narrative(
        self,
        request: GroundedNarrativeRequest,
        evidence: dict[str, Any],
    ) -> GroundedNarrativeResponse:
        probability = evidence.get("failure_probability")
        probability_text = "산출되지 않음" if probability is None else f"{probability * 100:.1f}%"
        claims = [
            GroundedNarrativeClaim(
                text=f"현재 사건 상태는 {evidence['status']}이며 failure probability는 {probability_text}입니다.",
                evidence_field_ids=["status", "failure_probability"],
            ),
            GroundedNarrativeClaim(
                text=(
                    f"운영 권장 판단은 {evidence['recommended_decision']}이고 "
                    f"confidence는 {evidence['confidence']}입니다."
                ),
                evidence_field_ids=["recommended_decision", "confidence"],
            ),
        ]
        if evidence["top_factors"]:
            factor = evidence["top_factors"][0]
            claims.append(
                GroundedNarrativeClaim(
                    text=f"가장 우선 확인할 근거는 {factor['display_name']}입니다.",
                    evidence_field_ids=[factor["evidence_field_id"]],
                )
            )
        if evidence["data_quality_warnings"]:
            claims.append(
                GroundedNarrativeClaim(
                    text="데이터 품질 경고가 있어 운영 판단 전에 입력 검증이 필요합니다.",
                    evidence_field_ids=["data_quality_warnings.0"],
                )
            )
        citations = list(dict.fromkeys(ref for claim in claims for ref in claim.evidence_field_ids))
        return GroundedNarrativeResponse(
            mode="deterministic",
            provider="none",
            event_id=request.event_id,
            goal=request.goal,
            headline=f"{evidence['equipment']['display_name']} · {evidence['status']}",
            summary=" ".join(claim.text for claim in claims),
            claims=claims,
            citations=citations,
        )

    def _validate_narrative(
        self,
        narrative: GroundedNarrativeResponse,
        evidence: dict[str, Any],
    ) -> None:
        if narrative.event_id != evidence["event_id"]:
            raise ValueError("narrative event does not match Evidence")
        allowed = self._allowed_evidence_refs(evidence)
        referenced = set(narrative.citations)
        for claim in narrative.claims:
            referenced.update(claim.evidence_field_ids)
        unknown = sorted(referenced - allowed)
        if unknown:
            raise ValueError(f"narrative contains unknown evidence references: {unknown}")
        combined = " ".join(
            [narrative.headline, narrative.summary, *(claim.text for claim in narrative.claims)]
        )
        if any(phrase in combined for phrase in FORBIDDEN_OPERATIONAL_CLAIMS):
            raise ValueError("narrative contains a forbidden operational claim")

    def grounded_narrative(
        self,
        *,
        principal: Principal,
        request: GroundedNarrativeRequest,
    ) -> GroundedNarrativeResponse:
        evidence = self.legacy_service.evidence_snapshot(request.event_id)
        deterministic = self._deterministic_narrative(request, evidence)
        narrative = deterministic
        if request.use_llm:
            if self.provider is None:
                narrative = deterministic.model_copy(
                    update={
                        "mode": "deterministic_fallback",
                        "fallback_reason": "planner_provider_unavailable",
                    }
                )
            else:
                try:
                    payload = self.provider.generate_json(
                        (
                            "Return JSON only. Write a grounded narrative from supplied Evidence. Every "
                            "claim must cite allowed_evidence_refs. Do not claim automatic control, "
                            "confirmed root cause or completed work."
                        ),
                        {
                            "event_id": request.event_id,
                            "goal": request.goal,
                            "role_code": self._role(principal),
                            "evidence": evidence,
                            "allowed_evidence_refs": sorted(self._allowed_evidence_refs(evidence)),
                            "deterministic_candidate": deterministic.model_dump(mode="json"),
                        },
                    )
                    payload.update(
                        {
                            "mode": "llm",
                            "provider": self._provider_name(self.provider),
                            "event_id": request.event_id,
                            "goal": request.goal,
                            "grounded": True,
                            "requires_approval": False,
                        }
                    )
                    narrative = GroundedNarrativeResponse.model_validate(payload)
                    self._validate_narrative(narrative, evidence)
                except Exception as exc:
                    narrative = deterministic.model_copy(
                        update={
                            "mode": "deterministic_fallback",
                            "provider": self._provider_name(self.provider),
                            "fallback_reason": type(exc).__name__,
                        }
                    )
        self._validate_narrative(narrative, evidence)
        return narrative

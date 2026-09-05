"""Canonical manufacturing operations application service."""

from __future__ import annotations

import copy
import os
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.common.company_context import load_company_context, public_company_context, retrieve_company_documents
from app.diagnosis.contracts import derive_features, load_fixture
from app.diagnosis.domain import (
    build_evidence_package,
    build_product_result_artifact,
    event_evidence_projection_to_legacy_evidence,
    product_result_artifact_to_event_evidence_projection,
)
from app.equipment.ports import EquipmentApplicationPort
from app.operations.agent_review_packet import compose_agent_review_packet
from app.operations.context_providers import AgentReviewContextRegistry
from app.operations.agent_review_summary_materialization import (
    AgentReviewSummaryMaterializer,
    summary_key,
    summary_key_payload,
)
from app.operations.agent_review_summary_provider import AgentReviewSummaryProvider
from app.operations.asset_detail_view_model import compose_asset_detail_view_model
from app.operations.domain_context_adapters import (
    DomainReviewContextAdapter,
    ManufacturingFixtureReviewContextAdapter,
)
from app.operations.operational_context_contract import OperationalRequestIdentity
from app.operations.operational_context_ports import (
    FixtureMaintenanceReadinessContextReadPort,
    FixtureProductionDecisionContextReadPort,
    FixtureQualityDeliveryContextReadPort,
)
from app.operations.operational_evidence_selection import (
    EvidenceSelectionStrategy,
    evaluate_evidence_selection,
    project_evidence_candidates,
    select_evidence_candidates,
)
from app.operations.operational_relation_resolver import resolve_operational_relations

from .context import ContextProviderFactory
from .contracts import (
    DecisionRequest,
    FollowUpRequest,
    FollowUpResponse,
    GroundedReport,
    Intent,
    LayoutRequest,
    NoteRequest,
    ReportRequest,
    UILayout,
)
from app.planner.contracts import IntentRouter, deterministic_answer
from .ports import (
    AuditRepositoryPort,
    CompanyContextQueryPort,
    LayoutPlannerPort,
    MaintenanceLineageQueryPort,
    ReportAgentPort,
)

RISK_PRIORITY = {"critical": 0, "warning": 1, "attention": 2, "data_quality_hold": 3, "normal": 4}
AGENT_REVIEW_RUNNING_LEASE_SECONDS = 120
_AGENT_REVIEW_SUMMARY_LOCKS: dict[str, Lock] = {}
_AGENT_REVIEW_SUMMARY_LOCKS_GUARD = Lock()


class EventNotFound(KeyError):
    pass


class ManufacturingPredictiveMaintenanceService:
    def __init__(
        self,
        root: str | Path,
        *,
        repository: AuditRepositoryPort,
        equipment_service: EquipmentApplicationPort,
        report_agent: ReportAgentPort,
        layout_planner: LayoutPlannerPort,
        context_provider_factory: ContextProviderFactory,
        agent_review_summary_provider: AgentReviewSummaryProvider | None = None,
        agent_answer_provider: Any | None = None,
        agent_review_context_registry: AgentReviewContextRegistry | None = None,
        domain_review_context_adapter: DomainReviewContextAdapter | None = None,
        maintenance_lineage_query: MaintenanceLineageQueryPort | None = None,
        company_context_query: CompanyContextQueryPort | None = None,
        knowledge_search: Any | None = None,
        workspace_id: str = "manufacturing-demo",
    ) -> None:
        self.root = Path(root)
        fixture_root = self.root / "data" / "fixtures"
        fixture_paths = sorted(
            path
            for pattern in ("GS-*.json", "AZ-*.json", "MPT-*.json")
            for path in fixture_root.glob(pattern)
        )
        self.project_fixtures = {
            payload["event_id"]: payload
            for payload in (load_fixture(path) for path in fixture_paths)
        }
        # Historical Gold regression and manufacturing Ontology projection must
        # remain exactly GS-001..GS-008. Showcase Project fixtures are available
        # through project_fixtures and project-scoped APIs, never this alias.
        self.fixtures = {
            event_id: fixture
            for event_id, fixture in self.project_fixtures.items()
            if self._fixture_project_id(fixture) == "manufacturing-demo-project"
        }
        self.equipment_service = equipment_service
        self.repository = repository
        self.report_agent = report_agent
        self.layout_planner = layout_planner
        self.context_provider_factory = context_provider_factory
        self.agent_review_summary_provider = agent_review_summary_provider
        self.agent_answer_provider = agent_answer_provider
        self.agent_review_context_registry = agent_review_context_registry
        self.maintenance_lineage_query = maintenance_lineage_query
        self.company_context_query = company_context_query
        self.knowledge_search = knowledge_search
        self.workspace_id = workspace_id
        self.domain_review_context_adapter = (
            domain_review_context_adapter
            or ManufacturingFixtureReviewContextAdapter(self.root)
        )
        self.intent_router = IntentRouter()

    def company_context(self, *, project_id: str, workspace_id: str) -> dict[str, Any]:
        """Return stable company masters with DB-backed operational records overlaid by id.

        Static reference data remains the bootstrap for stable masters. Once a record
        exists in persistence, the DB copy is authoritative for that project/workspace.
        """
        full = self._company_context_snapshot(project_id=project_id, workspace_id=workspace_id)
        base = public_company_context(full)
        base["context_storage"] = dict(full.get("context_storage") or {})
        return base

    def _company_context_snapshot(self, *, project_id: str, workspace_id: str) -> dict[str, Any]:
        """Return the full server-side corpus with persisted records overlaid by id."""

        base = copy.deepcopy(load_company_context())
        if self.company_context_query is None:
            return base
        try:
            records = self.company_context_query.list_records(project_id=project_id, workspace_id=workspace_id)
        except Exception:
            return base
        grouped: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            record_type = str(record.get("record_type") or "")
            payload = record.get("payload")
            if not record_type or not isinstance(payload, dict):
                continue
            payload = {
                **payload,
                "context_source": "team_db",
                "source_updated_at": record.get("source_updated_at"),
            }
            grouped.setdefault(record_type, []).append(payload)
        for record_type, persisted in grouped.items():
            existing = [dict(item) for item in base.get(record_type) or [] if isinstance(item, dict)]
            persisted_by_id = {
                str(item.get("id") or item.get("variant") or item.get("name")): item
                for item in persisted
            }
            merged = []
            seen: set[str] = set()
            for item in existing:
                key = str(item.get("id") or item.get("variant") or item.get("name"))
                merged.append(persisted_by_id.get(key, item))
                seen.add(key)
            merged.extend(item for key, item in persisted_by_id.items() if key not in seen)
            base[record_type] = merged
        base["context_storage"] = {
            "mode": "team_db_overlay" if records else "reference_bootstrap",
            "persisted_record_count": len(records),
        }
        return base

    def company_context_documents(
        self,
        query: str,
        *,
        project_id: str,
        workspace_id: str,
        asset_id: str | None = None,
        roles: list[str] | None = None,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        if self.knowledge_search is not None:
            try:
                indexed = self.knowledge_search.search_project(
                    query,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    roles=roles,
                    asset_id=asset_id,
                    top_k=top_k,
                )
                if indexed:
                    return indexed
            except Exception:
                # Retrieval remains read-only enrichment. Preserve the bounded,
                # source-referenced deterministic fallback when the index is
                # unavailable or being rebuilt.
                pass
        return retrieve_company_documents(
            query,
            asset_id=asset_id,
            roles=roles,
            top_k=top_k,
            context=self._company_context_snapshot(project_id=project_id, workspace_id=workspace_id),
        )

    def _closed_loop_context_for_fixture(
        self,
        fixture: dict[str, Any],
    ) -> dict[str, Any] | None:
        event_id = str(fixture.get("event_id") or "")
        if not event_id or self.maintenance_lineage_query is None:
            return fixture.get("closed_loop")
        try:
            lineage = self.maintenance_lineage_query.event_lineage(
                workspace_id=self.workspace_id,
                event_id=event_id,
            )
        except Exception:
            return fixture.get("closed_loop")
        context = _closed_loop_context_from_lineage(lineage)
        return context if _has_closed_loop_records(context) else fixture.get("closed_loop")

    def _fixture(self, event_id: str) -> dict[str, Any]:
        try:
            return self.project_fixtures[event_id]
        except KeyError as exc:
            raise EventNotFound(event_id) from exc

    def _context_provider(self, fixture: dict[str, Any]):
        return self.context_provider_factory(fixture)

    @staticmethod
    def _fixture_project_id(fixture: dict[str, Any]) -> str:
        return str(fixture.get("project_id") or "manufacturing-demo-project")

    def project_id_for_event(self, event_id: str) -> str:
        return self._fixture_project_id(self._fixture(event_id))

    def fixture_snapshot(self, event_id: str) -> dict[str, Any]:
        """Return the source snapshot through the Operations application boundary."""

        return self._fixture(event_id)

    def fixture_items(self) -> list[tuple[str, dict[str, Any]]]:
        return sorted(self.fixtures.items())

    def fixture_count(self) -> int:
        return len(self.fixtures)

    def event_activity(self, event_id: str) -> dict[str, Any]:
        return self.repository.event_activity(event_id)

    def record_audit(self, **command: Any) -> dict[str, Any]:
        return self.repository.record_audit(**command)

    def evidence_snapshot(self, event_id: str) -> dict[str, Any]:
        fixture = self._fixture(event_id)
        package = self._projected_legacy_evidence(fixture)
        package["lineage"]["project_id"] = self._fixture_project_id(fixture)
        if fixture.get("dataset_version"):
            package["lineage"]["dataset_version"] = str(fixture["dataset_version"])
        return package

    def event_evidence_projection(self, event_id: str, **_: Any) -> dict[str, Any]:
        fixture = self._fixture(event_id)
        projection = self._event_evidence_projection(fixture)
        projection["event_id"] = fixture["event_id"]
        projection["evidence_id"] = f"EVD-{fixture['event_id']}"
        projection["scenario_id"] = fixture["scenario_id"]
        projection["artifact_reference"]["event_id"] = fixture["event_id"]
        return projection

    def evidence(self, event_id: str, *, view: str = "legacy") -> dict[str, Any]:
        if view == "canonical":
            projection = self.event_evidence_projection(event_id)
            self._audit(
                event_id,
                "evidence.generated",
                projection["provenance"]["model_version"],
                {"event_id": projection["event_id"], "view": "canonical"},
            )
            return projection
        package = self.evidence_snapshot(event_id)
        self._audit(event_id, "evidence.generated", package["model"]["model_version"], {"evidence_id": package["evidence_id"]})
        return package

    def list_events(self, project_id: str = "manufacturing-demo-project") -> list[dict[str, Any]]:
        rows = []
        for event_id, fixture in self.project_fixtures.items():
            if self._fixture_project_id(fixture) != project_id:
                continue
            evidence = build_evidence_package(fixture, context_provider=self._context_provider(fixture))
            rows.append(
                {
                    "event_id": event_id,
                    "scenario_id": fixture["scenario_id"],
                    "equipment": fixture["equipment"],
                    "status": evidence["status"],
                    "failure_probability": evidence["failure_probability"],
                    "confidence": evidence["confidence"],
                    "predicted_failure_type": evidence["predicted_failure_type"],
                    "recommended_decision": evidence["recommended_decision"],
                }
            )
        return sorted(rows, key=lambda row: (RISK_PRIORITY[row["status"]], -(row["failure_probability"] or 0.0)))

    def list_equipment(self, project_id: str = "manufacturing-demo-project") -> list[dict[str, Any]]:
        return self.equipment_service.list_equipment(project_id)

    def equipment(self, equipment_id: str, project_id: str = "manufacturing-demo-project") -> dict[str, Any]:
        item = self.equipment_service.equipment(equipment_id, project_id)
        events = [
            event
            for event in self.list_events(project_id)
            if event["equipment"]["equipment_id"] == equipment_id
        ]
        return {**item, "events": events}

    def equipment_current_state(
        self, equipment_id: str, project_id: str = "manufacturing-demo-project"
    ) -> dict[str, Any] | None:
        return self.equipment_service.equipment_current_state(equipment_id, project_id)

    def asset_detail_view_model(
        self,
        asset_id: str,
        project_id: str = "manufacturing-demo-project",
        *,
        dataset_version_id: str | None = None,
        history_window: str = "24h",
    ) -> dict[str, Any]:
        fixture = self._fixture_for_asset(asset_id, project_id, dataset_version_id=dataset_version_id)
        artifact = self._product_result_artifact(fixture)
        asset = self._asset_summary_for_fixture(fixture, artifact)
        return compose_asset_detail_view_model(
            asset=asset,
            result_artifact=artifact,
            feature_series=self._feature_series_for_fixture(fixture, artifact),
            runtime_prediction_history=self._runtime_history_for_fixture(fixture, artifact),
            equipment_history=self._equipment_history_for_fixture(fixture),
            operation_context=self.domain_review_context_adapter.operation_context(
                fixture=fixture,
                artifact=artifact,
                project_id=self._fixture_project_id(fixture),
            ) or fixture.get("operation_context"),
            closed_loop=self._closed_loop_context_for_fixture(fixture),
            inspection_guidance=self.domain_review_context_adapter.inspection_guidance(
                fixture=fixture,
                artifact=artifact,
            ),
            inspection_locations=self.domain_review_context_adapter.inspection_locations(
                fixture=fixture,
                artifact=artifact,
            ),
            data_status={
                "source": "canonical",
                "last_updated_at": artifact["observed_at"],
                "warnings": [],
            },
            history_window=history_window,
            event_id=fixture.get("event_id"),
        )

    def agent_review_packet(
        self,
        asset_id: str,
        project_id: str = "manufacturing-demo-project",
        *,
        dataset_version_id: str | None = None,
        history_window: str = "24h",
    ) -> dict[str, Any]:
        fixture = self._fixture_for_asset(asset_id, project_id, dataset_version_id=dataset_version_id)
        artifact = self._product_result_artifact(fixture)
        view_model = self.asset_detail_view_model(
            asset_id,
            project_id,
            dataset_version_id=dataset_version_id,
            history_window=history_window,
        )
        return compose_agent_review_packet(
            project_id=project_id,
            view_model=view_model,
            sop_retrieval=self.domain_review_context_adapter.sop_retrieval(
                fixture=fixture,
                artifact=artifact,
            ),
            ontology_context=self.domain_review_context_adapter.ontology_context(
                fixture=fixture,
                artifact=artifact,
            ),
            context=(
                self.agent_review_context_registry.context_for_packet(
                    view_model=view_model,
                )
                if self.agent_review_context_registry
                else None
            ),
        )

    def agent_review_evidence_selection(
        self,
        asset_id: str,
        project_id: str = "manufacturing-demo-project",
        *,
        organization_id: str = "ORG-001",
        workspace_id: str = "manufacturing-demo",
        dataset_version_id: str | None = None,
        decision_as_of: datetime | None = None,
        retrieved_at: datetime | None = None,
        role: str = "process_manager",
        max_candidates: int = 8,
        required_evidence_ids: set[str] | None = None,
        required_limitation_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """Return S0/S1 evidence selection trace for versioned operation context."""

        fixture = self._fixture_for_asset(
            asset_id,
            project_id,
            dataset_version_id=dataset_version_id,
        )
        artifact = self._product_result_artifact(fixture)
        now = datetime.now(timezone.utc)
        identity = OperationalRequestIdentity(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            asset_id=asset_id,
            evidence_snapshot_id=str(artifact["artifact_id"]),
            decision_as_of=decision_as_of or now,
        )
        contexts = self._operational_selection_contexts(
            identity=identity,
            retrieved_at=retrieved_at or now,
        )
        relations = resolve_operational_relations(identity=identity, contexts=contexts)
        candidates = project_evidence_candidates(
            identity=identity,
            contexts=contexts,
            relation_resolution=relations,
        )
        full = select_evidence_candidates(
            candidates,
            strategy=EvidenceSelectionStrategy.FULL_CONTEXT,
        )
        selected = select_evidence_candidates(
            candidates,
            strategy=EvidenceSelectionStrategy.DETERMINISTIC,
            role=role,
            max_candidates=max_candidates,
        )
        metrics = evaluate_evidence_selection(
            full_context=full,
            selected=selected,
            required_evidence_ids=required_evidence_ids or set(),
            required_limitation_ids=required_limitation_ids or set(),
        )
        return {
            "schema_version": "agent-review-evidence-selection-v1.0",
            "asset_id": asset_id,
            "project_id": project_id,
            "identity": identity.model_dump(mode="json"),
            "relation_resolution": relations.model_dump(mode="json"),
            "strategies": {
                "S0": full.model_dump(mode="json"),
                "S1": selected.model_dump(mode="json"),
            },
            "metrics": metrics.model_dump(mode="json"),
            "mutation_allowed": False,
        }

    def agent_review_summary(
        self,
        asset_id: str,
        project_id: str = "manufacturing-demo-project",
        *,
        organization_id: str = "org-ontology-demo",
        workspace_id: str = "manufacturing-demo",
        dataset_version_id: str | None = None,
        history_window: str = "24h",
        trigger: str = "manual_materialization",
        engine: str = "simple",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Return a materialized read-only review summary for this evidence snapshot."""

        packet = self.agent_review_packet(
            asset_id,
            project_id,
            dataset_version_id=dataset_version_id,
            history_window=history_window,
        )
        materializer = AgentReviewSummaryMaterializer(
            self.repository,
            self.agent_review_summary_provider,
        )
        force = trigger == "ui_manual_regeneration"
        key_payload = summary_key_payload(
            packet=packet,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            history_window=history_window,
            provider=self.agent_review_summary_provider,
        )
        materialization_key = summary_key(key_payload)
        with _agent_review_summary_lock(materialization_key):
            if not force:
                cached_summary, cached_trace = materializer.lookup(
                    packet=packet,
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    history_window=history_window,
                )
                cached_status = (cached_trace.get("materialization") or {}).get("status")
                if cached_summary is not None and (
                    cached_status != "fallback" or self.agent_review_summary_provider is None
                ):
                    return cached_summary, cached_trace

            try:
                run = self._start_agent_review_workflow_run(
                    trigger=trigger,
                    engine=engine,
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    packet=packet,
                    key_payload=key_payload,
                    materialization_key=materialization_key,
                    materializer=materializer,
                    history_window=history_window,
                )
            except _AgentReviewSummaryMaterializedWhileWaiting as cached:
                return cached.result
            try:
                summary, trace = materializer.materialize(
                    packet=packet,
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    history_window=history_window,
                    workflow_run_id=run["workflow_run_id"],
                    force=force,
                    refresh_fallback=self.agent_review_summary_provider is not None,
                )
                status = _workflow_run_status(trace)
                finished = self.repository.finish_agent_review_workflow_run(
                    run["workflow_run_id"],
                    status=status,
                    trace={
                        "stage": "finished",
                        "materialization": trace.get("materialization") or {},
                        "provider": trace.get("provider"),
                        "fallback": trace.get("fallback"),
                        "reason": trace.get("reason"),
                        "validation_errors": trace.get("validation_errors") or [],
                    },
                )
                return summary, {
                    **trace,
                    "workflow_run": _workflow_run_trace(finished),
                }
            except Exception as exc:
                finished = self.repository.finish_agent_review_workflow_run(
                    run["workflow_run_id"],
                    status="failed",
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    trace={"stage": "failed", "error_type": type(exc).__name__},
                )
                raise RuntimeError(
                    f"agent_review_summary_workflow_failed:{finished['workflow_run_id']}"
                ) from exc

    def cached_agent_review_summary(
        self,
        asset_id: str,
        project_id: str = "manufacturing-demo-project",
        *,
        organization_id: str = "org-ontology-demo",
        workspace_id: str = "manufacturing-demo",
        dataset_version_id: str | None = None,
        history_window: str = "24h",
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Return a stored read-only review summary without triggering generation."""

        packet = self.agent_review_packet(
            asset_id,
            project_id,
            dataset_version_id=dataset_version_id,
            history_window=history_window,
        )
        summary, trace = AgentReviewSummaryMaterializer(
            self.repository,
            self.agent_review_summary_provider,
        ).lookup(
            packet=packet,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            history_window=history_window,
        )
        workflow_run_id = (trace.get("materialization") or {}).get("workflow_run_id")
        if isinstance(workflow_run_id, str) and workflow_run_id:
            run = self.repository.get_agent_review_workflow_run(workflow_run_id)
            if run is not None:
                trace = {**trace, "workflow_run": _workflow_run_trace(run)}
        return summary, trace

    def agent_review_workflow_runs(
        self,
        project_id: str = "manufacturing-demo-project",
        *,
        organization_id: str = "org-ontology-demo",
        workspace_id: str = "manufacturing-demo",
        asset_id: str | None = None,
        event_id: str | None = None,
        dataset_version_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        runs = self.repository.list_agent_review_workflow_runs(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            asset_id=asset_id,
            event_id=event_id,
            dataset_version_id=dataset_version_id,
            status=status,
            limit=limit,
        )
        return {
            "project_id": project_id,
            "workspace_id": workspace_id,
            "items": [_workflow_run_trace(run) for run in runs],
        }

    def materialize_agent_review_summaries(
        self,
        project_id: str = "manufacturing-demo-project",
        *,
        organization_id: str = "org-ontology-demo",
        workspace_id: str = "manufacturing-demo",
        history_window: str = "24h",
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Materialize missing Agent Review Summaries for project fixtures."""

        items: list[dict[str, Any]] = []
        fixtures = [
            fixture
            for fixture in self.project_fixtures.values()
            if self._fixture_project_id(fixture) == project_id
        ]
        fixtures = sorted(
            fixtures,
            key=lambda fixture: str((fixture.get("equipment") or {}).get("equipment_id") or ""),
        )
        if limit is not None:
            fixtures = fixtures[: max(0, limit)]

        for fixture in fixtures:
            asset_id = str((fixture.get("equipment") or {}).get("equipment_id") or "")
            if not asset_id:
                continue
            summary, trace = self.agent_review_summary(
                asset_id,
                project_id,
                organization_id=organization_id,
                workspace_id=workspace_id,
                dataset_version_id=fixture.get("dataset_version"),
                history_window=history_window,
                trigger="polling_watcher",
            )
            materialization = trace.get("materialization") or {}
            items.append(
                {
                    "asset_id": asset_id,
                    "event_id": fixture.get("event_id"),
                    "summary_id": materialization.get("summary_id"),
                    "summary_key": materialization.get("summary_key"),
                    "status": materialization.get("status"),
                    "reused": materialization.get("reused"),
                    "mode": summary.get("mode"),
                    "fallback_reason": materialization.get("fallback_reason"),
                    "workflow_run_id": (trace.get("workflow_run") or {}).get(
                        "workflow_run_id"
                    ),
                    "workflow_status": (trace.get("workflow_run") or {}).get(
                        "status"
                    ),
                }
            )

        return {
            "project_id": project_id,
            "history_window": history_window,
            "materialized_count": len(items),
            "created_count": sum(1 for item in items if not item.get("reused")),
            "reused_count": sum(1 for item in items if item.get("reused")),
            "items": items,
        }

    def patch_equipment_state(
        self,
        equipment_id: str,
        *,
        expected_state_version: int | None,
        state_patch: dict[str, Any],
        project_id: str = "manufacturing-demo-project",
    ) -> dict[str, Any]:
        return self.equipment_service.patch_equipment_state(
            equipment_id,
            expected_state_version=expected_state_version,
            state_patch=state_patch,
            project_id=project_id,
        )

    def event(self, event_id: str) -> dict[str, Any]:
        fixture = self._fixture(event_id)
        return {
            "event_id": event_id,
            "project_id": self._fixture_project_id(fixture),
            "scenario_id": fixture["scenario_id"],
            "equipment": fixture["equipment"],
            "observation": fixture["observation"],
            "history": fixture["history"],
            "runtime": fixture["runtime"],
            "activity": self.repository.event_activity(event_id),
        }

    def _operational_selection_contexts(
        self,
        *,
        identity: OperationalRequestIdentity,
        retrieved_at: datetime,
    ) -> dict[str, Any]:
        fixture_root = self.root / "data" / "fixtures" / "operation_context"

        def load_context(name: str) -> dict[str, Any]:
            return json.loads((fixture_root / name).read_text(encoding="utf-8"))

        return {
            "production": FixtureProductionDecisionContextReadPort(
                context=load_context("operational-decision-context-v1.json"),
                source_ref="fixture:production",
            ).lookup(identity=identity, retrieved_at=retrieved_at),
            "maintenance_readiness": FixtureMaintenanceReadinessContextReadPort(
                context=load_context("maintenance-readiness-context-v1.json"),
                source_ref="fixture:maintenance",
            ).lookup(identity=identity, retrieved_at=retrieved_at),
            "quality_delivery": FixtureQualityDeliveryContextReadPort(
                context=load_context("quality-delivery-context-v1.json"),
                source_ref="fixture:quality",
            ).lookup(identity=identity, retrieved_at=retrieved_at),
        }

    def _fixture_for_asset(
        self,
        asset_id: str,
        project_id: str,
        *,
        dataset_version_id: str | None = None,
    ) -> dict[str, Any]:
        for fixture in self.project_fixtures.values():
            if self._fixture_project_id(fixture) != project_id:
                continue
            if dataset_version_id and fixture.get("dataset_version") and fixture.get("dataset_version") != dataset_version_id:
                continue
            equipment = fixture.get("equipment") or {}
            if str(equipment.get("equipment_id")) == asset_id:
                return fixture
        raise EventNotFound(asset_id)

    @staticmethod
    def _asset_summary_for_fixture(fixture: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
        equipment = fixture.get("equipment") or {}
        last_maintenance_days_ago = _days_between(
            equipment.get("last_maintenance_date"),
            artifact["observed_at"],
        )
        estimated_downtime = equipment.get("estimated_downtime_minutes")
        return {
            "asset_id": artifact["asset_id"],
            "asset_type": equipment.get("asset_type") or artifact["asset_type"],
            "display_name": equipment.get("display_name") or artifact["asset_id"],
            "site_id": equipment.get("site_id") or artifact.get("site_id") or "Hanbit Tech Plant",
            "cell_id": equipment.get("cell_id") or equipment.get("line") or artifact.get("cell_id") or "unknown",
            "observed_at": artifact["observed_at"],
            "criticality": equipment.get("criticality"),
            "criticality_basis": ["fixture equipment.criticality"]
            if equipment.get("criticality") in {"low", "medium", "high"}
            else [],
            "criticality_source": "equipment_master"
            if equipment.get("criticality") in {"low", "medium", "high"}
            else "unknown",
            "maintenance_context": {
                "last_maintenance_days_ago": last_maintenance_days_ago,
                "similar_events_30d": None,
                "open_work_order_exists": None,
            },
            "operation_context": {
                "load_level": None,
                "runtime_hours_7d": None,
                "production_impact": _production_impact(estimated_downtime),
            },
        }

    @staticmethod
    def _feature_series_for_fixture(
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        feature_keys = list(
            dict.fromkeys(
                [
                    *(factor.get("feature") for factor in artifact.get("top_factors") or []),
                    *(
                        ((artifact.get("evidence_payload") or {}).get("sensor_evidence") or {})
                        .get("sensors", {})
                        .keys()
                    ),
                ]
            )
        )
        rows = fixture.get("history") or []
        current_observed_at = str(artifact["observed_at"])
        current_instant = _timestamp_instant(current_observed_at)
        series: dict[str, dict[str, Any]] = {}
        for key in feature_keys:
            points_by_instant: dict[datetime, dict[str, Any]] = {}
            for row in rows:
                derived_row: dict[str, Any] = {}
                try:
                    derived_row = derive_features(row)
                except (TypeError, ValueError):
                    derived_row = {}
                source_row = {**derived_row, **row}
                if key not in source_row:
                    continue
                observed_at = str(row.get("timestamp") or current_observed_at)
                instant = _timestamp_instant(observed_at)
                if instant >= current_instant:
                    continue
                point = {
                    "observed_at": observed_at,
                    "value": source_row.get(key),
                    "quality_status": "unknown"
                    if artifact.get("status_grade") == "data_quality_hold"
                    else "good",
                }
                if instant in points_by_instant and points_by_instant[instant] != point:
                    raise ValueError(
                        f"conflicting fixture history points at instant={instant.isoformat()}"
                    )
                points_by_instant[instant] = point
            points = [points_by_instant[instant] for instant in sorted(points_by_instant)]
            if points:
                series[str(key)] = {
                    "source_ref": f"observation-contract://{artifact['asset_id']}/{key}",
                    "points": points,
                }
        return series

    @staticmethod
    def _runtime_history_for_fixture(
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> list[dict[str, Any]]:
        points = []
        history = fixture.get("runtime_prediction_history") or fixture.get("prediction_history") or []
        for index, row in enumerate(history):
            if "failure_probability" not in row:
                continue
            observed_at = str(row.get("timestamp") or artifact["observed_at"])
            points.append(
                {
                    "observed_at": observed_at,
                    "failure_probability": row["failure_probability"],
                    "status_grade": row.get("status_grade") or row.get("status"),
                    "prediction_id": str(row.get("prediction_id") or f"{artifact['asset_id']}#{observed_at}#{index}"),
                    "source_kind": str(row.get("source_kind") or "runtime_inference"),
                    "source_ref": str(row.get("source_ref") or f"diagnosis-runtime-history://{artifact['asset_id']}/{observed_at}"),
                }
            )
        return points

    @staticmethod
    def _equipment_history_for_fixture(fixture: dict[str, Any]) -> list[dict[str, Any]]:
        equipment = fixture.get("equipment") or {}
        last_maintenance = equipment.get("last_maintenance_date")
        if not last_maintenance:
            return []
        return [
            {
                "occurred_at": f"{last_maintenance}T00:00:00+09:00",
                "kind": "maintenance",
                "tone": "normal",
                "description": "최근 정비 이력",
                "source": "equipment-maintenance-context",
            }
        ]

    def report(self, event_id: str, request: ReportRequest) -> tuple[GroundedReport, dict[str, Any]]:
        fixture = self._fixture(event_id)
        evidence = self._projected_legacy_evidence(fixture)
        self._attach_report_context(evidence, fixture, request.role)
        report, trace = self.report_agent.generate(
            evidence,
            request.role,
            locale=request.locale,
            use_llm=request.use_llm,
            provider_available=fixture["runtime"]["llm_available"],
            report_type=request.report_type,
        )
        self._audit(
            event_id,
            "report.generated",
            evidence["model"]["model_version"],
            {"report_id": report.report_id, "role": request.role, "report_type": report.report_type, "locale": request.locale, **trace},
        )
        return report, trace

    def _attach_report_context(self, evidence: dict[str, Any], fixture: dict[str, Any], role: str) -> None:
        equipment_id = str((fixture.get("equipment") or {}).get("equipment_id") or "")
        project_id = self._fixture_project_id(fixture)
        workspace_id = str(fixture.get("workspace_id") or self.workspace_id)
        goal = (
            "생산 영향 매출 공헌이익 자재 재고 운영 의사결정 회의 정비 이력"
            if role == "manager"
            else "설비 센서 점검 정비 이력 원인 근거 자재 작업 기록"
        )
        documents = self.company_context_documents(
            goal,
            project_id=project_id,
            workspace_id=workspace_id,
            asset_id=equipment_id or None,
            roles=["process_manager"] if role == "manager" else ["process_engineer"],
            top_k=8,
        )
        evidence["company_context_documents"] = [
            {
                "evidence_field_id": f"company_context.{item['id']}",
                "title": item.get("title"),
                "document_type": item.get("document_type"),
                "content": item.get("content"),
                "source_ref": item.get("source_ref"),
                "related_asset_ids": item.get("related_asset_ids") or [],
            }
            for item in documents
        ]

    def _event_evidence_projection(self, fixture: dict[str, Any]) -> dict[str, Any]:
        artifact = self._product_result_artifact(fixture)
        return product_result_artifact_to_event_evidence_projection(artifact)

    def _projected_legacy_evidence(self, fixture: dict[str, Any]) -> dict[str, Any]:
        artifact = self._product_result_artifact(fixture)
        projection = product_result_artifact_to_event_evidence_projection(artifact)
        legacy = event_evidence_projection_to_legacy_evidence(
            projection,
            ranked_factor_evidence=artifact.get("ranked_factor_evidence"),
        )
        legacy["event_id"] = fixture["event_id"]
        legacy["evidence_id"] = f"EVD-{fixture['event_id']}"
        legacy["scenario_id"] = fixture["scenario_id"]
        legacy["equipment"] = fixture["equipment"]
        return legacy

    def _product_result_artifact(self, fixture: dict[str, Any]) -> dict[str, Any]:
        return build_product_result_artifact(
            fixture,
            context_provider=self._context_provider(fixture),
        )

    def layout(self, event_id: str, request: LayoutRequest) -> tuple[UILayout, dict[str, Any]]:
        fixture = self._fixture(event_id)
        evidence = build_evidence_package(fixture, context_provider=self._context_provider(fixture))
        self._attach_report_context(evidence, fixture, request.role)
        report, report_trace = self.report_agent.generate(
            evidence,
            request.role,
            locale=request.locale,
            use_llm=request.use_llm,
            provider_available=fixture["runtime"]["llm_available"],
        )
        layout, layout_trace = self.layout_planner.plan(
            evidence,
            report,
            request.role,
            request.intent,
            locale=request.locale,
            use_llm=request.use_llm,
            provider_available=fixture["runtime"]["planner_available"],
        )
        trace = {"report": report_trace, "layout": layout_trace}
        self._audit(
            event_id,
            "layout.generated",
            evidence["model"]["model_version"],
            {"layout_id": layout.layout_id, "role": request.role, "intent": request.intent, **trace},
        )
        return layout, trace

    def decide(self, event_id: str, request: DecisionRequest) -> dict[str, Any]:
        self._fixture(event_id)
        record = self.repository.record_decision(event_id, request.actor, request.decision, request.note)
        self._audit(event_id, "decision.recorded", None, record)
        return record

    def note(self, event_id: str, request: NoteRequest) -> dict[str, Any]:
        self._fixture(event_id)
        record = self.repository.add_note(event_id, request.actor, request.body)
        self._audit(event_id, "note.recorded", None, {"note_id": record["id"], "actor": request.actor})
        return record

    def follow_up(self, event_id: str, request: FollowUpRequest) -> FollowUpResponse:
        fixture = self._fixture(event_id)
        evidence = build_evidence_package(fixture, context_provider=self._context_provider(fixture))
        routed = self.intent_router.route(request.question)
        intent: Intent = routed.intent
        report, report_trace = self.report_agent.generate(
            evidence,
            request.role,
            locale=request.locale,
            use_llm=False,
            provider_available=False,
        )
        layout, layout_trace = self.layout_planner.plan(
            evidence,
            report,
            request.role,
            intent,
            locale=request.locale,
            use_llm=False,
            provider_available=False,
        )
        answer = deterministic_answer(intent, evidence, routed.supported, request.locale)
        thread_id = f"THR-{event_id}-{request.role}"
        record = self.repository.add_conversation(
            thread_id,
            event_id,
            request.role,
            request.question,
            intent,
            answer,
        )
        return FollowUpResponse(
            thread_id=thread_id,
            event_id=event_id,
            role=request.role,
            intent=intent,
            answer=answer,
            report=report,
            layout=layout.model_dump(mode="python") if hasattr(layout, "model_dump") else layout,
            supported=routed.supported,
            audit={"conversation_id": record["id"], "reason": routed.reason, "report": report_trace, "layout": layout_trace},
        )

    def reset(self) -> dict[str, str]:
        self.repository.reset()
        return {"status": "reset", "scope": "decisions, notes, conversations, ontology actions, audit"}

    def _audit(self, event_id: str | None, action: str, model_version: str | None, payload: dict[str, Any]) -> None:
        self.repository.record_audit(
            event_id=event_id,
            run_id=str(uuid.uuid4()),
            action=action,
            model_version=model_version,
            payload=payload,
        )

    def _start_agent_review_workflow_run(
        self,
        *,
        trigger: str,
        engine: str,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        packet: dict[str, Any],
        key_payload: dict[str, Any],
        materialization_key: str,
        materializer: AgentReviewSummaryMaterializer,
        history_window: str,
    ) -> dict[str, Any]:
        record = {
            "trigger": trigger,
            "engine": engine,
            "status": "running",
            "organization_id": organization_id,
            "project_id": project_id,
            "workspace_id": workspace_id,
            "asset_id": packet.get("asset_id"),
            "event_id": key_payload["event_id"],
            "dataset_version_id": key_payload["dataset_version"],
            "history_window": history_window,
            "summary_key": materialization_key,
            "source_sha256": key_payload["source_sha256"],
            "context_sha256": key_payload["context_sha256"],
            "packet_schema_version": key_payload["packet_schema_version"],
            "prompt_version": key_payload["prompt_version"],
            "model_version": key_payload["model_version"],
            "trace": {"stage": "started"},
        }
        try:
            return self.repository.create_agent_review_workflow_run(**record)
        except Exception as exc:
            if not _is_agent_review_running_conflict(exc):
                raise
            waited = _wait_for_agent_review_summary(
                materializer,
                packet=packet,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                history_window=history_window,
            )
            if waited is not None:
                raise _AgentReviewSummaryMaterializedWhileWaiting(waited) from exc
            started_before = datetime.now(timezone.utc) - timedelta(
                seconds=AGENT_REVIEW_RUNNING_LEASE_SECONDS
            )
            expired = self.repository.expire_stale_agent_review_workflow_run(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                summary_key=materialization_key,
                started_before=started_before.isoformat(),
            )
            if expired is not None:
                try:
                    return self.repository.create_agent_review_workflow_run(**record)
                except Exception as retry_exc:
                    if not _is_agent_review_running_conflict(retry_exc):
                        raise
                    raise RuntimeError(
                        f"agent_review_summary_materialization_in_progress:{materialization_key}"
                    ) from retry_exc
            raise RuntimeError(
                f"agent_review_summary_materialization_in_progress:{materialization_key}"
            ) from exc


def _workflow_run_status(trace: dict[str, Any]) -> str:
    materialization = trace.get("materialization") or {}
    status = str(materialization.get("status") or "")
    if status == "ready":
        return "completed"
    if status == "fallback":
        return "partial"
    if status == "failed":
        return "failed"
    return "completed"


class _AgentReviewSummaryMaterializedWhileWaiting(Exception):
    def __init__(self, result: tuple[dict[str, Any], dict[str, Any]]) -> None:
        super().__init__("agent_review_summary_materialized_while_waiting")
        self.result = result


def _agent_review_summary_lock(summary_key_value: str) -> Lock:
    with _AGENT_REVIEW_SUMMARY_LOCKS_GUARD:
        lock = _AGENT_REVIEW_SUMMARY_LOCKS.get(summary_key_value)
        if lock is None:
            lock = Lock()
            _AGENT_REVIEW_SUMMARY_LOCKS[summary_key_value] = lock
        return lock


def _is_agent_review_running_conflict(exc: Exception) -> bool:
    text = f"{type(exc).__name__}:{exc}"
    return (
        "uq_agent_review_workflow_runs_running_summary" in text
        or "UNIQUE constraint failed: agent_review_workflow_runs.organization_id" in text
    )


def _wait_for_agent_review_summary(
    materializer: AgentReviewSummaryMaterializer,
    *,
    packet: dict[str, Any],
    organization_id: str,
    project_id: str,
    workspace_id: str,
    history_window: str,
    timeout_seconds: float = 3.0,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        summary, trace = materializer.lookup(
            packet=packet,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            history_window=history_window,
        )
        if summary is not None:
            return summary, trace
        time.sleep(0.05)
    return None


def _workflow_run_trace(run: dict[str, Any]) -> dict[str, Any]:
    return {
        "workflow_run_id": run["workflow_run_id"],
        "trigger": run["trigger"],
        "engine": run["engine"],
        "status": run["status"],
        "started_at": run["started_at"],
        "completed_at": run.get("completed_at"),
        "updated_at": run["updated_at"],
        "asset_id": run.get("asset_id"),
        "event_id": run.get("event_id"),
        "dataset_version_id": run.get("dataset_version_id"),
        "history_window": run.get("history_window"),
        "summary_key": run["summary_key"],
        "source_sha256": run["source_sha256"],
        "context_sha256": run["context_sha256"],
        "error_type": run.get("error_type"),
        "error_message": run.get("error_message"),
        "trace": run.get("trace") or {},
    }


def _timestamp_instant(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("fixture observation timestamps must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def _days_between(start_date: Any, end_timestamp: str) -> int | None:
    if not start_date:
        return None
    try:
        start = datetime.fromisoformat(f"{start_date}T00:00:00+09:00")
        end = datetime.fromisoformat(end_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, (end.date() - start.date()).days)


def _production_impact(estimated_downtime_minutes: Any) -> str | None:
    if not isinstance(estimated_downtime_minutes, int) or isinstance(estimated_downtime_minutes, bool):
        return None
    if estimated_downtime_minutes >= 180:
        return "high"
    if estimated_downtime_minutes >= 90:
        return "medium"
    if estimated_downtime_minutes > 0:
        return "low"
    return "none"


def _closed_loop_context_from_lineage(lineage: dict[str, Any]) -> dict[str, Any]:
    work_orders = [_work_order_context(item) for item in lineage.get("work_orders") or []]
    return {
        "work_orders": work_orders,
        "inspection_results": list(lineage.get("inspection_results") or []),
        "maintenance_actions": list(lineage.get("maintenance_actions") or []),
        "maintenance_events": list(lineage.get("maintenance_events") or []),
        "activities": list(lineage.get("activities") or []),
        "available_actions": _available_closed_loop_actions(work_orders),
        "runtime_status": None,
    }


def _has_closed_loop_records(context: dict[str, Any]) -> bool:
    return any(
        context.get(key)
        for key in (
            "work_orders",
            "inspection_results",
            "maintenance_actions",
            "maintenance_events",
            "activities",
        )
    )


def _work_order_context(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "work_order_id": str(item.get("work_order_id") or ""),
        "work_type": str(item.get("work_type") or ""),
        "status": str(item.get("status") or ""),
        "assigned_to": item.get("assigned_to"),
        "actor_display_name": item.get("actor_display_name"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _available_closed_loop_actions(work_orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions = []
    for work_order in work_orders:
        if work_order.get("work_type") != "inspection" or work_order.get("status") != "requested":
            continue
        work_order_id = str(work_order.get("work_order_id") or "")
        actions.append(
            {
                "action_id": "approve_inspection_work_order",
                "target_type": "work_order",
                "target_id": work_order_id,
                "label": "점검 승인",
                "disabled_reason": (
                    "데모 ViewModel은 읽기 전용입니다. 실제 승인은 Closed-loop mutation API 연결 후 처리합니다."
                ),
            }
        )
    return actions


# Temporary compatibility alias for integrations that still import the historical
# service name. New code should use ManufacturingPredictiveMaintenanceService.
FactorySignalService = ManufacturingPredictiveMaintenanceService

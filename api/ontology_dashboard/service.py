"""Canonical manufacturing demonstration application service."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from ontology_dashboard_manufacturing_ml import build_evidence_package, load_fixture
from ontology_dashboard_manufacturing_ml.evidence import FixtureContextProvider
from ontology_dashboard.migrations import migrate
from ontology_dashboard.settings import database_location

from .context import ResilientContextProvider
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
from .conversation import IntentRouter, deterministic_answer
from .llm import ReportAgent, configured_provider
from .planner import LayoutPlanner
from .repository import AuditRepository

RISK_PRIORITY = {"critical": 0, "warning": 1, "attention": 2, "data_quality_hold": 3, "normal": 4}


class EventNotFound(KeyError):
    pass


class ManufacturingPredictiveMaintenanceService:
    def __init__(
        self,
        root: str | Path,
        *,
        database_path: str | Path | None = None,
        repository: AuditRepository | None = None,
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
        database = database_path or database_location(self.root)
        if repository is None:
            migrate(str(database))
            repository = AuditRepository(database)
        self.repository = repository
        self.provider = configured_provider()
        self.report_agent = ReportAgent(self.root, self.provider)
        self.layout_planner = LayoutPlanner(self.root, self.provider)
        self.intent_router = IntentRouter()

    def _fixture(self, event_id: str) -> dict[str, Any]:
        try:
            return self.project_fixtures[event_id]
        except KeyError as exc:
            raise EventNotFound(event_id) from exc

    def _context_provider(self, fixture: dict[str, Any]):
        if fixture["runtime"]["context_provider"] == "project3_http":
            return ResilientContextProvider()
        return FixtureContextProvider()

    @staticmethod
    def _fixture_project_id(fixture: dict[str, Any]) -> str:
        return str(fixture.get("project_id") or "manufacturing-demo-project")

    def project_id_for_event(self, event_id: str) -> str:
        return self._fixture_project_id(self._fixture(event_id))

    def evidence_snapshot(self, event_id: str) -> dict[str, Any]:
        fixture = self._fixture(event_id)
        package = build_evidence_package(fixture, context_provider=self._context_provider(fixture))
        package["lineage"]["project_id"] = self._fixture_project_id(fixture)
        if fixture.get("dataset_version"):
            package["lineage"]["dataset_version"] = str(fixture["dataset_version"])
        return package

    def evidence(self, event_id: str) -> dict[str, Any]:
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
        unique: dict[str, dict[str, Any]] = {}
        for fixture in self.project_fixtures.values():
            if self._fixture_project_id(fixture) != project_id:
                continue
            equipment = fixture["equipment"]
            unique[equipment["equipment_id"]] = equipment
        return sorted(unique.values(), key=lambda item: item["equipment_id"])

    def equipment(self, equipment_id: str, project_id: str = "manufacturing-demo-project") -> dict[str, Any]:
        for item in self.list_equipment(project_id):
            if item["equipment_id"] == equipment_id:
                events = [event for event in self.list_events(project_id) if event["equipment"]["equipment_id"] == equipment_id]
                return {**item, "events": events}
        raise EventNotFound(equipment_id)

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

    def report(self, event_id: str, request: ReportRequest) -> tuple[GroundedReport, dict[str, Any]]:
        fixture = self._fixture(event_id)
        evidence = build_evidence_package(fixture, context_provider=self._context_provider(fixture))
        report, trace = self.report_agent.generate(
            evidence,
            request.role,
            use_llm=request.use_llm,
            provider_available=fixture["runtime"]["llm_available"],
        )
        self._audit(
            event_id,
            "report.generated",
            evidence["model"]["model_version"],
            {"report_id": report.report_id, "role": request.role, **trace},
        )
        return report, trace

    def layout(self, event_id: str, request: LayoutRequest) -> tuple[UILayout, dict[str, Any]]:
        fixture = self._fixture(event_id)
        evidence = build_evidence_package(fixture, context_provider=self._context_provider(fixture))
        report, report_trace = self.report_agent.generate(
            evidence,
            request.role,
            use_llm=request.use_llm,
            provider_available=fixture["runtime"]["llm_available"],
        )
        layout, layout_trace = self.layout_planner.plan(
            evidence,
            report,
            request.role,
            request.intent,
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
            use_llm=False,
            provider_available=False,
        )
        layout, layout_trace = self.layout_planner.plan(
            evidence,
            report,
            request.role,
            intent,
            use_llm=False,
            provider_available=False,
        )
        answer = deterministic_answer(intent, evidence, routed.supported)
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
            layout=layout,
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


# Temporary compatibility alias for integrations that still import the historical
# service name. New code should use ManufacturingPredictiveMaintenanceService.
FactorySignalService = ManufacturingPredictiveMaintenanceService

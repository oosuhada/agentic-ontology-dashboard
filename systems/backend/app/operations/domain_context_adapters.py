"""Domain context adapters for read-only Operations review enrichment."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from app.operations.sop_retrieval import retrieve_inspection_sops


class DomainReviewContextAdapter(Protocol):
    """Read-only adapter for domain-specific review context.

    Implementations may enrich UI/report/AI review inputs with operational
    context, inspection references, and SOP retrieval results. They must not
    create or approve closed-loop state.
    """

    adapter_id: str

    def operation_context(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
        project_id: str,
    ) -> dict[str, Any] | None:
        """Return production/operations context for the selected snapshot."""

    def inspection_guidance(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Return SOP-backed guidance keyed by Product Evidence component id."""

    def inspection_locations(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Return displayable inspection-location references keyed by component id."""

    def sop_retrieval(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        """Return read-only SOP retrieval candidates for agent review."""

    def ontology_context(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        """Return read-only factor/component/location/SOP relationship context."""


class _FixtureOperationContextAdapter:
    def __init__(self, contexts: list[dict[str, Any]]) -> None:
        self.contexts = contexts

    def operation_context(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
        project_id: str,
    ) -> dict[str, Any] | None:
        equipment = fixture.get("equipment") or {}
        dataset_version = str(fixture.get("dataset_version") or "")
        observed_at = _parse_iso_datetime(
            str((fixture.get("observation") or {}).get("timestamp") or artifact.get("observed_at") or "")
        )
        if observed_at is None:
            return None

        for context in self.contexts:
            if not {
                "source_type",
                "production_plan",
                "capacity_model",
            }.issubset(context):
                continue
            scope = context.get("scope") or {}
            if str(scope.get("project_id") or "") != project_id:
                continue
            if dataset_version and str(scope.get("dataset_version") or "") != dataset_version:
                continue
            temporal_scope = context.get("temporal_scope") or {}
            valid_from = _parse_iso_datetime(str(temporal_scope.get("valid_from") or ""))
            valid_to = _parse_iso_datetime(str(temporal_scope.get("valid_to") or ""))
            if valid_from is None or valid_to is None or not (valid_from <= observed_at < valid_to):
                continue
            fixture_context = fixture.get("operation_context") or {}
            event_impact = fixture_context.get("event_impact") or _event_impact_for_fixture(context, fixture, equipment)
            capacity = context.get("capacity_model") or {}
            planning_window = capacity.get("planning_window") or {}
            oee_basis = capacity.get("oee_basis") or {}
            cycle_time_basis = capacity.get("cycle_time_basis") or {}
            asset_count_basis = capacity.get("asset_count_basis") or {}
            production_impact = fixture_context.get("production_impact")
            if production_impact not in {"none", "low", "medium", "high"}:
                production_impact = _production_impact(
                    (event_impact or {}).get("basis", {}).get("estimated_downtime_minutes")
                    if event_impact
                    else equipment.get("estimated_downtime_minutes")
                )
            return {
                "load_level": fixture_context.get("load_level"),
                "runtime_hours_7d": fixture_context.get("runtime_hours_7d"),
                "production_impact": production_impact,
                "context_id": context["context_id"],
                "source_type": context["source_type"],
                "temporal_scope": temporal_scope,
                "production_plan": context["production_plan"],
                "capacity_model": {
                    "active_asset_count": asset_count_basis.get("active_asset_count"),
                    "planned_operating_hours": planning_window.get("planned_operating_hours"),
                    "oee": oee_basis.get("oee"),
                    "standard_cycle_minutes_per_unit": cycle_time_basis.get("standard_cycle_minutes_per_unit"),
                    "asset_units_per_hour": capacity.get("asset_units_per_hour"),
                    "daily_capacity_units": capacity.get("daily_capacity_units"),
                    "basis": (
                        f"{asset_count_basis.get('active_asset_count')} assets, "
                        f"{planning_window.get('planned_operating_hours')}h/day, "
                        f"OEE {oee_basis.get('oee')}, "
                        f"cycle {cycle_time_basis.get('standard_cycle_minutes_per_unit')}min 기준"
                    ),
                },
                "event_impact": event_impact,
                "limitations": context.get("limitations") or [],
            }
        return None


class _FixtureSopContextAdapter:
    def __init__(self, procedures: list[dict[str, Any]]) -> None:
        self.procedures = procedures

    def sop_retrieval(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        return retrieve_inspection_sops(
            fixture=fixture,
            artifact=artifact,
            procedures=self.procedures,
        )

    def inspection_guidance(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        component_ids = _component_ids(artifact)
        guidance_by_component: dict[str, dict[str, Any]] = {}
        for sop in self._matching_inspection_sops(fixture=fixture, artifact=artifact):
            for component_id in component_ids.intersection({str(item) for item in sop.get("component_ids") or []}):
                guidance = sop.get("guidance") or {}
                guidance_by_component[component_id] = {
                    "source_type": sop["source_kind"],
                    "sop_id": sop["sop_id"],
                    "title": sop["title"],
                    "version": sop["version"],
                    "reference_location_label": guidance.get("reference_location_label"),
                    "suggested_check_method": guidance.get("suggested_check_method"),
                    "checklist_draft": guidance.get("checklist_draft") or [],
                    "maintenance_review_prerequisites": guidance.get(
                        "maintenance_review_prerequisites"
                    )
                    or {},
                    "safety_level": sop["safety_level"],
                    "requires_human_approval": sop["requires_human_approval"],
                    "source_ref": f"{sop['source_uri']}#{sop['sop_id']}",
                    "disclaimer": guidance.get("disclaimer"),
                }
        return guidance_by_component

    def _matching_inspection_sops(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            item["procedure"]
            for item in self.sop_retrieval(fixture=fixture, artifact=artifact)["results"]
        ]


class _FixtureInspectionLocationAdapter:
    def __init__(self, references: list[dict[str, Any]]) -> None:
        self.references = references

    def inspection_locations(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        component_ids = _component_ids(artifact)
        asset_type = str(artifact.get("asset_type") or fixture.get("asset_type") or "")
        references: dict[str, dict[str, Any]] = {}
        for contract in self.references:
            if asset_type and asset_type not in {str(item) for item in contract.get("asset_types") or []}:
                continue
            for location in contract.get("locations") or []:
                component_id = str(location.get("component_id") or "")
                if component_id not in component_ids:
                    continue
                references[component_id] = {
                    "contract_id": contract.get("contract_id"),
                    "maturity": contract.get("maturity"),
                    "location_label": location.get("location_label"),
                    "inspection_method": location.get("inspection_method"),
                    "source_ref": f"{contract['source_uri']}#{component_id}",
                }
        return references


class _FixtureOntologyContextAdapter:
    def __init__(
        self,
        *,
        location_adapter: _FixtureInspectionLocationAdapter,
        sop_adapter: _FixtureSopContextAdapter,
        spare_part_contexts: list[dict[str, Any]],
        similar_event_contexts: list[dict[str, Any]],
    ) -> None:
        self.location_adapter = location_adapter
        self.sop_adapter = sop_adapter
        self.spare_part_contexts = spare_part_contexts
        self.similar_event_contexts = similar_event_contexts

    def ontology_context(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        """Compose a fixture-backed ontology traversal trace for agent packets."""

        locations = self.location_adapter.inspection_locations(
            fixture=fixture,
            artifact=artifact,
        )
        sop = self.sop_adapter.sop_retrieval(fixture=fixture, artifact=artifact)
        sop_results_by_id = _sop_results_by_id(sop)
        factor_refs_by_component = _factor_refs_by_component(artifact)
        component_hypotheses = (
            (artifact.get("evidence_payload") or {}).get("component_hypotheses") or []
        )
        traversals = []
        for hypothesis in component_hypotheses:
            if not isinstance(hypothesis, dict):
                continue
            component_id = str(hypothesis.get("component_id") or "")
            if not component_id:
                continue
            location = locations.get(component_id) or {}
            matched_sop_ids = _matched_sop_ids(component_id, sop_results_by_id)
            factor_refs = factor_refs_by_component.get(component_id, [])
            factor_keys = _factor_keys(factor_refs)
            spare_parts = self._matched_spare_parts(
                fixture=fixture,
                artifact=artifact,
                component_id=component_id,
            )
            similar_events = self._matched_similar_events(
                fixture=fixture,
                artifact=artifact,
                component_id=component_id,
                factor_keys=factor_keys,
            )
            traversals.append(
                {
                    "component_id": component_id,
                    "component_label": str(hypothesis.get("component_label") or ""),
                    "factor_refs": factor_refs,
                    "location_label": location.get("location_label"),
                    "location_source_ref": location.get("source_ref"),
                    "sop_ids": matched_sop_ids,
                    "spare_parts": spare_parts,
                    "similar_events": similar_events,
                    "source_refs": [
                        ref
                        for ref in [
                            str(hypothesis.get("source_ref") or ""),
                            str(location.get("source_ref") or ""),
                            *[
                                str(sop_results_by_id[sop_id].get("source_ref") or "")
                                for sop_id in matched_sop_ids
                            ],
                            *[str(item.get("source_ref") or "") for item in spare_parts],
                            *[str(item.get("source_ref") or "") for item in similar_events],
                        ]
                        if ref
                    ],
                }
            )
        return {
            "provider": "manufacturing_fixture_ontology_context",
            "mutation_allowed": False,
            "traversals": traversals,
            "source_refs": list(
                dict.fromkeys(
                    ref
                    for traversal in traversals
                    for ref in traversal.get("source_refs", [])
                    if ref
                )
            ),
        }

    def _matched_spare_parts(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
        component_id: str,
    ) -> list[dict[str, Any]]:
        asset_type = str(artifact.get("asset_type") or fixture.get("asset_type") or "")
        equipment = fixture.get("equipment") or {}
        part_available = equipment.get("spare_part_available")
        matches: list[dict[str, Any]] = []
        for context in self.spare_part_contexts:
            asset_types = {str(item) for item in context.get("asset_types") or []}
            if asset_type and asset_type not in asset_types:
                continue
            for part in context.get("parts") or []:
                if str(part.get("component_id") or "") != component_id:
                    continue
                matches.append(
                    {
                        "part_id": str(part.get("part_id") or ""),
                        "part_label": str(part.get("part_label") or ""),
                        "replacement_scope": str(part.get("replacement_scope") or ""),
                        "availability": _spare_part_availability(part_available),
                        "lead_time_days": part.get("lead_time_days"),
                        "replacement_window_minutes": part.get(
                            "replacement_window_minutes"
                        ),
                        "assumption_level": str(context.get("assumption_level") or ""),
                        "source_ref": f"{context['source_uri']}#{part.get('part_id')}",
                    }
                )
        return matches

    def _matched_similar_events(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
        component_id: str,
        factor_keys: list[str],
    ) -> list[dict[str, Any]]:
        asset_type = str(artifact.get("asset_type") or fixture.get("asset_type") or "")
        factor_key_set = set(factor_keys)
        matches: list[dict[str, Any]] = []
        for context in self.similar_event_contexts:
            asset_types = {str(item) for item in context.get("asset_types") or []}
            if asset_type and asset_type not in asset_types:
                continue
            for event in context.get("events") or []:
                event_factor_keys = {str(item) for item in event.get("factor_keys") or []}
                if str(event.get("component_id") or "") != component_id:
                    continue
                if factor_key_set and not factor_key_set.intersection(event_factor_keys):
                    continue
                matches.append(
                    {
                        "similar_event_id": str(event.get("similar_event_id") or ""),
                        "asset_label": str(event.get("asset_label") or ""),
                        "observed_at": str(event.get("observed_at") or ""),
                        "matched_factor_keys": sorted(
                            factor_key_set.intersection(event_factor_keys)
                        ),
                        "action_taken": str(event.get("action_taken") or ""),
                        "outcome": str(event.get("outcome") or ""),
                        "post_action_observation_window_hours": event.get(
                            "post_action_observation_window_hours"
                        ),
                        "assumption_level": str(context.get("assumption_level") or ""),
                        "source_ref": (
                            f"{context['source_uri']}#{event.get('similar_event_id')}"
                        ),
                    }
                )
        return matches


class ManufacturingFixtureReviewContextAdapter:
    """Reference-backed manufacturing domain adapter used by Operations."""

    adapter_id = "manufacturing-fixture-review-context"

    def __init__(self, root: str | Path) -> None:
        fixture_root = Path(root) / "data" / "fixtures"
        self.operation_contexts = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((fixture_root / "operation_context").glob("*.json"))
        ]
        self.inspection_sops = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((fixture_root / "inspection_sop").glob("*.json"))
        ]
        self.inspection_location_references = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((fixture_root / "inspection_location").glob("*.json"))
        ]
        self.spare_part_contexts = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((fixture_root / "spare_part").glob("*.json"))
        ]
        self.similar_event_contexts = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((fixture_root / "similar_event").glob("*.json"))
        ]
        self.operation_adapter = _FixtureOperationContextAdapter(self.operation_contexts)
        self.sop_adapter = _FixtureSopContextAdapter(self.inspection_sops)
        self.location_adapter = _FixtureInspectionLocationAdapter(
            self.inspection_location_references
        )
        self.ontology_adapter = _FixtureOntologyContextAdapter(
            location_adapter=self.location_adapter,
            sop_adapter=self.sop_adapter,
            spare_part_contexts=self.spare_part_contexts,
            similar_event_contexts=self.similar_event_contexts,
        )

    def operation_context(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
        project_id: str,
    ) -> dict[str, Any] | None:
        return self.operation_adapter.operation_context(
            fixture=fixture,
            artifact=artifact,
            project_id=project_id,
        )

    def inspection_guidance(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        self.sop_adapter.procedures = self.inspection_sops
        return self.sop_adapter.inspection_guidance(fixture=fixture, artifact=artifact)

    def inspection_locations(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        return self.location_adapter.inspection_locations(
            fixture=fixture,
            artifact=artifact,
        )

    def sop_retrieval(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        self.sop_adapter.procedures = self.inspection_sops
        return self.sop_adapter.sop_retrieval(fixture=fixture, artifact=artifact)

    def ontology_context(
        self,
        *,
        fixture: dict[str, Any],
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        return self.ontology_adapter.ontology_context(fixture=fixture, artifact=artifact)

def _component_ids(artifact: dict[str, Any]) -> set[str]:
    component_hypotheses = (
        (artifact.get("evidence_payload") or {}).get("component_hypotheses") or []
    )
    return {
        str(item.get("component_id"))
        for item in component_hypotheses
        if isinstance(item, dict) and item.get("component_id")
    }


def _factor_refs_by_component(artifact: dict[str, Any]) -> dict[str, list[str]]:
    component_hypotheses = (
        (artifact.get("evidence_payload") or {}).get("component_hypotheses") or []
    )
    refs: dict[str, list[str]] = {}
    for hypothesis in component_hypotheses:
        if not isinstance(hypothesis, dict):
            continue
        component_id = str(hypothesis.get("component_id") or "")
        if not component_id:
            continue
        refs[component_id] = [
            str(item)
            for item in hypothesis.get("basis") or []
            if str(item).startswith("factor.")
        ]
    return refs


def _factor_keys(factor_refs: list[str]) -> list[str]:
    keys = []
    for ref in factor_refs:
        parts = ref.split(".", 2)
        if len(parts) == 3 and ref.startswith("factor."):
            keys.append(parts[2])
    return keys


def _spare_part_availability(value: Any) -> str:
    if value is True:
        return "available_from_fixture"
    if value is False:
        return "unavailable_from_fixture"
    return "unknown"


def _sop_results_by_id(sop_retrieval: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str((item.get("procedure") or {}).get("sop_id") or ""): item
        for item in sop_retrieval.get("results") or []
        if str((item.get("procedure") or {}).get("sop_id") or "")
    }


def _matched_sop_ids(
    component_id: str,
    sop_results_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    return sorted(
        sop_id
        for sop_id, result in sop_results_by_id.items()
        if component_id
        in {str(item) for item in (result.get("procedure") or {}).get("component_ids") or []}
    )


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


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _event_impact_for_fixture(
    context: dict[str, Any],
    fixture: dict[str, Any],
    equipment: dict[str, Any],
) -> dict[str, Any] | None:
    event_id = str(fixture.get("event_id") or "")
    equipment_id = str(equipment.get("equipment_id") or "")
    for impact in context.get("event_impacts") or []:
        if str(impact.get("event_id") or "") == event_id:
            return {**impact, "equipment_id": equipment_id or str(impact.get("equipment_id") or "")}
    for impact in context.get("event_impacts") or []:
        if str(impact.get("equipment_id") or "") == equipment_id:
            return {**impact, "equipment_id": equipment_id}
    return None

from __future__ import annotations

import re
import uuid
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from app.ontology.ontology_domain import OBJECT_TYPE_BY_ID
from model.contracts import (
    CapabilityEvaluation,
    CapabilityStatus,
    DatasetIntakeProfile,
    MappingEvidence,
    MappingSet,
    OntologyMappingCandidate,
    canonical_checksum,
)


class MappingLLMSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_field: str
    target_object_type: str | None = None
    target_property: str | None = None
    semantic_role: str
    confidence: float
    rationale: str


class MappingLLMProvider(Protocol):
    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]: ...


ALIASES: tuple[tuple[re.Pattern[str], str, str, str], ...] = (
    (re.compile(r"^(?:machine|equipment|asset|device)(?:_?id)?$", re.I), "telemetry_observation", "equipment_id", "identifier"),
    (re.compile(r"^(?:datetime|timestamp|time|observed_at|date)$", re.I), "telemetry_observation", "observed_at", "timestamp"),
    (re.compile(r"^(?:volt|voltage|voltage_v)$", re.I), "telemetry_observation", "voltage_v", "measure"),
    (re.compile(r"^(?:rotate|rotation|rotation_speed|rotational_speed_rpm|rpm)$", re.I), "telemetry_observation", "rotational_speed_rpm", "measure"),
    (re.compile(r"^pressure(?:_.*)?$", re.I), "telemetry_observation", "pressure", "measure"),
    (re.compile(r"^vibration(?:_.*)?$", re.I), "telemetry_observation", "vibration", "measure"),
    (re.compile(r"^(?:air_temperature|air_temperature_k|air_temp)$", re.I), "telemetry_observation", "air_temperature_k", "measure"),
    (re.compile(r"^(?:process_temperature|process_temperature_k|process_temp)$", re.I), "telemetry_observation", "process_temperature_k", "measure"),
    (re.compile(r"^(?:torque|torque_nm)$", re.I), "telemetry_observation", "torque_nm", "measure"),
    (re.compile(r"^(?:tool_wear|tool_wear_min|wear)$", re.I), "telemetry_observation", "tool_wear_min", "measure"),
    (re.compile(r"^(?:failure|machine_failure|label|target)$", re.I), "telemetry_observation", "machine_failure", "status"),
    (re.compile(r"^(?:model|product_type|type)$", re.I), "telemetry_observation", "product_type", "dimension"),
    (re.compile(r"^(?:age|equipment_age|equipment_age_years)$", re.I), "telemetry_observation", "equipment_age_years", "measure"),
    (re.compile(r"^(?:site|site_id)$", re.I), "production_cell", "site_id", "dimension"),
    (re.compile(r"^(?:line|production_line)$", re.I), "equipment", "line", "dimension"),
    (re.compile(r"^(?:criticality)$", re.I), "equipment", "criticality", "dimension"),
    (re.compile(r"^(?:assigned_engineer|engineer)$", re.I), "equipment", "assigned_engineer", "dimension"),
)


def registered_target(object_type: str | None, property_id: str | None) -> bool:
    if object_type is None or property_id is None:
        return object_type is None and property_id is None
    definition = OBJECT_TYPE_BY_ID.get(object_type)
    return definition is not None and property_id in {item.id for item in definition.properties}


def property_contract(object_type: str, property_id: str) -> tuple[str, str | None]:
    definition = OBJECT_TYPE_BY_ID[object_type]
    property_ = next(item for item in definition.properties if item.id == property_id)
    return property_.value_type, property_.unit


def _deterministic_candidate(profile: DatasetIntakeProfile, field_name: str) -> OntologyMappingCandidate:
    field = next(item for item in profile.field_profiles if item.name == field_name)
    matched = next(
        (
            (object_type, property_id, semantic_role)
            for pattern, object_type, property_id, semantic_role in ALIASES
            if pattern.search(field_name)
        ),
        None,
    )
    profile_semantics = set(field.semantic_candidates)
    critical = bool({"identifier", "timestamp", "group_key"}.intersection(profile_semantics))
    if matched is None:
        semantic_role = (
            "measure"
            if field.inferred_datatype in {"integer", "number"}
            else "dimension"
            if field.inferred_datatype in {"string", "boolean"}
            else "unresolved"
        )
        return OntologyMappingCandidate(
            candidate_id=f"map-candidate-{uuid.uuid5(uuid.NAMESPACE_URL, profile.profile_id + ':' + field_name)}",
            source_field=field_name,
            semantic_role=semantic_role,
            critical_field=critical,
            confidence=0.0,
            evidences=[
                MappingEvidence(
                    source="rule",
                    detail="No registered Object Type/Property alias matched; candidate remains unresolved.",
                    score=0.0,
                )
            ],
            status="unresolved",
        )
    object_type, property_id, semantic_role = matched
    datatype, registered_unit = property_contract(object_type, property_id)
    unit_hint = field.summary.get("unit_hint")
    evidences = [
        MappingEvidence(
            source="rule",
            detail=f"field alias matched registered {object_type}.{property_id}",
            score=0.94,
        )
    ]
    if unit_hint:
        evidences.append(
            MappingEvidence(
                source="unit_metadata",
                detail=f"profile unit hint={unit_hint}; registry unit={registered_unit or 'unspecified'}",
                score=0.8,
            )
        )
    critical = critical or property_id in {"equipment_id", "observed_at", "machine_failure"}
    return OntologyMappingCandidate(
        candidate_id=f"map-candidate-{uuid.uuid5(uuid.NAMESPACE_URL, profile.profile_id + ':' + field_name)}",
        source_field=field_name,
        target_object_type=object_type,
        target_property=property_id,
        datatype=datatype,
        physical_unit=registered_unit,
        grain="observation" if object_type == "telemetry_observation" else "object",
        semantic_role=semantic_role,
        group_key=property_id == "equipment_id",
        join_key=property_id in {"equipment_id", "site_id"},
        critical_field=critical,
        confidence=0.94,
        evidences=evidences,
        status="proposed",
    )


def generate_mapping_set(
    profile: DatasetIntakeProfile,
    *,
    dataset_version_id: str,
    version: int,
    idempotency_key: str,
    use_llm: bool = False,
    provider: MappingLLMProvider | None = None,
) -> MappingSet:
    candidates = [_deterministic_candidate(profile, item.name) for item in profile.field_profiles]
    if use_llm and provider is not None:
        by_field = {candidate.source_field: candidate for candidate in candidates}
        registry = {
            object_type: [property_.id for property_ in definition.properties]
            for object_type, definition in OBJECT_TYPE_BY_ID.items()
        }
        for source_field, current in list(by_field.items()):
            try:
                suggestion = MappingLLMSuggestion.model_validate(
                    provider.generate_json(
                        "Return one existing Object Type/Property pair or null. Never invent registry entries.",
                        {
                            "source_field": source_field,
                            "profile": next(
                                item.model_dump(mode="json")
                                for item in profile.field_profiles
                                if item.name == source_field
                            ),
                            "registry": registry,
                            "deterministic_candidate": current.model_dump(mode="json"),
                        },
                    )
                )
                if suggestion.source_field != source_field or not registered_target(
                    suggestion.target_object_type,
                    suggestion.target_property,
                ):
                    raise ValueError("LLM suggestion is outside the registry")
                if suggestion.target_object_type and suggestion.target_property:
                    datatype, unit = property_contract(
                        suggestion.target_object_type,
                        suggestion.target_property,
                    )
                    current = current.model_copy(
                        update={
                            "target_object_type": suggestion.target_object_type,
                            "target_property": suggestion.target_property,
                            "datatype": datatype,
                            "physical_unit": unit,
                            "semantic_role": suggestion.semantic_role,
                            "confidence": max(0.0, min(1.0, suggestion.confidence)),
                            "status": "proposed",
                            "evidences": [
                                *current.evidences,
                                MappingEvidence(
                                    source="llm_suggestion",
                                    detail=suggestion.rationale,
                                    score=max(0.0, min(1.0, suggestion.confidence)),
                                ),
                            ],
                        }
                    )
                by_field[source_field] = current
            except (ValidationError, ValueError, TypeError):
                continue
        candidates = [by_field[item.source_field] for item in candidates]
    checksum = canonical_checksum([item.model_dump(mode="json") for item in candidates])
    mapping_set_id = f"mapping-set-{uuid.uuid5(uuid.NAMESPACE_URL, f'{profile.profile_id}:{dataset_version_id}:{version}:{checksum}')}"
    return MappingSet(
        organization_id=profile.organization_id,
        project_id=profile.project_id,
        workspace_id=profile.workspace_id,
        mapping_set_id=mapping_set_id,
        dataset_version_id=dataset_version_id,
        version=version,
        checksum_sha256=checksum,
        candidates=candidates,
        idempotency_key=idempotency_key,
    )


def update_candidate(
    candidate: OntologyMappingCandidate,
    *,
    decision: str,
    target_object_type: str | None,
    target_property: str | None,
    datatype: str | None,
    physical_unit: str | None,
    grain: str | None,
    semantic_role: str | None,
    group_key: bool | None,
    join_key: bool | None,
    actor_id: str,
    rationale: str,
) -> OntologyMappingCandidate:
    if decision == "reject":
        return candidate.model_copy(
            update={
                "status": "rejected",
                "evidences": [
                    *candidate.evidences,
                    MappingEvidence(
                        source="user_confirmation",
                        detail=f"rejected by {actor_id}: {rationale}",
                        score=1.0,
                    ),
                ],
            }
        )
    object_type = target_object_type if decision == "edit" else candidate.target_object_type
    property_id = target_property if decision == "edit" else candidate.target_property
    if not registered_target(object_type, property_id) or object_type is None or property_id is None:
        raise ValueError("approved mapping must target a registered Object Type/Property")
    registered_datatype, registered_unit = property_contract(object_type, property_id)
    resolved_datatype = datatype or registered_datatype
    if resolved_datatype != registered_datatype:
        raise ValueError("mapping datatype conflicts with registered property datatype")
    return candidate.model_copy(
        update={
            "target_object_type": object_type,
            "target_property": property_id,
            "datatype": resolved_datatype,
            "physical_unit": physical_unit if physical_unit is not None else registered_unit,
            "grain": grain or candidate.grain or "observation",
            "semantic_role": semantic_role or candidate.semantic_role,
            "group_key": candidate.group_key if group_key is None else group_key,
            "join_key": candidate.join_key if join_key is None else join_key,
            "status": "approved",
            "confidence": 1.0,
            "evidences": [
                *candidate.evidences,
                MappingEvidence(
                    source="user_confirmation",
                    detail=f"approved by {actor_id}: {rationale}",
                    score=1.0,
                ),
            ],
        }
    )


def validate_mapping_set_for_approval(mapping_set: MappingSet) -> None:
    for candidate in mapping_set.candidates:
        if candidate.critical_field and candidate.status != "approved":
            raise ValueError(f"critical field requires approval: {candidate.source_field}")
        if candidate.status == "approved" and not registered_target(
            candidate.target_object_type,
            candidate.target_property,
        ):
            raise ValueError(f"mapping targets unknown registry value: {candidate.source_field}")
    approved = [item for item in mapping_set.candidates if item.status == "approved"]
    if not approved:
        raise ValueError("Mapping Set requires at least one approved candidate")


CAPABILITY_PREREQUISITES: dict[str, tuple[str, ...]] = {
    "predictive_training": ("group_key", "timestamp", "measure", "label"),
    "predictive_scoring": ("group_key", "timestamp", "measure"),
    "maintenance_context": ("equipment_identifier", "maintenance_reference"),
    "replay_time_series": ("group_key", "timestamp", "measure"),
    "explanation": ("group_key", "timestamp", "measure"),
}


def evaluate_capabilities(mapping_set: MappingSet) -> list[CapabilityEvaluation]:
    approved = [item for item in mapping_set.candidates if item.status == "approved"]
    signals = {
        "group_key": any(item.group_key for item in approved),
        "equipment_identifier": any(
            item.target_property == "equipment_id" or item.semantic_role == "identifier"
            for item in approved
        ),
        "timestamp": any(item.semantic_role == "timestamp" for item in approved),
        "measure": any(item.semantic_role == "measure" for item in approved),
        "label": any(item.target_property == "machine_failure" for item in approved),
        "maintenance_reference": any(
            item.target_object_type in {"work_order", "maintenance_action"} for item in approved
        ),
    }
    results: list[CapabilityEvaluation] = []
    for capability, prerequisites in CAPABILITY_PREREQUISITES.items():
        missing = [item for item in prerequisites if not signals.get(item, False)]
        satisfied = [item for item in prerequisites if signals.get(item, False)]
        status = CapabilityStatus.READY if not missing else CapabilityStatus.BLOCKED
        results.append(
            CapabilityEvaluation(
                organization_id=mapping_set.organization_id,
                project_id=mapping_set.project_id,
                workspace_id=mapping_set.workspace_id,
                evaluation_id=f"capability-{uuid.uuid5(uuid.NAMESPACE_URL, mapping_set.mapping_set_id + ':' + capability)}",
                dataset_version_id=mapping_set.dataset_version_id,
                mapping_set_id=mapping_set.mapping_set_id,
                capability=capability,
                status=status,
                satisfied_prerequisites=satisfied,
                missing_prerequisites=missing,
            )
        )
    return results


__all__ = [
    "CAPABILITY_PREREQUISITES",
    "MappingLLMProvider",
    "evaluate_capabilities",
    "generate_mapping_set",
    "registered_target",
    "update_candidate",
    "validate_mapping_set_for_approval",
]

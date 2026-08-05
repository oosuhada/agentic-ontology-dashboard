from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from io import StringIO

import pandas as pd

from ..adapters.models import (
    DatasetManifest,
    DatasetSchema,
    DatasetSource,
    EvidenceSource,
    PredictionEvidence,
    PredictionModel,
    PredictionResult,
    PredictionSubject,
    PredictionValue,
    QualityRule,
    RecommendedAction,
)
from ..adapters.prediction_repository import PredictionResultRepository
from .artifacts import ArtifactStoreBlocked, LocalArtifactStore
from .intake import DatasetIntakeProfiler, IntakeLLMProvider, draft_from_profile
from .mapping import (
    MappingLLMProvider,
    evaluate_capabilities,
    generate_mapping_set,
    update_candidate,
    validate_mapping_set_for_approval,
)
from .features import (
    materialize_feature_dataset,
    read_source_for_profile,
    validate_recipe_set,
)
from .experiments import dependency_capabilities, run_experiment
from .registry import input_schema_checksum, score_model, threshold_from_experiment_report
from .models import (
    CapabilityEvaluation,
    DatasetIntakeProfile,
    ManifestDraft,
    ManifestDraftDecisionRequest,
    ManifestDraftUpdateRequest,
    ManifestIngestRequest,
    FeatureDatasetVersion,
    FeatureMaterializationRequest,
    FeatureRecipeSet,
    FeatureRecipeSetCreateRequest,
    FeatureRecipeSetDecisionRequest,
    CandidateResult,
    ExperimentCreateRequest,
    ExperimentCancelRequest,
    ExperimentRecoverRequest,
    ExperimentRetryRequest,
    ExperimentRun,
    ExplanationArtifact,
    MappingCandidateDecisionRequest,
    MappingSet,
    MappingSetDecisionRequest,
    ModelingContractSummary,
    ModelActivateRequest,
    ModelReleaseDecisionRequest,
    ModelReleaseRequestCreate,
    ModelReleaseRequestRecord,
    ModelRollbackRequest,
    ModelScoreRequest,
    ModelScoreResult,
    ModelVersion,
    ModelVersionCreateRequest,
    canonical_checksum,
)
from .repository import ModelingRepository


class ExperimentCancelled(RuntimeError):
    pass


class ModelingService:
    def __init__(
        self,
        repository: ModelingRepository,
        *,
        artifact_store: LocalArtifactStore | None = None,
        artifact_blocked_reason: str | None = None,
        intake_profiler: DatasetIntakeProfiler | None = None,
        mapping_provider: MappingLLMProvider | None = None,
        prediction_repository: PredictionResultRepository | None = None,
    ) -> None:
        self.repository = repository
        self.artifact_store = artifact_store
        self.artifact_blocked_reason = artifact_blocked_reason
        self.intake_profiler = intake_profiler
        self.mapping_provider = mapping_provider
        self.prediction_repository = prediction_repository

    @classmethod
    def configured(
        cls,
        database: str,
        artifact_root: str | None,
        *,
        intake_roots: list[str | Path] | None = None,
        intake_provider: IntakeLLMProvider | None = None,
        mapping_provider: MappingLLMProvider | None = None,
        prediction_repository: PredictionResultRepository | None = None,
    ) -> "ModelingService":
        profiler = (
            DatasetIntakeProfiler(intake_roots, provider=intake_provider)
            if intake_roots
            else None
        )
        try:
            store = LocalArtifactStore(artifact_root)
            return cls(
                ModelingRepository(database),
                artifact_store=store,
                intake_profiler=profiler,
                mapping_provider=mapping_provider,
                prediction_repository=prediction_repository,
            )
        except ArtifactStoreBlocked as exc:
            return cls(
                ModelingRepository(database),
                artifact_store=None,
                artifact_blocked_reason=str(exc),
                intake_profiler=profiler,
                mapping_provider=mapping_provider,
                prediction_repository=prediction_repository,
            )

    def contract_summary(self) -> ModelingContractSummary:
        return ModelingContractSummary(
            contracts=[
                "dataset_intake_profile",
                "manifest_draft",
                "ontology_mapping_candidate",
                "capability_evaluation",
                "feature_recipe_set",
                "feature_dataset_version",
                "experiment_run",
                "model_version",
                "threshold_policy",
                "explanation_artifact",
            ],
            artifact_store="ready" if self.artifact_store is not None else "blocked",
        )

    def artifact_capability(self) -> dict[str, Any]:
        return {
            "status": "ready" if self.artifact_store is not None else "blocked",
            "reason": self.artifact_blocked_reason,
            "canonical_uri_scheme": "artifact://",
            "local_path_is_identity": False,
        }

    def profile_source(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        source_path: str,
        sheet: str | None,
        use_llm: bool,
        idempotency_key: str,
        actor_id: str,
    ) -> DatasetIntakeProfile:
        if self.intake_profiler is None:
            raise RuntimeError("Dataset Intake roots are not configured")
        profile = self.intake_profiler.profile(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            source_path=source_path,
            sheet=sheet,
            use_llm=use_llm,
            idempotency_key=idempotency_key,
        )
        stored = DatasetIntakeProfile.model_validate(
            self.repository.put(
                "intake_profile",
                profile.model_dump(mode="json"),
                idempotency_key=idempotency_key,
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.intake.profiled",
            aggregate_type="DatasetIntakeProfile",
            aggregate_id=stored.profile_id,
            payload={
                "source_checksum_sha256": stored.source_checksum_sha256,
                "parser_version": stored.parser_version,
                "status": stored.status,
            },
        )
        return stored

    def intake_profile(
        self,
        profile_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> DatasetIntakeProfile:
        return DatasetIntakeProfile.model_validate(
            self.repository.get(
                "intake_profile",
                profile_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        )

    def create_manifest_draft(
        self,
        *,
        profile_id: str,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        idempotency_key: str,
        actor_id: str,
    ) -> ManifestDraft:
        profile = self.intake_profile(
            profile_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        draft = draft_from_profile(profile, idempotency_key=idempotency_key)
        stored = ManifestDraft.model_validate(
            self.repository.put(
                "manifest_draft",
                draft.model_dump(mode="json"),
                idempotency_key=idempotency_key,
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.manifest_draft.created",
            aggregate_type="ManifestDraft",
            aggregate_id=stored.draft_id,
            payload={"profile_id": profile_id, "revision": stored.revision},
        )
        return stored

    def manifest_draft(
        self,
        draft_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> ManifestDraft:
        return ManifestDraft.model_validate(
            self.repository.get(
                "manifest_draft",
                draft_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        )

    def update_manifest_draft(
        self,
        draft_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ManifestDraftUpdateRequest,
        actor_id: str,
    ) -> ManifestDraft:
        updates = request.model_dump(
            mode="json",
            exclude={"project_id", "workspace_id", "expected_revision"},
            exclude_none=True,
        )
        updated = ManifestDraft.model_validate(
            self.repository.update(
                "manifest_draft",
                draft_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                expected_revision=request.expected_revision,
                updated_payload=updates,
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.manifest_draft.updated",
            aggregate_type="ManifestDraft",
            aggregate_id=draft_id,
            payload={"revision": updated.revision, "updated_fields": sorted(updates)},
        )
        return updated

    def decide_manifest_draft(
        self,
        draft_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ManifestDraftDecisionRequest,
        actor_id: str,
    ) -> ManifestDraft:
        target = {
            "approve": "approved",
            "reject": "rejected",
            "supersede": "superseded",
        }[request.decision]
        current = self.manifest_draft(
            draft_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if target == "approved":
            if current.missing_prerequisites:
                raise ValueError("Manifest Draft has unresolved prerequisites")
            selected = [item for item in current.field_suggestions if item.selected]
            if not selected:
                raise ValueError("Manifest Draft must select at least one field")
            essential = [item for item in current.field_suggestions if item.essential_key]
            if any(not item.selected for item in essential):
                raise ValueError("essential identifier/timestamp/group keys require explicit selection")
        updated = ManifestDraft.model_validate(
            self.repository.transition(
                "manifest_draft",
                draft_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                target_status=target,
                expected_revision=request.expected_revision,
                transition_kind="review",
                updated_payload={
                    "approved_by": actor_id if target == "approved" else None,
                    "decision_rationale": request.rationale,
                },
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=f"modeling.manifest_draft.{target}",
            aggregate_type="ManifestDraft",
            aggregate_id=draft_id,
            payload={"revision": updated.revision, "rationale": request.rationale},
        )
        return updated

    def approved_manifest_payload(
        self,
        draft_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        draft = self.manifest_draft(
            draft_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(draft.status) != "approved":
            raise ValueError("Dataset ingestion requires an approved Manifest Draft")
        profile = self.intake_profile(
            draft.profile_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        return {
            "source": {
                "uri": profile.source_uri,
                "checksum_sha256": profile.source_checksum_sha256,
                "media_type": profile.media_type,
            },
            "format": draft.format,
            "encoding": draft.encoding,
            "delimiter": draft.delimiter,
            "sheet": draft.sheet,
            "selected_fields": [
                item.model_dump(mode="json") for item in draft.field_suggestions if item.selected
            ],
            "quality_rules": draft.quality_rules,
            "approval": {
                "draft_id": draft.draft_id,
                "revision": draft.revision,
                "approved_by": draft.approved_by,
                "rationale": draft.decision_rationale,
            },
        }

    def adapter_manifest(
        self,
        draft_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ManifestIngestRequest,
    ) -> DatasetManifest:
        draft = self.manifest_draft(
            draft_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(draft.status) != "approved":
            raise ValueError("Dataset ingestion requires an approved Manifest Draft")
        if draft.missing_prerequisites:
            raise ValueError(
                "Manifest Draft still has missing prerequisites: "
                + ", ".join(draft.missing_prerequisites)
            )
        profile = self.intake_profile(
            draft.profile_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        selected = [item for item in draft.field_suggestions if item.selected]
        if not selected:
            raise ValueError("approved Manifest Draft has no selected fields")
        aliases: dict[str, list[str]] = {}
        required_fields: list[str] = []
        primary_key: list[str] = []
        timestamp_field: str | None = None
        for item in selected:
            canonical = item.canonical_field or item.source_field
            aliases.setdefault(canonical, [])
            if item.source_field != canonical:
                aliases[canonical].append(item.source_field)
            if item.required and canonical not in required_fields:
                required_fields.append(canonical)
            if item.essential_key and canonical not in primary_key:
                primary_key.append(canonical)
            if canonical == "observed_at":
                timestamp_field = canonical
        quality_rules = [QualityRule.model_validate(item) for item in draft.quality_rules]
        return DatasetManifest(
            manifest_id=draft.draft_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            adapter_code="governed-tabular",
            dataset_name=request.dataset_name,
            dataset_version=request.dataset_version,
            license=request.license,
            provenance_url=request.provenance_url,
            source=DatasetSource(
                uri=profile.source_uri,
                media_type=profile.media_type,
                checksum_sha256=profile.source_checksum_sha256,
                size_bytes=profile.byte_size,
                encoding=draft.encoding or "utf-8",
            ),
            schema=DatasetSchema(
                format=draft.format,
                delimiter=draft.delimiter,
                sheet=draft.sheet,
                required_fields=required_fields,
                field_aliases=aliases,
                primary_key=primary_key,
                timestamp_field=timestamp_field,
                timezone="UTC",
            ),
            quality_rules=quality_rules,
        )

    def create_mapping_set(
        self,
        *,
        profile_id: str,
        dataset_version_id: str,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        use_llm: bool,
        idempotency_key: str,
        actor_id: str,
    ) -> MappingSet:
        profile = self.intake_profile(
            profile_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        existing = self.repository.list(
            "mapping_set",
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=500,
        )
        versions = [
            int(item.get("version", 0))
            for item in existing
            if item.get("dataset_version_id") == dataset_version_id
        ]
        mapping_set = generate_mapping_set(
            profile,
            dataset_version_id=dataset_version_id,
            version=max(versions, default=0) + 1,
            idempotency_key=idempotency_key,
            use_llm=use_llm,
            provider=self.mapping_provider,
        )
        stored = MappingSet.model_validate(
            self.repository.put(
                "mapping_set",
                mapping_set.model_dump(mode="json"),
                idempotency_key=idempotency_key,
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.mapping_set.created",
            aggregate_type="MappingSet",
            aggregate_id=stored.mapping_set_id,
            payload={
                "profile_id": profile_id,
                "dataset_version_id": dataset_version_id,
                "candidate_count": len(stored.candidates),
            },
        )
        return stored

    def mapping_set(
        self,
        mapping_set_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> MappingSet:
        return MappingSet.model_validate(
            self.repository.get(
                "mapping_set",
                mapping_set_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        )

    def decide_mapping_candidate(
        self,
        mapping_set_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: MappingCandidateDecisionRequest,
        actor_id: str,
    ) -> MappingSet:
        current = self.mapping_set(
            mapping_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(current.status) != "draft":
            raise ValueError("approved/rejected Mapping Set is immutable; create a new version")
        found = False
        candidates = []
        for candidate in current.candidates:
            if candidate.candidate_id != request.candidate_id:
                candidates.append(candidate)
                continue
            found = True
            candidates.append(
                update_candidate(
                    candidate,
                    decision=request.decision,
                    target_object_type=request.target_object_type,
                    target_property=request.target_property,
                    datatype=request.datatype,
                    physical_unit=request.physical_unit,
                    grain=request.grain,
                    semantic_role=request.semantic_role,
                    group_key=request.group_key,
                    join_key=request.join_key,
                    actor_id=actor_id,
                    rationale=request.rationale,
                )
            )
        if not found:
            raise KeyError(request.candidate_id)
        checksum = canonical_checksum([item.model_dump(mode="json") for item in candidates])
        updated = MappingSet.model_validate(
            self.repository.update(
                "mapping_set",
                mapping_set_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                expected_revision=request.expected_revision,
                updated_payload={
                    "candidates": [item.model_dump(mode="json") for item in candidates],
                    "checksum_sha256": checksum,
                },
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=f"modeling.mapping_candidate.{request.decision}",
            aggregate_type="MappingSet",
            aggregate_id=mapping_set_id,
            payload={
                "candidate_id": request.candidate_id,
                "revision": updated.revision,
                "rationale": request.rationale,
            },
        )
        return updated

    def decide_mapping_set(
        self,
        mapping_set_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: MappingSetDecisionRequest,
        actor_id: str,
    ) -> MappingSet:
        current = self.mapping_set(
            mapping_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        target = {
            "approve": "approved",
            "reject": "rejected",
            "supersede": "superseded",
        }[request.decision]
        if target == "approved":
            validate_mapping_set_for_approval(current)
        updated = MappingSet.model_validate(
            self.repository.transition(
                "mapping_set",
                mapping_set_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                target_status=target,
                expected_revision=request.expected_revision,
                transition_kind="review",
                updated_payload={"approved_by": actor_id if target == "approved" else None},
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=f"modeling.mapping_set.{target}",
            aggregate_type="MappingSet",
            aggregate_id=mapping_set_id,
            payload={"revision": updated.revision, "rationale": request.rationale},
        )
        return updated

    def clone_mapping_set(
        self,
        mapping_set_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        idempotency_key: str,
        actor_id: str,
    ) -> MappingSet:
        current = self.mapping_set(
            mapping_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        clone_payload = current.model_dump(mode="json")
        clone_payload.update(
            {
                "mapping_set_id": f"mapping-set-{canonical_checksum({'source': mapping_set_id, 'key': idempotency_key})[:24]}",
                "version": current.version + 1,
                "status": "draft",
                "approved_by": None,
                "revision": 1,
                "idempotency_key": idempotency_key,
            }
        )
        clone = MappingSet.model_validate(clone_payload)
        stored = MappingSet.model_validate(
            self.repository.put(
                "mapping_set",
                clone.model_dump(mode="json"),
                idempotency_key=idempotency_key,
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.mapping_set.version_created",
            aggregate_type="MappingSet",
            aggregate_id=stored.mapping_set_id,
            payload={"source_mapping_set_id": mapping_set_id, "version": stored.version},
        )
        return stored

    def mapping_capabilities(
        self,
        mapping_set_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> list[CapabilityEvaluation]:
        mapping_set = self.mapping_set(
            mapping_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        return evaluate_capabilities(mapping_set)

    def create_feature_recipe_set(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: FeatureRecipeSetCreateRequest,
        actor_id: str,
    ) -> FeatureRecipeSet:
        raw_mapping = self.repository.get(
            "mapping_set",
            request.mapping_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        mapping_set = MappingSet.model_validate(raw_mapping)
        if mapping_set.dataset_version_id != request.dataset_version_id:
            raise ValueError("Feature Recipe Set Dataset Version does not match Mapping Set")
        existing = self.repository.list(
            "recipe_set",
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=500,
        )
        versions = [
            int(item.get("version", 0))
            for item in existing
            if item.get("dataset_version_id") == request.dataset_version_id
        ]
        version = max(versions, default=0) + 1
        checksum = canonical_checksum(
            {
                "dataset_version_id": request.dataset_version_id,
                "mapping_set_id": request.mapping_set_id,
                "mapping_set_checksum": mapping_set.checksum_sha256,
                "recipes": [item.model_dump(mode="json") for item in request.recipes],
                "label_policy": request.label_policy.model_dump(mode="json"),
            }
        )
        recipe_set = FeatureRecipeSet(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            recipe_set_id=f"recipe-set-{checksum[:24]}",
            dataset_version_id=request.dataset_version_id,
            mapping_set_id=request.mapping_set_id,
            version=version,
            checksum_sha256=checksum,
            recipes=request.recipes,
            label_policy=request.label_policy,
            validation_report={},
            idempotency_key=request.idempotency_key,
        )
        validation = validate_recipe_set(recipe_set, mapping_set)
        approved_source_fields = {
            str(item["source_field"]): str(item["target_property"])
            for item in raw_mapping["candidates"]
            if item.get("status") == "approved" and item.get("target_property")
        }
        if not approved_source_fields:
            raise ValueError("Feature Recipe Set requires approved source mappings")
        validation["approved_source_fields"] = approved_source_fields
        validation["mapping_set_checksum_sha256"] = raw_mapping["checksum_sha256"]
        recipe_set = recipe_set.model_copy(update={"validation_report": validation})
        stored = FeatureRecipeSet.model_validate(
            self.repository.put(
                "recipe_set",
                recipe_set.model_dump(mode="json"),
                idempotency_key=request.idempotency_key,
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.feature_recipe_set.created",
            aggregate_type="FeatureRecipeSet",
            aggregate_id=stored.recipe_set_id,
            payload={
                "dataset_version_id": stored.dataset_version_id,
                "mapping_set_id": stored.mapping_set_id,
                "recipe_count": len(stored.recipes),
            },
        )
        return stored

    def feature_recipe_set(
        self,
        recipe_set_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> FeatureRecipeSet:
        return FeatureRecipeSet.model_validate(
            self.repository.get(
                "recipe_set",
                recipe_set_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        )

    def decide_feature_recipe_set(
        self,
        recipe_set_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: FeatureRecipeSetDecisionRequest,
        actor_id: str,
    ) -> FeatureRecipeSet:
        current = self.feature_recipe_set(
            recipe_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        target = {
            "approve": "approved",
            "reject": "rejected",
            "supersede": "superseded",
        }[request.decision]
        if target == "approved":
            mapping_set = self.mapping_set(
                current.mapping_set_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
            validate_recipe_set(current, mapping_set)
        updated = FeatureRecipeSet.model_validate(
            self.repository.transition(
                "recipe_set",
                recipe_set_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                target_status=target,
                expected_revision=request.expected_revision,
                transition_kind="review",
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=f"modeling.feature_recipe_set.{target}",
            aggregate_type="FeatureRecipeSet",
            aggregate_id=recipe_set_id,
            payload={"revision": updated.revision, "rationale": request.rationale},
        )
        return updated

    def materialize_features(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: FeatureMaterializationRequest,
        actor_id: str,
    ) -> FeatureDatasetVersion:
        if self.artifact_store is None:
            raise RuntimeError(self.artifact_blocked_reason or "artifact store unavailable")
        profile = self.intake_profile(
            request.profile_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        recipe_set = self.feature_recipe_set(
            request.recipe_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(recipe_set.status) != "approved":
            raise ValueError("Feature materialization requires an approved Feature Recipe Set")
        mapping_set = self.mapping_set(
            recipe_set.mapping_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        frame = read_source_for_profile(profile.source_uri, {})
        result = materialize_feature_dataset(
            source_frame=frame,
            mapping_set=mapping_set,
            recipe_set=recipe_set,
            artifact_store=self.artifact_store,
            idempotency_key=request.idempotency_key,
            approved_source_mapping=dict(
                recipe_set.validation_report.get("approved_source_fields", {})
            ),
        )
        stored = FeatureDatasetVersion.model_validate(
            self.repository.put(
                "feature_dataset",
                result.dataset_version.model_dump(mode="json"),
                idempotency_key=request.idempotency_key,
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.feature_dataset.materialized",
            aggregate_type="FeatureDatasetVersion",
            aggregate_id=stored.feature_dataset_version_id,
            payload={
                "dataset_version_id": stored.dataset_version_id,
                "recipe_set_id": stored.recipe_set_id,
                "row_count": stored.row_count,
                "materialization_checksum_sha256": stored.materialization_checksum_sha256,
            },
        )
        return stored

    def feature_dataset_version(
        self,
        feature_dataset_version_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> FeatureDatasetVersion:
        return FeatureDatasetVersion.model_validate(
            self.repository.get(
                "feature_dataset",
                feature_dataset_version_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        )

    def queue_experiment(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ExperimentCreateRequest,
        actor_id: str,
    ) -> ExperimentRun:
        feature_version = self.feature_dataset_version(
            request.feature_dataset_version_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(feature_version.status) != "succeeded" or feature_version.artifact is None:
            raise ValueError("Experiment requires a succeeded Feature Dataset Version artifact")
        recipe_set = self.feature_recipe_set(
            feature_version.recipe_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(recipe_set.status) != "approved":
            raise ValueError("Experiment requires an approved Feature Recipe Set")
        mapping_set = self.mapping_set(
            feature_version.mapping_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(mapping_set.status) != "approved":
            raise ValueError("Experiment requires an approved Mapping Set")
        algorithms = list(dict.fromkeys(request.algorithms))
        if not algorithms:
            raise ValueError("Experiment requires at least one algorithm")
        candidates = [
            CandidateResult(
                candidate_id=f"candidate-{algorithm}-queued",
                algorithm=algorithm,
                status="queued",
            )
            for algorithm in algorithms
        ]
        identity_payload = {
            "feature_dataset_version_id": request.feature_dataset_version_id,
            "split_policy": request.split_policy.model_dump(mode="json"),
            "algorithms": algorithms,
            "random_seed": request.random_seed,
            "recall_target": request.recall_target,
            "false_negative_cost": request.false_negative_cost,
            "false_positive_cost": request.false_positive_cost,
            "idempotency_key": request.idempotency_key,
        }
        experiment_id = f"experiment-{canonical_checksum(identity_payload)[:24]}"
        experiment = ExperimentRun(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            experiment_id=experiment_id,
            dataset_version_id=feature_version.dataset_version_id,
            mapping_set_id=feature_version.mapping_set_id,
            recipe_set_id=feature_version.recipe_set_id,
            feature_dataset_version_id=feature_version.feature_dataset_version_id,
            label_policy_id=feature_version.label_policy_id,
            status="queued",
            split_policy=request.split_policy,
            random_seed=request.random_seed,
            recall_target=request.recall_target,
            false_negative_cost=request.false_negative_cost,
            false_positive_cost=request.false_positive_cost,
            candidates=candidates,
            idempotency_key=request.idempotency_key,
        )
        stored = ExperimentRun.model_validate(
            self.repository.put(
                "experiment",
                experiment.model_dump(mode="json"),
                idempotency_key=request.idempotency_key,
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.experiment.queued",
            aggregate_type="ExperimentRun",
            aggregate_id=stored.experiment_id,
            payload={
                "feature_dataset_version_id": stored.feature_dataset_version_id,
                "algorithms": algorithms,
                "synchronous_training": False,
            },
        )
        return stored

    def experiment(
        self,
        experiment_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> ExperimentRun:
        return ExperimentRun.model_validate(
            self.repository.get(
                "experiment",
                experiment_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        )

    def list_experiments(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        limit: int = 100,
    ) -> list[ExperimentRun]:
        return [
            ExperimentRun.model_validate(item)
            for item in self.repository.list(
                "experiment",
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                limit=limit,
            )
        ]

    def retry_experiment(
        self,
        experiment_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ExperimentRetryRequest,
        actor_id: str,
    ) -> ExperimentRun:
        current = self.experiment(
            experiment_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(current.status) not in {"failed", "cancelled"}:
            raise ValueError("only failed or cancelled Experiment Runs can be retried")
        reset_candidates = [
            item.model_copy(
                update={
                    "status": "queued",
                    "validation_metrics": None,
                    "held_out_test_metrics": None,
                    "selected": False,
                    "selection_rationale": None,
                    "artifact": None,
                    "error_reason": None,
                }
            )
            for item in current.candidates
        ]
        updated = ExperimentRun.model_validate(
            self.repository.transition(
                "experiment",
                experiment_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                target_status="queued",
                expected_revision=request.expected_revision,
                transition_kind="run",
                updated_payload={
                    "progress": 0.0,
                    "candidates": [item.model_dump(mode="json") for item in reset_candidates],
                    "retry_count": current.retry_count + 1,
                    "selected_candidate_id": None,
                    "threshold_policy_id": None,
                    "artifact": None,
                },
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.experiment.retried",
            aggregate_type="ExperimentRun",
            aggregate_id=experiment_id,
            payload={"retry_count": updated.retry_count},
        )
        return updated

    def cancel_experiment(
        self,
        experiment_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ExperimentCancelRequest,
        actor_id: str,
    ) -> ExperimentRun:
        current = self.experiment(
            experiment_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(current.status) not in {"queued", "running"}:
            raise ValueError("only queued or running Experiment Runs can be cancelled")
        cancelled_candidates = [
            item.model_copy(
                update={
                    "status": "rejected"
                    if str(item.status) in {"queued", "running"}
                    else item.status,
                    "error_reason": item.error_reason
                    or f"Experiment cancelled: {request.reason}",
                }
            )
            for item in current.candidates
        ]
        cancelled = ExperimentRun.model_validate(
            self.repository.transition(
                "experiment",
                experiment_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                target_status="cancelled",
                expected_revision=request.expected_revision,
                transition_kind="run",
                updated_payload={
                    "candidates": [
                        item.model_dump(mode="json") for item in cancelled_candidates
                    ],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.experiment.cancelled",
            aggregate_type="ExperimentRun",
            aggregate_id=experiment_id,
            payload={"reason": request.reason, "previous_status": str(current.status)},
        )
        return cancelled

    def recover_stale_experiment(
        self,
        experiment_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ExperimentRecoverRequest,
        actor_id: str,
    ) -> ExperimentRun:
        current = self.experiment(
            experiment_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(current.status) != "running":
            raise ValueError("only running Experiment Runs can be recovered as stale")
        cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=request.stale_after_minutes
        )
        if current.updated_at > cutoff:
            raise ValueError("Experiment Run is not stale")
        failed = ExperimentRun.model_validate(
            self.repository.transition(
                "experiment",
                experiment_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                target_status="failed",
                expected_revision=request.expected_revision,
                transition_kind="run",
                updated_payload={
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "candidates": [
                        item.model_copy(
                            update={
                                "status": "failed"
                                if str(item.status) in {"queued", "running"}
                                else item.status,
                                "error_reason": item.error_reason
                                or "Worker heartbeat expired; run recovered as stale.",
                            }
                        ).model_dump(mode="json")
                        for item in current.candidates
                    ],
                },
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.experiment.stale_detected",
            aggregate_type="ExperimentRun",
            aggregate_id=experiment_id,
            payload={
                "stale_after_minutes": request.stale_after_minutes,
                "last_updated_at": current.updated_at.isoformat(),
            },
        )
        return self.retry_experiment(
            experiment_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            request=ExperimentRetryRequest(
                project_id=project_id,
                workspace_id=workspace_id,
                expected_revision=failed.revision,
            ),
            actor_id=actor_id,
        )

    def execute_experiment(
        self,
        experiment_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        worker_id: str,
    ) -> ExperimentRun:
        if self.artifact_store is None:
            raise RuntimeError(self.artifact_blocked_reason or "artifact store unavailable")
        current = self.experiment(
            experiment_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(current.status) != "queued":
            raise ValueError("worker can only execute queued Experiment Runs")
        running = ExperimentRun.model_validate(
            self.repository.transition(
                "experiment",
                experiment_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                target_status="running",
                expected_revision=current.revision,
                transition_kind="run",
                updated_payload={"progress": 0.01},
            )
        )
        feature_version = self.feature_dataset_version(
            running.feature_dataset_version_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        assert feature_version.artifact is not None
        feature_bytes = self.artifact_store.read_bytes(feature_version.artifact)
        feature_frame = pd.read_json(StringIO(feature_bytes.decode("utf-8")), lines=True)

        algorithms = [item.algorithm for item in running.candidates]

        def progress_callback(progress: float, candidates: list[CandidateResult]) -> None:
            latest = self.experiment(
                experiment_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
            if str(latest.status) == "cancelled":
                raise ExperimentCancelled("Experiment Run was cancelled")
            if str(latest.status) != "running":
                return
            self.repository.update(
                "experiment",
                experiment_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                expected_revision=latest.revision,
                updated_payload={
                    "progress": progress,
                    "candidates": [item.model_dump(mode="json") for item in candidates],
                },
            )

        try:
            completed, threshold_policy, _ = run_experiment(
                running,
                feature_frame=feature_frame,
                algorithms=algorithms,
                artifact_store=self.artifact_store,
                recall_target=running.recall_target,
                false_negative_cost=running.false_negative_cost,
                false_positive_cost=running.false_positive_cost,
                progress_callback=progress_callback,
            )
            latest = self.experiment(
                experiment_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
            stored = ExperimentRun.model_validate(
                self.repository.transition(
                    "experiment",
                    experiment_id,
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    target_status="succeeded",
                    expected_revision=latest.revision,
                    transition_kind="run",
                    updated_payload={
                        "progress": completed.progress,
                        "candidates": [item.model_dump(mode="json") for item in completed.candidates],
                        "selected_candidate_id": completed.selected_candidate_id,
                        "threshold_policy_id": threshold_policy.threshold_policy_id,
                        "artifact": completed.artifact.model_dump(mode="json")
                        if completed.artifact
                        else None,
                    },
                )
            )
            self.repository.record_audit(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                actor_id=worker_id,
                action="modeling.experiment.succeeded",
                aggregate_type="ExperimentRun",
                aggregate_id=experiment_id,
                payload={
                    "selected_candidate_id": stored.selected_candidate_id,
                    "threshold_policy_id": stored.threshold_policy_id,
                    "test_used_for_selection": False,
                },
            )
            return stored
        except Exception as exc:
            latest = self.experiment(
                experiment_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
            if isinstance(exc, ExperimentCancelled) and str(latest.status) == "cancelled":
                self.repository.record_audit(
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    actor_id=worker_id,
                    action="modeling.experiment.worker_cancelled",
                    aggregate_type="ExperimentRun",
                    aggregate_id=experiment_id,
                    payload={"progress": latest.progress},
                )
                return latest
            if str(latest.status) == "running":
                self.repository.transition(
                    "experiment",
                    experiment_id,
                    organization_id=organization_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    target_status="failed",
                    expected_revision=latest.revision,
                    transition_kind="run",
                    updated_payload={
                        "progress": latest.progress,
                        "candidates": [
                            item.model_copy(
                                update={
                                    "status": "failed" if item.status in {"queued", "running"} else item.status,
                                    "error_reason": item.error_reason or f"{type(exc).__name__}: {exc}",
                                }
                            ).model_dump(mode="json")
                            for item in latest.candidates
                        ],
                    },
                )
            self.repository.record_audit(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                actor_id=worker_id,
                action="modeling.experiment.failed",
                aggregate_type="ExperimentRun",
                aggregate_id=experiment_id,
                payload={"error_type": type(exc).__name__, "error": str(exc)},
            )
            raise

    def create_model_version(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ModelVersionCreateRequest,
        actor_id: str,
    ) -> ModelVersion:
        if self.artifact_store is None:
            raise RuntimeError(self.artifact_blocked_reason or "artifact store unavailable")
        experiment = self.experiment(
            request.experiment_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(experiment.status) != "succeeded" or not experiment.selected_candidate_id:
            raise ValueError("Model Version requires a succeeded Experiment Run")
        selected = next(
            (
                item
                for item in experiment.candidates
                if item.candidate_id == experiment.selected_candidate_id and item.selected
            ),
            None,
        )
        if selected is None or selected.artifact is None:
            raise ValueError("selected Experiment candidate has no verified artifact")
        if selected.algorithm == "dummy_prior":
            raise ValueError("baseline Dummy model cannot become a Model Version")
        # Verify before registry persistence.
        self.artifact_store.read_bytes(selected.artifact)
        if experiment.artifact is None:
            raise ValueError("Experiment report artifact is required")
        report = json.loads(self.artifact_store.read_bytes(experiment.artifact))
        threshold_policy = threshold_from_experiment_report(report)
        promotion_gate = self._validate_promotion_inputs(
            experiment=experiment,
            selected=selected,
            report=report,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        feature_version = self.feature_dataset_version(
            experiment.feature_dataset_version_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        input_features = [
            str(item["name"])
            for item in feature_version.schema_metadata.get("columns", [])
            if isinstance(item, dict) and str(item.get("name", "")).startswith("feature__")
        ]
        if not input_features:
            raise ValueError("Feature Dataset Version has no governed input feature schema")
        schema_checksum = input_schema_checksum(
            input_features=input_features,
            schema_metadata=feature_version.schema_metadata,
            recipe_set_id=experiment.recipe_set_id,
        )
        identity = canonical_checksum(
            {
                "experiment_id": experiment.experiment_id,
                "candidate_id": selected.candidate_id,
                "artifact_checksum": selected.artifact.checksum_sha256,
                "input_schema_checksum": schema_checksum,
                "threshold_policy_id": threshold_policy.threshold_policy_id,
            }
        )
        explanation_provider = (
            "linear_contribution" if selected.algorithm == "logistic_regression" else "feature_perturbation"
        )
        model = ModelVersion(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            model_version_id=f"model-{identity[:24]}",
            experiment_id=experiment.experiment_id,
            candidate_id=selected.candidate_id,
            algorithm=selected.algorithm,
            dataset_version_id=experiment.dataset_version_id,
            mapping_set_id=experiment.mapping_set_id,
            recipe_set_id=experiment.recipe_set_id,
            feature_dataset_version_id=experiment.feature_dataset_version_id,
            label_policy_id=experiment.label_policy_id,
            status="candidate",
            artifact=selected.artifact,
            input_features=input_features,
            input_schema_checksum_sha256=schema_checksum,
            runtime_versions=dict(report.get("runtime_versions", {})),
            calibration_method=None,
            calibration_artifact=None,
            confidence_status="unavailable_uncalibrated",
            threshold_policy=threshold_policy,
            explanation_provider=explanation_provider,
            explanation_provider_version="1",
            limitations=list(report.get("limitations", [])),
            promotion_gate=promotion_gate,
        )
        stored = ModelVersion.model_validate(
            self.repository.put(
                "model_version",
                model.model_dump(mode="json"),
                idempotency_key=request.idempotency_key,
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.model_version.created",
            aggregate_type="ModelVersion",
            aggregate_id=stored.model_version_id,
            payload={
                "experiment_id": stored.experiment_id,
                "algorithm": stored.algorithm,
                "artifact_checksum_sha256": stored.artifact.checksum_sha256,
                "input_schema_checksum_sha256": stored.input_schema_checksum_sha256,
            },
        )
        return stored

    def _validate_promotion_inputs(
        self,
        *,
        experiment: ExperimentRun,
        selected: CandidateResult,
        report: dict[str, Any],
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        if report.get("experiment_id") != experiment.experiment_id:
            raise ValueError("Experiment report identity does not match Experiment Run")
        if report.get("selected_candidate_id") != selected.candidate_id:
            raise ValueError("Experiment report selected candidate does not match registry state")
        report_candidates = report.get("candidate_results")
        expected_candidates = [
            item.model_dump(mode="json") for item in experiment.candidates
        ]
        if canonical_checksum(report_candidates) != canonical_checksum(expected_candidates):
            raise ValueError("Experiment candidate results do not match immutable report artifact")
        if selected.validation_metrics is None:
            raise ValueError("promotion gate requires validation metrics")
        if selected.held_out_test_metrics is None:
            raise ValueError("promotion gate requires held-out test metrics")
        if report.get("validation_used_for_selection") is not True:
            raise ValueError("promotion gate requires validation-only model selection")
        if report.get("test_used_for_selection") is not False:
            raise ValueError("held-out test must not be used for model selection")

        baseline = next(
            (
                item
                for item in experiment.candidates
                if item.algorithm == "dummy_prior"
                and item.status == "succeeded"
                and item.validation_metrics is not None
            ),
            None,
        )
        if baseline is None:
            raise ValueError("promotion gate requires a successful Dummy baseline")
        selected_ap = selected.validation_metrics.average_precision
        baseline_ap = baseline.validation_metrics.average_precision
        if selected_ap is None or baseline_ap is None or selected_ap <= baseline_ap:
            raise ValueError("selected candidate does not improve validation Average Precision over baseline")

        threshold_policy = threshold_from_experiment_report(report)
        threshold_row = next(
            (
                item
                for item in report.get("threshold_curve", [])
                if abs(
                    float(item.get("threshold", -1))
                    - threshold_policy.selected_operational_threshold
                )
                < 1e-9
            ),
            None,
        )
        if threshold_row is None:
            raise ValueError("selected operational threshold is missing from validation curve")
        selected_recall = float(threshold_row.get("recall", -1))
        if selected_recall < threshold_policy.recall_target:
            raise ValueError("selected operational threshold fails minimum recall policy")

        mapping = self.mapping_set(
            experiment.mapping_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(mapping.status) != "approved":
            raise ValueError("promotion gate requires an approved Mapping Set")
        recipe = self.feature_recipe_set(
            experiment.recipe_set_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(recipe.status) != "approved":
            raise ValueError("promotion gate requires an approved Feature Recipe Set")
        feature_version = self.feature_dataset_version(
            experiment.feature_dataset_version_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        expected_lineage = (
            experiment.dataset_version_id,
            experiment.mapping_set_id,
            experiment.recipe_set_id,
            experiment.label_policy_id,
        )
        actual_lineage = (
            feature_version.dataset_version_id,
            feature_version.mapping_set_id,
            feature_version.recipe_set_id,
            feature_version.label_policy_id,
        )
        if expected_lineage != actual_lineage:
            raise ValueError("Experiment and Feature Dataset lineage are incompatible")
        if mapping.dataset_version_id != experiment.dataset_version_id:
            raise ValueError("Mapping Set belongs to a different Dataset Version")
        if (
            recipe.dataset_version_id != experiment.dataset_version_id
            or recipe.mapping_set_id != experiment.mapping_set_id
        ):
            raise ValueError("Feature Recipe Set lineage is incompatible with Experiment")
        if str(feature_version.status) != "succeeded" or feature_version.artifact is None:
            raise ValueError("promotion gate requires a succeeded Feature Dataset artifact")
        assert self.artifact_store is not None
        self.artifact_store.read_bytes(feature_version.artifact)

        capabilities = dependency_capabilities()
        dependency = capabilities.get(selected.algorithm)
        if dependency is None or dependency.get("status") != "ready":
            raise ValueError(
                f"runtime capability is unavailable for selected algorithm: {selected.algorithm}"
            )
        forbidden = {"evaluation_truth", "hidden_truth"}
        feature_names = {
            str(item.get("name", "")).lower()
            for item in feature_version.schema_metadata.get("columns", [])
            if isinstance(item, dict)
        }
        leaked = sorted(feature_names & forbidden)
        if leaked:
            raise ValueError(
                "promotion gate rejects evaluator-only features: " + ", ".join(leaked)
            )
        blockers = recipe.validation_report.get("blockers", [])
        if blockers:
            raise ValueError("unresolved Feature Recipe governance blockers remain")
        return {
            "status": "passed",
            "validation_average_precision": selected_ap,
            "baseline_average_precision": baseline_ap,
            "baseline_improvement": selected_ap - baseline_ap,
            "selected_threshold_recall": selected_recall,
            "minimum_recall": threshold_policy.recall_target,
            "held_out_test_present": True,
            "lineage_compatible": True,
            "runtime_capability": dependency,
            "evaluator_truth_leakage": False,
        }

    def _revalidate_model_release_gate(self, model: ModelVersion) -> None:
        if self.artifact_store is None:
            raise RuntimeError(self.artifact_blocked_reason or "artifact store unavailable")
        self.artifact_store.read_bytes(model.artifact)
        if model.promotion_gate.get("status") != "passed":
            raise ValueError("Model Version has not passed the promotion gate")
        mapping = self.mapping_set(
            model.mapping_set_id,
            organization_id=model.organization_id,
            project_id=model.project_id,
            workspace_id=model.workspace_id,
        )
        recipe = self.feature_recipe_set(
            model.recipe_set_id,
            organization_id=model.organization_id,
            project_id=model.project_id,
            workspace_id=model.workspace_id,
        )
        feature_version = self.feature_dataset_version(
            model.feature_dataset_version_id,
            organization_id=model.organization_id,
            project_id=model.project_id,
            workspace_id=model.workspace_id,
        )
        if str(mapping.status) != "approved" or str(recipe.status) != "approved":
            raise ValueError("governed lineage was superseded or is no longer approved")
        if str(feature_version.status) != "succeeded" or feature_version.artifact is None:
            raise ValueError("Feature Dataset artifact is no longer available")
        self.artifact_store.read_bytes(feature_version.artifact)
        capability = dependency_capabilities().get(model.algorithm, {})
        if capability.get("status") != "ready":
            raise ValueError(f"runtime capability unavailable for {model.algorithm}")

    def model_version(
        self,
        model_version_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> ModelVersion:
        return ModelVersion.model_validate(
            self.repository.get(
                "model_version",
                model_version_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        )

    def list_model_versions(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        limit: int = 100,
    ) -> list[ModelVersion]:
        return [
            ModelVersion.model_validate(item)
            for item in self.repository.list(
                "model_version",
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                limit=limit,
            )
        ]

    def request_model_release(
        self,
        model_version_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ModelReleaseRequestCreate,
        actor_id: str,
    ) -> ModelReleaseRequestRecord:
        model = self.model_version(
            model_version_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(model.status) != "candidate":
            raise ValueError("only candidate Model Versions can request approval")
        self._revalidate_model_release_gate(model)
        release_id = f"model-release-{canonical_checksum({'model': model_version_id, 'requester': actor_id, 'rationale': request.rationale})[:24]}"
        record = ModelReleaseRequestRecord(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            release_request_id=release_id,
            model_version_id=model_version_id,
            requested_by=actor_id,
            request_rationale=request.rationale,
        )
        stored = ModelReleaseRequestRecord.model_validate(
            self.repository.put_release_request(record.model_dump(mode="json"))
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.model_release.requested",
            aggregate_type="ModelVersion",
            aggregate_id=model_version_id,
            payload={"release_request_id": stored.release_request_id},
        )
        return stored

    def list_model_release_requests(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        limit: int = 100,
    ) -> list[ModelReleaseRequestRecord]:
        return [
            ModelReleaseRequestRecord.model_validate(item)
            for item in self.repository.list_release_requests(
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                limit=limit,
            )
        ]

    def decide_model_release(
        self,
        release_request_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ModelReleaseDecisionRequest,
        actor_id: str,
    ) -> tuple[ModelReleaseRequestRecord, ModelVersion]:
        current = ModelReleaseRequestRecord.model_validate(
            self.repository.get_release_request(
                release_request_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        )
        status = "approved" if request.decision == "approve" else "rejected"
        decided = ModelReleaseRequestRecord.model_validate(
            self.repository.decide_release_request(
                release_request_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                expected_revision=request.expected_revision,
                status=status,
                decided_by=actor_id,
                decision_rationale=request.rationale,
            )
        )
        model = self.model_version(
            current.model_version_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        target = "approved" if status == "approved" else "rejected"
        updated_model = ModelVersion.model_validate(
            self.repository.transition(
                "model_version",
                model.model_version_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                target_status=target,
                expected_revision=model.revision,
                transition_kind="model",
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=f"modeling.model_release.{status}",
            aggregate_type="ModelVersion",
            aggregate_id=model.model_version_id,
            payload={
                "release_request_id": release_request_id,
                "rationale": request.rationale,
            },
        )
        return decided, updated_model

    def activate_model(
        self,
        model_version_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ModelActivateRequest,
        actor_id: str,
    ) -> ModelVersion:
        target = self.model_version(
            model_version_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(target.status) != "approved":
            raise ValueError("only an approved Model Version can be activated")
        if target.revision != request.expected_revision:
            raise ValueError("optimistic revision conflict")
        activated = ModelVersion.model_validate(
            self.repository.activate_model_version(
                model_version_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                expected_revision=request.expected_revision,
                allowed_current_statuses={"approved"},
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.model_version.activated",
            aggregate_type="ModelVersion",
            aggregate_id=model_version_id,
            payload={"prediction_task": activated.prediction_task},
        )
        return activated

    def rollback_model(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ModelRollbackRequest,
        actor_id: str,
    ) -> ModelVersion:
        target = self.model_version(
            request.target_model_version_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        if str(target.status) not in {"approved", "retired"}:
            raise ValueError("rollback target must be approved or retired")
        rolled_back = ModelVersion.model_validate(
            self.repository.activate_model_version(
                target.model_version_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
                expected_revision=target.revision,
                allowed_current_statuses={"approved", "retired"},
            )
        )
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.model_version.rollback_activated",
            aggregate_type="ModelVersion",
            aggregate_id=rolled_back.model_version_id,
            payload={"prediction_task": rolled_back.prediction_task},
        )
        return rolled_back

    def score_active_model(
        self,
        model_version_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        request: ModelScoreRequest,
        actor_id: str,
    ) -> tuple[ModelScoreResult, ExplanationArtifact]:
        if self.artifact_store is None:
            raise RuntimeError(self.artifact_blocked_reason or "artifact store unavailable")
        model = self.model_version(
            model_version_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
        )
        result, explanation = score_model(
            model=model,
            artifact_store=self.artifact_store,
            observation_id=request.observation_id,
            observed_at=request.observed_at,
            features=request.features,
            expected_input_schema_checksum_sha256=request.expected_input_schema_checksum_sha256,
        )
        stored_explanation = ExplanationArtifact.model_validate(
            self.repository.put(
                "explanation",
                explanation.model_dump(mode="json"),
                idempotency_key=explanation.explanation_id,
            )
        )
        prediction_boundary = self._prediction_result_boundary(
            model=model,
            result=result,
            explanation=stored_explanation,
        )
        if self.prediction_repository is not None:
            self.prediction_repository.save(prediction_boundary)
        self.repository.record_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            action="modeling.model_version.scored",
            aggregate_type="ModelVersion",
            aggregate_id=model_version_id,
            payload={
                "prediction_result_id": result.prediction_result_id,
                "observation_id": result.observation_id,
                "explanation_id": stored_explanation.explanation_id,
                "confidence_status": result.confidence_status,
                "prediction_result_contract_version": prediction_boundary.contract_version,
                "prediction_result_persisted": self.prediction_repository is not None,
            },
        )
        return result, stored_explanation

    def _prediction_result_boundary(
        self,
        *,
        model: ModelVersion,
        result: ModelScoreResult,
        explanation: ExplanationArtifact,
    ) -> PredictionResult:
        evidence = [
            PredictionEvidence(
                evidence_id=f"{explanation.explanation_id}:{factor.rank}",
                kind="feature",
                label=factor.feature,
                value=factor.observed_value,
                unit=factor.unit,
                contribution=factor.contribution,
                source=EvidenceSource(
                    system="adaptive-modeling-explanation",
                    reference=explanation.explanation_id,
                    checksum=explanation.checksum_sha256,
                ),
            )
            for factor in explanation.top_factors
        ]
        if not evidence:
            evidence = [
                PredictionEvidence(
                    evidence_id=f"{result.prediction_result_id}:model-artifact",
                    kind="artifact",
                    label="Verified active model artifact",
                    value={
                        "explanation_status": explanation.status,
                        "explanation_unavailable_reason": explanation.unavailable_reason,
                    },
                    source=EvidenceSource(
                        system="adaptive-modeling-registry",
                        reference=model.artifact.uri,
                        checksum=model.artifact.checksum_sha256,
                    ),
                )
            ]
        recommended_actions: list[RecommendedAction] = []
        if result.predicted_label == "failure_risk":
            recommended_actions.append(
                RecommendedAction(
                    action_type="review_equipment_risk",
                    label="Review equipment risk and inspection need",
                    reason=(
                        "Policy recommendation generated from the approved threshold; "
                        "this does not create or approve a Work Order."
                    ),
                    requires_approval=True,
                    parameters={
                        "decision_threshold": result.decision_threshold,
                        "failure_probability": result.failure_probability,
                        "work_order_created": False,
                    },
                )
            )
        return PredictionResult(
            prediction_id=result.prediction_result_id,
            organization_id=model.organization_id,
            project_id=model.project_id,
            workspace_id=model.workspace_id,
            source_run_id=model.experiment_id,
            subject=PredictionSubject(
                object_type="telemetry_observation",
                object_id=result.observation_id,
                observed_at=result.observed_at,
            ),
            prediction=PredictionValue(
                task="classification",
                status="warning" if result.predicted_label == "failure_risk" else "normal",
                label=result.predicted_label,
                score=result.failure_probability,
                confidence=result.confidence,
                horizon=model.label_policy_id,
            ),
            evidence=evidence,
            recommended_actions=recommended_actions,
            model=PredictionModel(
                provider="ontology_dashboard.modeling",
                model_name=model.algorithm,
                model_version=model.model_version_id,
                dataset_version=model.dataset_version_id,
                policy_version=model.threshold_policy.threshold_policy_id,
                code_version=model.explanation_provider_version,
            ),
        )

    def explanation(
        self,
        explanation_id: str,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
    ) -> ExplanationArtifact:
        return ExplanationArtifact.model_validate(
            self.repository.get(
                "explanation",
                explanation_id,
                organization_id=organization_id,
                project_id=project_id,
                workspace_id=workspace_id,
            )
        )

    def workbench_payload(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        selected_experiment_id: str | None = None,
    ) -> dict[str, Any]:
        profiles = self.repository.list(
            "intake_profile",
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=200,
        )
        manifests = self.repository.list(
            "manifest_draft",
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=200,
        )
        mappings = self.repository.list(
            "mapping_set",
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=200,
        )
        recipe_sets = self.repository.list(
            "recipe_set",
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=200,
        )
        feature_datasets = self.repository.list(
            "feature_dataset",
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=200,
        )
        experiments = self.list_experiments(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=200,
        )
        models = self.list_model_versions(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=200,
        )
        release_requests = self.list_model_release_requests(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=200,
        )
        selected = next(
            (item for item in experiments if item.experiment_id == selected_experiment_id),
            experiments[0] if experiments else None,
        )
        report: dict[str, Any] | None = None
        report_status = "not_selected"
        report_reason: str | None = None
        if selected is not None:
            if selected.artifact is None:
                report_status = "unavailable"
                report_reason = "Experiment Run has no report artifact."
            elif self.artifact_store is None:
                report_status = "blocked"
                report_reason = self.artifact_blocked_reason or "Artifact store unavailable."
            else:
                try:
                    report = json.loads(self.artifact_store.read_bytes(selected.artifact))
                    report_status = "available"
                except Exception as exc:
                    report_status = "unavailable"
                    report_reason = f"{type(exc).__name__}: {exc}"
        leaderboard = []
        if selected is not None:
            leaderboard = [
                {
                    "candidate_id": item.candidate_id,
                    "algorithm": item.algorithm,
                    "status": item.status,
                    "selected": item.selected,
                    "validation_metrics": item.validation_metrics.model_dump(mode="json")
                    if item.validation_metrics
                    else None,
                    "held_out_test_metrics": item.held_out_test_metrics.model_dump(mode="json")
                    if item.held_out_test_metrics
                    else None,
                    "dependency_version": item.dependency_version,
                    "error_reason": item.error_reason,
                }
                for item in selected.candidates
            ]
        active = [item for item in models if str(item.status) == "active"]
        selected_mapping = next(
            (
                item
                for item in mappings
                if selected is not None
                and item.get("mapping_set_id") == selected.mapping_set_id
            ),
            None,
        )
        selected_recipe = next(
            (
                item
                for item in recipe_sets
                if selected is not None
                and item.get("recipe_set_id") == selected.recipe_set_id
            ),
            None,
        )
        selected_feature = next(
            (
                item
                for item in feature_datasets
                if selected is not None
                and item.get("feature_dataset_version_id")
                == selected.feature_dataset_version_id
            ),
            None,
        )
        latest_profile = profiles[0] if profiles else None
        latest_manifest = manifests[0] if manifests else None
        latest_mapping = mappings[0] if mappings else None
        latest_recipe = recipe_sets[0] if recipe_sets else None
        latest_feature = feature_datasets[0] if feature_datasets else None
        readiness_steps = [
            {
                "step": "dataset_intake_profile",
                "status": latest_profile.get("status") if latest_profile else "missing",
                "identity": latest_profile.get("profile_id") if latest_profile else None,
            },
            {
                "step": "manifest_draft",
                "status": latest_manifest.get("status") if latest_manifest else "missing",
                "identity": latest_manifest.get("draft_id") if latest_manifest else None,
            },
            {
                "step": "mapping_set",
                "status": latest_mapping.get("status") if latest_mapping else "missing",
                "identity": latest_mapping.get("mapping_set_id") if latest_mapping else None,
            },
            {
                "step": "feature_recipe_set",
                "status": latest_recipe.get("status") if latest_recipe else "missing",
                "identity": latest_recipe.get("recipe_set_id") if latest_recipe else None,
            },
            {
                "step": "feature_dataset_version",
                "status": latest_feature.get("status") if latest_feature else "missing",
                "identity": latest_feature.get("feature_dataset_version_id")
                if latest_feature
                else None,
            },
        ]
        required_statuses = {
            "dataset_intake_profile": {"ready_for_review"},
            "manifest_draft": {"approved"},
            "mapping_set": {"approved"},
            "feature_recipe_set": {"approved"},
            "feature_dataset_version": {"succeeded"},
        }
        missing_prerequisites = [
            item["step"]
            for item in readiness_steps
            if item["status"] not in required_statuses[item["step"]]
        ]
        audit_events = self.repository.list_audit(
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            limit=300,
        )
        rollback_history = [
            item
            for item in audit_events
            if item["action"] == "modeling.model_version.rollback_activated"
        ]
        running = [item for item in experiments if str(item.status) == "running"]
        queued = [item for item in experiments if str(item.status) == "queued"]
        return {
            "schema_version": "ml-validator-workbench-v1",
            # Keep the canonical nested scope while also exposing the two
            # route identities at the response root.  The public OpenAPI
            # contract and older clients both require these fields.
            "project_id": project_id,
            "workspace_id": workspace_id,
            "scope": {
                "organization_id": organization_id,
                "project_id": project_id,
                "workspace_id": workspace_id,
            },
            "capabilities": {
                "artifact_store": self.artifact_capability(),
                "experiment_execution": "queued_worker_or_cli",
                "worker_health": {
                    "status": "unknown" if running or queued else "idle",
                    "reason": (
                        "No external worker heartbeat registry is configured; stale-run recovery uses Experiment updated_at."
                        if running or queued
                        else None
                    ),
                    "running_count": len(running),
                    "queued_count": len(queued),
                },
                "synchronous_training_endpoint": False,
            },
            "readiness": {
                "status": "ready" if not missing_prerequisites else "blocked",
                "steps": readiness_steps,
                "missing_prerequisites": missing_prerequisites,
            },
            "experiments": [item.model_dump(mode="json") for item in experiments],
            "selected_experiment_id": selected.experiment_id if selected else None,
            "leaderboard": leaderboard,
            "report": {
                "status": report_status,
                "reason": report_reason,
                "split": report.get("split") if report else None,
                "threshold_policy": report.get("threshold_policy") if report else None,
                "threshold_curve": report.get("threshold_curve", []) if report else [],
                "precision_recall_curve": report.get("precision_recall_curve", []) if report else [],
                "roc_curve": report.get("roc_curve", []) if report else [],
                "calibration": report.get("calibration", []) if report else [],
                "slice_metrics": report.get("slice_metrics", []) if report else [],
                "runtime_versions": report.get("runtime_versions") if report else None,
                "lineage": report.get("lineage") if report else None,
                "limitations": report.get("limitations", []) if report else [],
                "validation_used_for_selection": report.get("validation_used_for_selection")
                if report
                else None,
                "test_used_for_selection": report.get("test_used_for_selection") if report else None,
            },
            "models": [item.model_dump(mode="json") for item in models],
            "active_models": [item.model_dump(mode="json") for item in active],
            "release_requests": [item.model_dump(mode="json") for item in release_requests],
            "lineage_detail": {
                "mapping_set": selected_mapping,
                "feature_recipe_set": selected_recipe,
                "feature_dataset_version": selected_feature,
            },
            "global_feature_importance": {
                "status": "unavailable",
                "reason": "No governed global importance artifact was produced by this Experiment Run.",
                "items": [],
            },
            "operational_monitoring": {
                "status": "unavailable",
                "reason": "Operational drift/outcome artifacts are not connected; offline metrics are not used as a substitute.",
            },
            "audit_events": audit_events,
            "rollback_history": rollback_history,
            "empty": not experiments and not models,
        }

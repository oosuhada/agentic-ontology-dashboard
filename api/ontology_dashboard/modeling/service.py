from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import ArtifactStoreBlocked, LocalArtifactStore
from .intake import DatasetIntakeProfiler, IntakeLLMProvider, draft_from_profile
from .mapping import (
    MappingLLMProvider,
    evaluate_capabilities,
    generate_mapping_set,
    update_candidate,
    validate_mapping_set_for_approval,
)
from .models import (
    CapabilityEvaluation,
    DatasetIntakeProfile,
    ManifestDraft,
    ManifestDraftDecisionRequest,
    ManifestDraftUpdateRequest,
    MappingCandidateDecisionRequest,
    MappingSet,
    MappingSetDecisionRequest,
    ModelingContractSummary,
    canonical_checksum,
)
from .repository import ModelingRepository


class ModelingService:
    def __init__(
        self,
        repository: ModelingRepository,
        *,
        artifact_store: LocalArtifactStore | None = None,
        artifact_blocked_reason: str | None = None,
        intake_profiler: DatasetIntakeProfiler | None = None,
        mapping_provider: MappingLLMProvider | None = None,
    ) -> None:
        self.repository = repository
        self.artifact_store = artifact_store
        self.artifact_blocked_reason = artifact_blocked_reason
        self.intake_profiler = intake_profiler
        self.mapping_provider = mapping_provider

    @classmethod
    def configured(
        cls,
        database: str,
        artifact_root: str | None,
        *,
        intake_roots: list[str | Path] | None = None,
        intake_provider: IntakeLLMProvider | None = None,
        mapping_provider: MappingLLMProvider | None = None,
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
            )
        except ArtifactStoreBlocked as exc:
            return cls(
                ModelingRepository(database),
                artifact_store=None,
                artifact_blocked_reason=str(exc),
                intake_profiler=profiler,
                mapping_provider=mapping_provider,
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

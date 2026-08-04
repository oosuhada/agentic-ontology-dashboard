from __future__ import annotations

from typing import Any

from .artifacts import ArtifactStoreBlocked, LocalArtifactStore
from .models import ModelingContractSummary
from .repository import ModelingRepository


class ModelingService:
    def __init__(
        self,
        repository: ModelingRepository,
        *,
        artifact_store: LocalArtifactStore | None = None,
        artifact_blocked_reason: str | None = None,
    ) -> None:
        self.repository = repository
        self.artifact_store = artifact_store
        self.artifact_blocked_reason = artifact_blocked_reason

    @classmethod
    def configured(cls, database: str, artifact_root: str | None) -> "ModelingService":
        try:
            store = LocalArtifactStore(artifact_root)
            return cls(ModelingRepository(database), artifact_store=store)
        except ArtifactStoreBlocked as exc:
            return cls(
                ModelingRepository(database),
                artifact_store=None,
                artifact_blocked_reason=str(exc),
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

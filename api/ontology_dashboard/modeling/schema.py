from __future__ import annotations

from typing import TypeAlias

from pydantic import TypeAdapter

from .models import (
    DatasetIntakeProfile,
    ExperimentRun,
    ExplanationArtifact,
    FeatureDatasetVersion,
    FeatureRecipeSet,
    ManifestDraft,
    MappingSet,
    ModelVersion,
)


AdaptiveModelingContract: TypeAlias = (
    DatasetIntakeProfile
    | ManifestDraft
    | MappingSet
    | FeatureRecipeSet
    | FeatureDatasetVersion
    | ExperimentRun
    | ModelVersion
    | ExplanationArtifact
)


def adaptive_modeling_schema() -> dict:
    """Return the canonical Draft 2020-12 schema from the typed contracts."""

    schema = TypeAdapter(AdaptiveModelingContract).json_schema(
        mode="validation",
        ref_template="#/$defs/{model}",
    )
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = (
        "https://ontology-dashboard.local/schemas/adaptive-modeling.schema.json"
    )
    schema["title"] = "Adaptive Modeling Contracts"
    return schema


__all__ = ["AdaptiveModelingContract", "adaptive_modeling_schema"]

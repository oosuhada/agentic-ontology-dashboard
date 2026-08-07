"""Typed visualization registry, field profiling and deterministic recommendation."""

from .models import (
    FieldMapping,
    FieldProfile,
    VisualizationCandidate,
    VisualizationKind,
    VisualizationRecommendation,
)
from .profiler import profile_rows
from .recommender import VISUALIZATION_REGISTRY, recommend_visualization

__all__ = [
    "FieldMapping",
    "FieldProfile",
    "VISUALIZATION_REGISTRY",
    "VisualizationCandidate",
    "VisualizationKind",
    "VisualizationRecommendation",
    "profile_rows",
    "recommend_visualization",
]

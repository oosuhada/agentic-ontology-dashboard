"""Canonical ontology-aware planning package.

The legacy event-layout planner still imports ``ontology_dashboard.planner.LayoutPlanner``
through the historical namespace alias.  Keep that symbol available without eagerly
importing the dashboard planner service, which would create a service composition cycle.
"""

from __future__ import annotations

from typing import Any

from .layout import LayoutPlanner
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


def __getattr__(name: str) -> Any:
    if name == "OntologyDashboardPlannerService":
        from .service import OntologyDashboardPlannerService

        return OntologyDashboardPlannerService
    raise AttributeError(name)


__all__ = [
    "BoardRecommendationItem",
    "BoardRecommendationRequest",
    "BoardRecommendationResponse",
    "DashboardDraftRequest",
    "DashboardDraftResponse",
    "GroundedNarrativeClaim",
    "GroundedNarrativeRequest",
    "GroundedNarrativeResponse",
    "LayoutPlanner",
    "NaturalLanguageObjectQueryRequest",
    "ObjectQueryFilter",
    "ObjectQueryIntent",
    "ObjectQueryPlanResponse",
    "VisualizationPlannerResponse",
    "VisualizationRecommendationRequest",
    "OntologyDashboardPlannerService",
]

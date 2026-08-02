"""Compatibility re-export for the canonical planner service.

New code must import from :mod:`ontology_dashboard.planner`.
"""

from ontology_dashboard.planner.service import OntologyDashboardPlannerService

__all__ = ["OntologyDashboardPlannerService"]

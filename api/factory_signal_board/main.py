"""Deprecated compatibility entrypoint.

The executable composition root lives in :mod:`ontology_dashboard.main`.
Remove this module when the remaining physical legacy package relocation is
complete.
"""

from ontology_dashboard.main import (
    app,
    get_identity_service,
    get_ontology_planner_service,
    get_rate_limiter,
    get_service,
)

__all__ = [
    "app",
    "get_identity_service",
    "get_ontology_planner_service",
    "get_rate_limiter",
    "get_service",
]

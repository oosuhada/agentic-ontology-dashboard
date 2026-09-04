"""Canonical Ontology domain package."""

from .ontology_domain import (
    ACTION_TYPES,
    LINK_TYPES,
    OBJECT_TYPES,
    ActionInvocation,
    LinkRecord,
    ObjectRecord,
    registry_payload,
)
from .ontology_service import OntologyService
from .projection import OntologyProjectionInput

__all__ = [
    "ACTION_TYPES",
    "LINK_TYPES",
    "OBJECT_TYPES",
    "ActionInvocation",
    "LinkRecord",
    "ObjectRecord",
    "OntologyProjectionInput",
    "OntologyService",
    "registry_payload",
]

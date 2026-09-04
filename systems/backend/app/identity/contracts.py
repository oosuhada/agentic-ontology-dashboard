"""Stable Identity contracts for cross-context consumers."""

from .identity_exception import AuthError
from .identity_schema import Principal, ROLE_DEFINITIONS
from .ports import IdentityAccessPort, PrincipalContext, WorkspaceScope

__all__ = [
    "AuthError",
    "IdentityAccessPort",
    "Principal",
    "PrincipalContext",
    "ROLE_DEFINITIONS",
    "WorkspaceScope",
]

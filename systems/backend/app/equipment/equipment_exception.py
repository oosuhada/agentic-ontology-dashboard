"""Domain exceptions owned by the Equipment bounded context."""

from __future__ import annotations


class EquipmentError(Exception):
    """Base class for Equipment domain/application failures."""


class EquipmentNotFoundError(EquipmentError):
    """Raised when an Equipment master does not exist in the requested scope."""


class EquipmentStateVersionConflictError(EquipmentError):
    """Raised when optimistic Equipment state concurrency validation fails."""

    def __init__(self, *, expected: int | None, actual: int | None) -> None:
        super().__init__(
            f"equipment state_version conflict: expected={expected!r}, actual={actual!r}"
        )
        self.expected = expected
        self.actual = actual


class InvalidEquipmentStatePatchError(EquipmentError):
    """Raised when a state patch violates Equipment-owned mutation rules."""

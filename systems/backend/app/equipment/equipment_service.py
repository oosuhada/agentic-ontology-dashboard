"""Application service for Equipment master and current-state use cases."""

from __future__ import annotations

from typing import Any, Mapping

from .equipment_domain import apply_state_patch
from .equipment_exception import (
    EquipmentNotFoundError,
    EquipmentStateVersionConflictError,
)
from .equipment_repository import EquipmentRepository


DEFAULT_PROJECT_ID = "manufacturing-demo-project"


class EquipmentService:
    """Own Equipment identity, current-state reads, and state mutation semantics."""

    def __init__(self, repository: EquipmentRepository) -> None:
        self.repository = repository

    def list_equipment(self, project_id: str = DEFAULT_PROJECT_ID) -> list[dict[str, Any]]:
        return [master.as_dict() for master in self.repository.list_masters(project_id=project_id)]

    def equipment(
        self, equipment_id: str, project_id: str = DEFAULT_PROJECT_ID
    ) -> dict[str, Any]:
        master = self.repository.get_master(project_id=project_id, equipment_id=equipment_id)
        if master is None:
            raise EquipmentNotFoundError(equipment_id)
        return master.as_dict()

    def equipment_current_state(
        self, equipment_id: str, project_id: str = DEFAULT_PROJECT_ID
    ) -> dict[str, Any] | None:
        self._require_master(project_id=project_id, equipment_id=equipment_id)
        snapshot = self.repository.get_current_state(
            project_id=project_id,
            equipment_id=equipment_id,
        )
        return None if snapshot is None else snapshot.as_dict()

    def patch_equipment_state(
        self,
        equipment_id: str,
        *,
        expected_state_version: int | None,
        state_patch: Mapping[str, Any],
        project_id: str = DEFAULT_PROJECT_ID,
    ) -> dict[str, Any]:
        self._require_master(project_id=project_id, equipment_id=equipment_id)
        current = self.repository.get_current_state(
            project_id=project_id,
            equipment_id=equipment_id,
        )
        actual_version = None if current is None else current.state_version
        if actual_version != expected_state_version:
            raise EquipmentStateVersionConflictError(
                expected=expected_state_version,
                actual=actual_version,
            )
        current_state = {} if current is None else current.state
        updated_state = apply_state_patch(current_state, state_patch)
        snapshot = self.repository.compare_and_set_state(
            project_id=project_id,
            equipment_id=equipment_id,
            expected_state_version=expected_state_version,
            state=updated_state,
        )
        return snapshot.as_dict()

    def _require_master(self, *, project_id: str, equipment_id: str) -> None:
        if self.repository.get_master(project_id=project_id, equipment_id=equipment_id) is None:
            raise EquipmentNotFoundError(equipment_id)

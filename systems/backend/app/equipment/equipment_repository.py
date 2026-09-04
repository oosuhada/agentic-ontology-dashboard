"""Repository port for the Equipment bounded context."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from .equipment_domain import EquipmentCurrentState, EquipmentMaster


class EquipmentRepository(Protocol):
    """Persistence-neutral contract consumed by :class:`EquipmentService`."""

    def list_masters(self, *, project_id: str) -> list[EquipmentMaster]: ...

    def get_master(self, *, project_id: str, equipment_id: str) -> EquipmentMaster | None: ...

    def get_current_state(
        self, *, project_id: str, equipment_id: str
    ) -> EquipmentCurrentState | None: ...

    def compare_and_set_state(
        self,
        *,
        project_id: str,
        equipment_id: str,
        expected_state_version: int | None,
        state: Mapping[str, Any],
    ) -> EquipmentCurrentState: ...

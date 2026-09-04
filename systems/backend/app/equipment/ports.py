"""Public application ports owned by the Equipment context."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class EquipmentApplicationPort(Protocol):
    def list_equipment(self, project_id: str = "manufacturing-demo-project") -> list[dict[str, Any]]: ...

    def equipment(
        self, equipment_id: str, project_id: str = "manufacturing-demo-project"
    ) -> dict[str, Any]: ...

    def equipment_current_state(
        self, equipment_id: str, project_id: str = "manufacturing-demo-project"
    ) -> dict[str, Any] | None: ...

    def patch_equipment_state(
        self,
        equipment_id: str,
        *,
        expected_state_version: int | None,
        state_patch: Mapping[str, Any],
        project_id: str = "manufacturing-demo-project",
    ) -> dict[str, Any]: ...


__all__ = ["EquipmentApplicationPort"]

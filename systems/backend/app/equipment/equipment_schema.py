"""Transport-neutral public schema types for Equipment consumers."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, TypedDict


class EquipmentMasterPayload(TypedDict):
    equipment_id: str


class EquipmentCurrentStatePayload(TypedDict):
    equipment_id: str
    state_version: int
    state: dict[str, Any]


class EquipmentStatePatchCommand(TypedDict):
    """Public input contract for an optimistic Equipment state mutation."""

    expected_state_version: int | None
    state_patch: Mapping[str, Any]


class EquipmentCurrentStateQuery(Protocol):
    """Public query port consumed by downstream domains without implementation imports."""

    def equipment_current_state(
        self,
        equipment_id: str,
        project_id: str = "manufacturing-demo-project",
    ) -> EquipmentCurrentStatePayload | None: ...


class EquipmentStatePatchPort(Protocol):
    """Public optimistic mutation port used by an authorized coordinating domain."""

    def patch_equipment_state(
        self,
        equipment_id: str,
        *,
        expected_state_version: int | None,
        state_patch: Mapping[str, Any],
        project_id: str = "manufacturing-demo-project",
    ) -> EquipmentCurrentStatePayload: ...

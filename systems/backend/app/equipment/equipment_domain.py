"""Transport- and persistence-neutral Equipment domain invariants."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .equipment_exception import InvalidEquipmentStatePatchError


@dataclass(frozen=True, slots=True)
class EquipmentMaster:
    """Stable Equipment identity plus master attributes owned by Equipment."""

    equipment_id: str
    attributes: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "EquipmentMaster":
        equipment_id = str(payload.get("equipment_id") or "").strip()
        if not equipment_id:
            raise ValueError("equipment_id must be a non-empty string")
        attributes = {
            key: deepcopy(value)
            for key, value in payload.items()
            if key != "equipment_id"
        }
        return cls(equipment_id=equipment_id, attributes=attributes)

    def as_dict(self) -> dict[str, Any]:
        return {"equipment_id": self.equipment_id, **deepcopy(dict(self.attributes))}


@dataclass(frozen=True, slots=True)
class EquipmentCurrentState:
    """Versioned current-state snapshot for one Equipment aggregate."""

    equipment_id: str
    state_version: int
    state: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "equipment_id": self.equipment_id,
            "state_version": self.state_version,
            "state": deepcopy(dict(self.state)),
        }


def next_state_version(expected_version: int | None) -> int:
    """Return the only valid successor for an Equipment state version."""

    if expected_version is None:
        return 1
    if expected_version < 1:
        raise ValueError("equipment state_version must be positive once initialized")
    return expected_version + 1


def apply_state_patch(
    current_state: Mapping[str, Any],
    state_patch: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply an approved Equipment state command without storing command syntax."""

    if set(state_patch) != {"tool_wear_min"}:
        raise InvalidEquipmentStatePatchError("unsupported equipment state patch")
    tool_wear = state_patch.get("tool_wear_min")
    if not isinstance(tool_wear, Mapping):
        raise InvalidEquipmentStatePatchError("tool_wear_min patch must be an object")
    if (
        tool_wear.get("operation") != "reset"
        or tool_wear.get("value") != 0
        or tool_wear.get("unit") != "min"
    ):
        raise InvalidEquipmentStatePatchError(
            "tool_wear_min reset requires operation=reset, value=0, unit=min"
        )

    updated = deepcopy(dict(current_state))
    updated["tool_wear_min"] = {"value": 0, "unit": "min"}
    return updated

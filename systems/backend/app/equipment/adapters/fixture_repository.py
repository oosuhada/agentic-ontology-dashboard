"""Fixture-backed Equipment repository adapter for the showcase runtime."""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any, Iterable, Mapping, cast

from ..equipment_domain import EquipmentCurrentState, EquipmentMaster, next_state_version
from ..equipment_exception import EquipmentStateVersionConflictError


class FixtureEquipmentRepository:
    """Process-local fixture adapter implementing the Equipment repository port."""

    def __init__(self, masters: Iterable[tuple[str, Mapping[str, Any]]]) -> None:
        self._masters: dict[tuple[str, str], EquipmentMaster] = {}
        for project_id, payload in masters:
            master = EquipmentMaster.from_mapping(payload)
            self._masters[(project_id, master.equipment_id)] = master
        self._states: dict[tuple[str, str], EquipmentCurrentState] = {}
        self._state_lock = RLock()

    def list_masters(self, *, project_id: str) -> list[EquipmentMaster]:
        return sorted(
            (
                master
                for (candidate_project_id, _), master in self._masters.items()
                if candidate_project_id == project_id
            ),
            key=lambda master: master.equipment_id,
        )

    def get_master(self, *, project_id: str, equipment_id: str) -> EquipmentMaster | None:
        return self._masters.get((project_id, equipment_id))

    def get_current_state(
        self, *, project_id: str, equipment_id: str
    ) -> EquipmentCurrentState | None:
        with self._state_lock:
            snapshot = self._states.get((project_id, equipment_id))
            if snapshot is None:
                return None
            return EquipmentCurrentState(
                equipment_id=snapshot.equipment_id,
                state_version=snapshot.state_version,
                state=deepcopy(dict(snapshot.state)),
            )

    def compare_and_set_state(
        self,
        *,
        project_id: str,
        equipment_id: str,
        expected_state_version: int | None,
        state: Mapping[str, Any],
    ) -> EquipmentCurrentState:
        key = (project_id, equipment_id)
        with self._state_lock:
            current = self._states.get(key)
            actual_version = None if current is None else current.state_version
            if actual_version != expected_state_version:
                raise EquipmentStateVersionConflictError(
                    expected=expected_state_version,
                    actual=actual_version,
                )
            self._states[key] = EquipmentCurrentState(
                equipment_id=equipment_id,
                state_version=next_state_version(actual_version),
                state=deepcopy(dict(state)),
            )
            return cast(
                EquipmentCurrentState,
                self.get_current_state(project_id=project_id, equipment_id=equipment_id),
            )

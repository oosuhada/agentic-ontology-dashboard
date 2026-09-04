from __future__ import annotations

import ast
from pathlib import Path

from app.maintenance import MaintenanceEvent, WorkOrder
from app.maintenance.ports import DiagnosisResultQueryPort, EquipmentStatePatchPort
from app.infra.db.maintenance_repository import MaintenanceRepository


ROOT = Path(__file__).resolve().parents[1]
MAINTENANCE = ROOT / "systems" / "backend" / "app" / "maintenance"
LEGACY = ROOT / "systems" / "backend" / "ontology_dashboard" / "closed_loop"


def test_closed_loop_package_is_physically_migrated() -> None:
    assert not list(LEGACY.glob("*.py"))
    for relative in (
        "__init__.py",
        "maintenance_domain.py",
        "maintenance_schema.py",
        "integration.py",
        "ports.py",
    ):
        assert (MAINTENANCE / relative).is_file(), relative
    assert (
        ROOT / "systems" / "backend" / "app" / "infra" / "db" / "maintenance_repository.py"
    ).is_file()


def test_maintenance_domain_does_not_import_legacy_or_infra_implementations() -> None:
    violations: list[str] = []
    for path in MAINTENANCE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            for name in names:
                if name == "ontology_dashboard" or name.startswith("app.runtime."):
                    violations.append(f"{path.name}: {name}")
                if name.startswith("app.infra"):
                    violations.append(f"{path.name}: {name}")
    assert violations == []


def test_maintenance_public_contracts_are_importable() -> None:
    assert WorkOrder.model_fields["work_order_id"]
    assert MaintenanceEvent.model_fields["maintenance_event_id"]
    assert MaintenanceRepository
    assert DiagnosisResultQueryPort
    assert EquipmentStatePatchPort

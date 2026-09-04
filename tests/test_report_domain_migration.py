from __future__ import annotations

import ast
from pathlib import Path

from app.report import (
    ReportAgent,
    ReportService,
    build_report_router,
    render_report,
)
from app.report.ports import (
    DiagnosisEvidencePort,
    MaintenanceHistoryPort,
    ReportGenerationProviderPort,
)
from app.infra.db.report_repository import ReportRepository


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "systems" / "backend" / "app" / "report"
LEGACY = ROOT / "systems" / "backend" / "ontology_dashboard"


def test_report_sources_are_physically_canonical() -> None:
    for relative in (
        "reports.py",
        "llm.py",
        "export_models.py",
        "export_repository.py",
        "export_service.py",
        "routers/exports.py",
    ):
        assert not (LEGACY / relative).exists(), relative

    for relative in (
        "report_schema.py",
        "report_service.py",
        "report_router.py",
        "generation.py",
        "generation_provider.py",
        "ports.py",
    ):
        assert (REPORT / relative).is_file(), relative
    assert (ROOT / "systems/backend/app/infra/db/report_repository.py").is_file()


def test_report_domain_has_no_legacy_or_infra_implementation_imports() -> None:
    violations: list[str] = []
    for path in REPORT.rglob("*.py"):
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


def test_report_public_generation_and_consumer_ports_are_explicit() -> None:
    assert ReportService
    assert ReportRepository
    assert ReportAgent
    assert render_report
    assert build_report_router
    assert ReportGenerationProviderPort
    assert DiagnosisEvidencePort
    assert MaintenanceHistoryPort

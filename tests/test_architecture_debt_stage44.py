from __future__ import annotations

import importlib
import ontology_dashboard
from pathlib import Path

from scripts.check_architecture_debt import assert_no_regressions, collect_architecture_debt

ROOT = Path(__file__).resolve().parents[1]


def test_stage44_architecture_inventory_has_no_regression() -> None:
    items = collect_architecture_debt(ROOT)
    assert_no_regressions(items)
    by_id = {item.id: item for item in items}
    assert by_id["roadmap_override_registered"].state == "resolved"
    assert by_id["soon_navigation_feature_flags"].state == "resolved"
    assert by_id["planner_legacy_router_imports"].state == "resolved"
    assert by_id["validated_project3_query_boundary"].state == "resolved"
    assert by_id["foundation_identity_physical_relocation"].state == "resolved"
    assert by_id["dashboard_physical_relocation"].state == "resolved"
    assert by_id["analysis_physical_relocation"].state == "resolved"
    assert by_id["export_workflow_physical_relocation"].state == "resolved"
    assert by_id["ontology_compatibility_physical_relocation"].state == "resolved"
    assert by_id["legacy_namespace_path_extension"].state == "resolved"
    assert by_id["legacy_package_removed"].state == "resolved"


def test_stage55_legacy_package_debt_is_fully_resolved() -> None:
    items = collect_architecture_debt(ROOT)
    assert not [item for item in items if item.state == "accepted"]
    assert next(item for item in items if item.id == "legacy_composition_root").state == "resolved"
    assert not tuple((ROOT / "api" / "factory_signal_board").glob("*.py"))
    assert [Path(path).resolve() for path in ontology_dashboard.__path__] == [
        (ROOT / "api" / "ontology_dashboard").resolve()
    ]


def test_foundation_identity_modules_load_from_canonical_directory() -> None:
    module_names = (
        "context",
        "contracts",
        "security",
        "identity_models",
        "identity_repository",
        "identity",
        "repository",
        "service",
    )
    canonical_root = ROOT / "api" / "ontology_dashboard"
    for name in module_names:
        module = importlib.import_module(f"ontology_dashboard.{name}")
        assert Path(module.__file__).resolve().parent == canonical_root.resolve()

    identity = importlib.import_module("ontology_dashboard.identity")
    identity_repository = importlib.import_module("ontology_dashboard.identity_repository")
    assert identity.IdentityRepository is identity_repository.IdentityRepository


def test_dashboard_modules_load_from_canonical_directory() -> None:
    module_names = (
        "dashboard_models",
        "dashboard_catalog",
        "dashboard_repository",
        "dashboard_service",
    )
    canonical_root = ROOT / "api" / "ontology_dashboard"
    for name in module_names:
        module = importlib.import_module(f"ontology_dashboard.{name}")
        assert Path(module.__file__).resolve().parent == canonical_root.resolve()

    dashboard_repository = importlib.import_module("ontology_dashboard.dashboard_repository")
    dashboard_service = importlib.import_module("ontology_dashboard.dashboard_service")
    postgresql_repositories = importlib.import_module("ontology_dashboard.postgresql_repositories")
    assert dashboard_service.DashboardRepository is dashboard_repository.DashboardRepository
    assert issubclass(
        postgresql_repositories.PostgreSQLDashboardRepository,
        dashboard_repository.DashboardRepository,
    )


def test_analysis_modules_load_from_canonical_directory() -> None:
    module_names = (
        "analysis_models",
        "analysis_repository",
        "analysis_service",
    )
    canonical_root = ROOT / "api" / "ontology_dashboard"
    for name in module_names:
        module = importlib.import_module(f"ontology_dashboard.{name}")
        assert Path(module.__file__).resolve().parent == canonical_root.resolve()

    analysis_repository = importlib.import_module("ontology_dashboard.analysis_repository")
    analysis_service = importlib.import_module("ontology_dashboard.analysis_service")
    assert analysis_service.AnalysisRepository is analysis_repository.AnalysisRepository


def test_export_workflow_modules_load_from_canonical_directory() -> None:
    module_names = (
        "export_models",
        "export_repository",
        "export_service",
        "role_workflow_models",
        "role_workflow_repository",
        "role_workflow_service",
    )
    canonical_root = ROOT / "api" / "ontology_dashboard"
    for name in module_names:
        module = importlib.import_module(f"ontology_dashboard.{name}")
        assert Path(module.__file__).resolve().parent == canonical_root.resolve()

    export_repository = importlib.import_module("ontology_dashboard.export_repository")
    export_service = importlib.import_module("ontology_dashboard.export_service")
    workflow_repository = importlib.import_module("ontology_dashboard.role_workflow_repository")
    workflow_service = importlib.import_module("ontology_dashboard.role_workflow_service")
    postgresql_repositories = importlib.import_module("ontology_dashboard.postgresql_repositories")
    assert export_service.ExportRepository is export_repository.ExportRepository
    assert workflow_service.RoleWorkflowRepository is workflow_repository.RoleWorkflowRepository
    assert issubclass(
        postgresql_repositories.PostgreSQLExportRepository,
        export_repository.ExportRepository,
    )
    assert issubclass(
        postgresql_repositories.PostgreSQLRoleWorkflowRepository,
        workflow_repository.RoleWorkflowRepository,
    )


def test_ontology_compatibility_modules_load_from_canonical_directory() -> None:
    module_names = (
        "conversation",
        "llm",
        "reports",
        "ontology",
        "ontology_adapter",
        "ontology_repository",
        "ontology_service",
        "ontology_planner_models",
        "ontology_planner_service",
    )
    canonical_root = ROOT / "api" / "ontology_dashboard"
    for name in module_names:
        module = importlib.import_module(f"ontology_dashboard.{name}")
        assert Path(module.__file__).resolve().parent == canonical_root.resolve()

    ontology = importlib.import_module("ontology_dashboard.ontology")
    ontology_adapter = importlib.import_module("ontology_dashboard.ontology_adapter")
    ontology_repository = importlib.import_module("ontology_dashboard.ontology_repository")
    ontology_service = importlib.import_module("ontology_dashboard.ontology_service")
    postgresql_repositories = importlib.import_module("ontology_dashboard.postgresql_repositories")
    assert ontology_adapter.ObjectRecord is ontology.ObjectRecord
    assert ontology_service.OntologyActionRepository is ontology_repository.OntologyActionRepository
    assert issubclass(
        postgresql_repositories.PostgreSQLOntologyActionRepository,
        ontology_repository.OntologyActionRepository,
    )

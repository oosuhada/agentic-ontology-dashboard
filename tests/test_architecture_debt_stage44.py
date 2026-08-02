from __future__ import annotations

import importlib
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


def test_remaining_legacy_debt_is_explicitly_owned_by_stage55() -> None:
    items = collect_architecture_debt(ROOT)
    accepted = {item.id: item.stage for item in items if item.state == "accepted"}
    assert accepted.get("legacy_namespace_path_extension") == 55
    assert "legacy_composition_root" not in accepted
    assert next(item for item in items if item.id == "legacy_composition_root").state == "resolved"


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

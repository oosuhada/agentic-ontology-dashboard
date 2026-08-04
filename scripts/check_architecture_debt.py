#!/usr/bin/env python3
"""Executable architecture-debt inventory for the convergence roadmap.

The inventory distinguishes accepted migration debt from regressions that must fail CI.
It intentionally uses only the standard library so it can run before dependencies install.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

DebtState = Literal["resolved", "accepted", "regression"]


@dataclass(frozen=True)
class DebtItem:
    id: str
    state: DebtState
    stage: int
    evidence: str
    action: str


def _contains(path: Path, text: str) -> bool:
    return path.exists() and text in path.read_text(encoding="utf-8")


def _is_thin_reexport(path: Path, canonical_module: str) -> bool:
    if not path.exists():
        return False
    executable_lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith('"""')
    ]
    return executable_lines == [f"from {canonical_module} import *  # noqa: F403"]


def _canonical_with_optional_legacy_shim(
    root: Path,
    module: str,
    canonical_module: str | None = None,
) -> bool:
    canonical_path = root / "api" / "ontology_dashboard" / f"{module}.py"
    legacy_root = root / "api" / "factory_signal_board"
    if not canonical_path.exists():
        return False
    if not any(legacy_root.glob("*.py")):
        return True
    return _is_thin_reexport(
        legacy_root / f"{module}.py",
        canonical_module or f"ontology_dashboard.{module}",
    )


def collect_architecture_debt(root: Path) -> list[DebtItem]:
    canonical_init = root / "api" / "ontology_dashboard" / "__init__.py"
    canonical_composition_root = root / "api" / "ontology_dashboard" / "main.py"
    legacy_package = root / "api" / "factory_signal_board"
    legacy_composition_shim = root / "api" / "factory_signal_board" / "main.py"
    planner_router = root / "api" / "ontology_dashboard" / "routers" / "planner.py"
    dependencies = root / "api" / "ontology_dashboard" / "dependencies.py"
    feature_flags = root / "web" / "src" / "featureFlags.ts"
    dashboard_shell = root / "web" / "src" / "features" / "dashboard" / "DashboardShell.tsx"
    roadmap = root / "docs" / "30-implementation" / "product-convergence-roadmap.md"
    master_prompt = root / "docs" / "60-development-prompts" / "next-session-master-prompt.md"
    project3_client = root / "api" / "ontology_dashboard" / "integrations" / "project3" / "client.py"
    pyproject = root / "api" / "pyproject.toml"
    foundation_modules = (
        "context",
        "contracts",
        "security",
        "identity_models",
        "identity_repository",
        "identity",
        "repository",
        "service",
    )
    dashboard_modules = (
        "dashboard_models",
        "dashboard_catalog",
        "dashboard_repository",
        "dashboard_service",
    )
    analysis_modules = (
        "analysis_models",
        "analysis_repository",
        "analysis_service",
    )
    export_workflow_modules = (
        "export_models",
        "export_repository",
        "export_service",
        "role_workflow_models",
        "role_workflow_repository",
        "role_workflow_service",
    )
    ontology_compatibility_modules = (
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

    legacy_path_extension = _contains(canonical_init, "__path__.append")
    legacy_python_sources = tuple(legacy_package.glob("*.py"))
    legacy_package_discovered = _contains(pyproject, "factory_signal_board")
    canonical_root_present = canonical_composition_root.exists() and _contains(canonical_composition_root, "app = create_app()")
    legacy_root_executable = any(
        _contains(legacy_composition_shim, token)
        for token in ("app = create_app()", "app.include_router", "@app.exception_handler")
    )
    forbidden_planner_import = any(
        _contains(path, token)
        for path in (planner_router, dependencies)
        for token in (
            "from ..ontology_planner_",
            "from .ontology_planner_",
            "import ontology_planner_models",
            "import ontology_planner_service",
        )
    )
    flags_explicit = all(
        _contains(feature_flags, token)
        for token in (
            "VITE_FEATURE_ONTOLOGY_WORKBENCH",
            "VITE_FEATURE_DATASET_CATALOG",
            "VITE_FEATURE_GOVERNANCE_WORKBENCH",
        )
    )
    nav_uses_flags = _contains(dashboard_shell, "featureFlags.ontologyWorkbench")
    roadmap_is_override = _contains(
        master_prompt,
        "docs/30-implementation/product-convergence-roadmap.md",
    )
    polyglot_target = all(
        _contains(roadmap, token)
        for token in ("PostgreSQL", "pgvector", "Neo4j", "LangGraph")
    )
    raw_cypher_method = any(
        _contains(project3_client, token)
        for token in ("def execute_cypher", "def cypher(", "raw_cypher")
    )
    foundation_identity_relocated = all(
        _canonical_with_optional_legacy_shim(root, module)
        for module in foundation_modules
    )
    dashboard_relocated = all(
        _canonical_with_optional_legacy_shim(root, module)
        for module in dashboard_modules
    )
    analysis_relocated = all(
        _canonical_with_optional_legacy_shim(root, module)
        for module in analysis_modules
    )
    export_workflow_relocated = all(
        _canonical_with_optional_legacy_shim(root, module)
        for module in export_workflow_modules
    )
    ontology_compatibility_relocated = all(
        _canonical_with_optional_legacy_shim(root, module)
        for module in ontology_compatibility_modules
    )

    return [
        DebtItem(
            id="roadmap_override_registered",
            state="resolved" if roadmap_is_override and polyglot_target else "regression",
            stage=44,
            evidence="next-session master prompt and convergence roadmap",
            action="Keep the convergence roadmap authoritative over the historical Project Layer sequence.",
        ),
        DebtItem(
            id="soon_navigation_feature_flags",
            state="resolved" if flags_explicit and nav_uses_flags else "regression",
            stage=44,
            evidence="web/src/featureFlags.ts and DashboardShell.tsx",
            action="Every unfinished workbench must remain behind an explicit build-time feature flag.",
        ),
        DebtItem(
            id="planner_legacy_router_imports",
            state="regression" if forbidden_planner_import else "resolved",
            stage=45,
            evidence="planner router and dependency composition",
            action="Import planner contracts only from ontology_dashboard.planner.",
        ),
        DebtItem(
            id="validated_project3_query_boundary",
            state="regression" if raw_cypher_method else "resolved",
            stage=45,
            evidence="Project3Client public methods",
            action="Expose natural-language query, schema, search, subgraph and RAG methods; never raw Cypher execution.",
        ),
        DebtItem(
            id="foundation_identity_physical_relocation",
            state="resolved" if foundation_identity_relocated else "regression",
            stage=55,
            evidence="canonical foundation/identity modules with compatibility-only legacy re-exports",
            action="Keep context, contracts, security, identity, audit repository and demo service implementations physically canonical.",
        ),
        DebtItem(
            id="dashboard_physical_relocation",
            state="resolved" if dashboard_relocated else "regression",
            stage=55,
            evidence="canonical Dashboard models, catalog, repository and service with compatibility-only legacy re-exports",
            action="Keep Dashboard contracts, catalog constants, repository cache and service implementation physically canonical.",
        ),
        DebtItem(
            id="analysis_physical_relocation",
            state="resolved" if analysis_relocated else "regression",
            stage=55,
            evidence="canonical Analysis models, durable repository and service with compatibility-only legacy re-exports",
            action="Keep durable run state, cache identity, cursor lifecycle and materialization-facing Analysis service physically canonical.",
        ),
        DebtItem(
            id="export_workflow_physical_relocation",
            state="resolved" if export_workflow_relocated else "regression",
            stage=55,
            evidence="canonical Export and Role Workflow models, repositories and services with compatibility-only legacy re-exports",
            action="Keep export checkpoints, approval workflows, field actions and transactional outbox repository identities physically canonical.",
        ),
        DebtItem(
            id="ontology_compatibility_physical_relocation",
            state="resolved" if ontology_compatibility_relocated else "regression",
            stage=55,
            evidence="canonical Ontology, provider, report, conversation and planner compatibility modules",
            action="Keep registry constants, ontology repositories/services, deterministic fallback and planner compatibility physically canonical.",
        ),
        DebtItem(
            id="legacy_namespace_path_extension",
            state="regression" if legacy_path_extension else "resolved",
            stage=55,
            evidence="api/ontology_dashboard/__init__.py",
            action="Keep ontology_dashboard package resolution confined to its canonical directory.",
        ),
        DebtItem(
            id="legacy_package_removed",
            state="resolved" if not legacy_python_sources and not legacy_package_discovered else "regression",
            stage=55,
            evidence="legacy Python source inventory and setuptools package discovery",
            action="Do not restore the historical runtime package or include it in package discovery.",
        ),
        DebtItem(
            id="legacy_composition_root",
            state="resolved" if canonical_root_present and not legacy_root_executable else "regression",
            stage=55,
            evidence="api/ontology_dashboard/main.py with a compatibility-only legacy shim",
            action="Keep the executable FastAPI composition root in ontology_dashboard.main.",
        ),
    ]


def assert_no_regressions(items: list[DebtItem]) -> None:
    regressions = [item for item in items if item.state == "regression"]
    if regressions:
        details = "\n".join(f"- {item.id}: {item.action}" for item in regressions)
        raise AssertionError(f"architecture debt guard failed:\n{details}")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    items = collect_architecture_debt(root)
    print(json.dumps([asdict(item) for item in items], ensure_ascii=False, indent=2))
    assert_no_regressions(items)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

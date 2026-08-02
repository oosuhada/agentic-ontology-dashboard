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


def collect_architecture_debt(root: Path) -> list[DebtItem]:
    canonical_init = root / "api" / "ontology_dashboard" / "__init__.py"
    composition_root = root / "api" / "factory_signal_board" / "main.py"
    planner_router = root / "api" / "ontology_dashboard" / "routers" / "planner.py"
    dependencies = root / "api" / "ontology_dashboard" / "dependencies.py"
    feature_flags = root / "web" / "src" / "featureFlags.ts"
    dashboard_shell = root / "web" / "src" / "features" / "dashboard" / "DashboardShell.tsx"
    roadmap = root / "docs" / "10-product-convergence-polyglot-agentic-roadmap.md"
    master_prompt = root / "docs" / "next-session-master-prompt.md"
    project3_client = root / "api" / "ontology_dashboard" / "integrations" / "project3" / "client.py"

    legacy_path_extension = _contains(canonical_init, "__path__.append")
    legacy_root_present = composition_root.exists()
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
    roadmap_is_override = _contains(master_prompt, "10-product-convergence-polyglot-agentic-roadmap.md")
    polyglot_target = all(
        _contains(roadmap, token)
        for token in ("PostgreSQL", "pgvector", "Neo4j", "LangGraph")
    )
    raw_cypher_method = any(
        _contains(project3_client, token)
        for token in ("def execute_cypher", "def cypher(", "raw_cypher")
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
            id="legacy_namespace_path_extension",
            state="accepted" if legacy_path_extension else "resolved",
            stage=55,
            evidence="api/ontology_dashboard/__init__.py",
            action="Physically relocate remaining runtime modules, then delete the package path extension.",
        ),
        DebtItem(
            id="legacy_composition_root",
            state="accepted" if legacy_root_present else "resolved",
            stage=55,
            evidence="api/factory_signal_board/main.py",
            action="Move the FastAPI composition root to ontology_dashboard.main and retain no executable legacy package.",
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

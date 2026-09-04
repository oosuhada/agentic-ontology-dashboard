from __future__ import annotations

import ast
from pathlib import Path

from app.planner import PlannerLLMPort
from app.planner.planner_router import build_planner_router


ROOT = Path(__file__).resolve().parents[1]
PLANNER_ROOT = ROOT / "systems" / "backend" / "app" / "planner"
LEGACY_ROOT = ROOT / "systems" / "backend" / "ontology_dashboard"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_planner_sources_are_physically_canonical() -> None:
    required = {
        "__init__.py",
        "conversation.py",
        "layout.py",
        "planner_router.py",
        "planner_schema.py",
        "planner_service.py",
        "ports.py",
        "state.py",
    }
    assert required <= {path.name for path in PLANNER_ROOT.glob("*.py")}

    removed = (
        LEGACY_ROOT / "conversation.py",
        LEGACY_ROOT / "ontology_planner_models.py",
        LEGACY_ROOT / "ontology_planner_service.py",
        LEGACY_ROOT / "planner",
        LEGACY_ROOT / "routers" / "planner.py",
    )
    assert all(not path.exists() for path in removed)


def test_planner_application_layer_has_no_legacy_or_infra_implementation_imports() -> None:
    forbidden: list[str] = []
    for path in PLANNER_ROOT.glob("*.py"):
        if path.name == "planner_router.py":
            continue
        for module in _imports(path):
            if module == "ontology_dashboard" or module.startswith("app.runtime."):
                forbidden.append(f"{path.name}: {module}")
            if module == "app.infra" or module.startswith("app.infra."):
                forbidden.append(f"{path.name}: {module}")
    assert forbidden == []


def test_generic_agent_runtime_is_not_recreated_under_planner() -> None:
    assert not (PLANNER_ROOT / "orchestration.py").exists()
    assert not (PLANNER_ROOT / "agent.py").exists()
    assert not LEGACY_ROOT.exists()


def test_planner_llm_port_and_router_factory_are_public() -> None:
    assert PlannerLLMPort is not None
    assert callable(build_planner_router)

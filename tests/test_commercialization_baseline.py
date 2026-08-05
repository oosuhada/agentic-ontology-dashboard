from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "commercialization_baseline",
    ROOT / "scripts/generate_commercialization_baseline.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_phase17_baseline_is_deterministic_and_truthful() -> None:
    first = MODULE.build_baseline(ROOT, include_environment=False)
    second = MODULE.build_baseline(ROOT, include_environment=False)

    assert first == second
    assert first["package_lock"]["consistent"] is True
    assert first["inventory"]["legacy_namespace_files"] == []
    assert [item["state"] for item in first["version_baseline"]] == [
        "implemented",
        "implemented",
        "implemented",
        "not_implemented",
    ]
    stale = {item["path"]: item for item in first["document_freshness"]}
    assert stale["docs/20-architecture/current-state/current-state.md"]["status"] == "stale"


def test_phase17_markdown_distinguishes_production_readiness() -> None:
    payload = MODULE.build_baseline(ROOT, include_environment=False)
    rendered = MODULE.render_markdown(payload)

    assert "Passing local tests does not make" in rendered
    assert "V4 starts as `not_implemented`" in rendered

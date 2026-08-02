from __future__ import annotations

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


def test_remaining_legacy_debt_is_explicitly_owned_by_stage55() -> None:
    items = collect_architecture_debt(ROOT)
    accepted = {item.id: item.stage for item in items if item.state == "accepted"}
    assert accepted.get("legacy_namespace_path_extension") == 55
    assert accepted.get("legacy_composition_root") == 55

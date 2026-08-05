from pathlib import Path

from ontology_dashboard.application_runtime import ApplicationRuntimeRepository, SearchRequest
from ontology_dashboard.migrations import migrate


ORG = "org-ontology-demo"
PROJECT = "manufacturing-demo-project"


def repository(tmp_path: Path) -> ApplicationRuntimeRepository:
    database = tmp_path / "phase29.db"
    migrate(str(database))
    result = ApplicationRuntimeRepository(database)
    result.ensure_samples(ORG, PROJECT)
    return result


def test_generates_standard_and_configured_object_views(tmp_path: Path) -> None:
    snapshot = repository(tmp_path).snapshot(ORG, PROJECT)
    views = {(item["object_type_id"], item["form_factor"]): item for item in snapshot.object_views}
    assert ("equipment", "full") in views
    assert ("compressor", "panel") in views
    assert "lineage" in views[("equipment", "full")]["definition"]["sections"]
    assert snapshot.safety["fallback"].startswith("standard Object View")


def test_renderer_and_component_catalog_are_safe_and_accessible(tmp_path: Path) -> None:
    snapshot = repository(tmp_path).snapshot(ORG, PROJECT)
    assert snapshot.renderer_registry["marked"] == "masked-value"
    assert snapshot.renderer_registry["unknown"] == "safe-json-fallback"
    assert {item["type"] for item in snapshot.component_catalog} >= {
        "object-set-table",
        "object-view",
        "action-form",
    }
    assert snapshot.safety["expressions"] == "typed variables; no JavaScript"


def test_global_search_prefilters_markings_before_delivery(tmp_path: Path) -> None:
    repo = repository(tmp_path)
    hidden = repo.search(
        ORG,
        PROJECT,
        SearchRequest(query="CNC", eligible_markings=()),
    )
    assert hidden == ()
    visible = repo.search(
        ORG,
        PROJECT,
        SearchRequest(query="CNC", eligible_markings=("confidential",)),
    )
    assert visible[0]["id"] == "equipment:M-001"
    assert visible[0]["score"] == 80


def test_metadata_application_uses_whitelisted_components_and_typed_events(tmp_path: Path) -> None:
    snapshot = repository(tmp_path).snapshot(ORG, PROJECT)
    page = snapshot.application["pages"][0]
    catalog = {item["type"] for item in snapshot.component_catalog}
    assert all(component["type"] in catalog for component in page["components"])
    assert snapshot.application["variables"]["assetSet"]["kind"] == "interface_query"
    assert snapshot.application["events"][0]["action"] == "set"


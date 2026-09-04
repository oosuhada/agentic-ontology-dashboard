from pathlib import Path

from app.infra.db.dataset_repository import DatasetRepository
from scripts.seed_demo_dataset_catalog import ORGANIZATION_ID, PROJECT_ID, seed


def test_demo_dataset_bootstrap_is_versioned_and_idempotent(tmp_path: Path) -> None:
    database = tmp_path / "demo.db"
    artifact_root = tmp_path / "artifacts"

    first = seed(str(database), artifact_root)
    second = seed(str(database), artifact_root)

    assert len(first) == 2
    assert second == first
    assert sum(item["records"] for item in first) == 15
    assert len(list(artifact_root.glob("*.jsonl"))) == 2

    repository = DatasetRepository(database)
    datasets = repository.list_datasets(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
    )
    assert {item["id"] for item in datasets} == {
        "ds-manufacturing-equipment",
        "ds-manufacturing-risk-events",
    }
    assert sum(int(item["record_count"]) for item in datasets) == 15
    assert all(item["projection_health"]["relational"] == "ready" for item in datasets)
    assert all(item["source_type"] == "local_fixture" for item in datasets)

    for dataset in datasets:
        versions = repository.list_versions(
            organization_id=ORGANIZATION_ID,
            project_id=PROJECT_ID,
            dataset_id=dataset["id"],
        )
        assert len(versions) == 1
        materializations = repository.list_materializations(
            organization_id=ORGANIZATION_ID,
            project_id=PROJECT_ID,
            dataset_id=dataset["id"],
        )
        assert len(materializations) == 1

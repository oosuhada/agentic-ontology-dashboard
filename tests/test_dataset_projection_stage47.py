from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.dataset import (
    DatasetCatalogService,
    DatasetCreateRequest,
    DatasetVersionCreateRequest,
    OntologyMappingCreateRequest,
)
from app.infra.db.dataset_repository import DatasetRepository
from app.dataset.projection import (
    DatasetProjectionCoordinator,
    InMemoryProjectionPort,
)
from app.dependencies import (
    build_manufacturing_service,
    get_dataset_catalog_service,
    get_identity_service,
    get_service,
)
from app.identity import CSRF_COOKIE, IdentityService
from app.main import app
from app.infra.db.migrations import migrate
from identity_test_support import build_identity_service

ROOT = Path(__file__).resolve().parents[1]
CHECKSUM = "a" * 64


@pytest.fixture()
def setup(tmp_path: Path):
    database_path = tmp_path / "dataset-projection.db"
    migrate(str(database_path))
    identity = build_identity_service(database_path, app_env="test", seed_demo=True)
    repository = DatasetRepository(database_path)
    catalog = DatasetCatalogService(repository)
    user = identity.repository.authenticate("fde@ontology.local", "FDE!2026")
    principal = identity.repository.principal(
        user["id"],
        active_project_id="manufacturing-demo-project",
    )
    return database_path, identity, repository, catalog, principal


def create_catalog_fixture(catalog: DatasetCatalogService, principal):
    dataset = catalog.create_dataset(
        principal=principal,
        request=DatasetCreateRequest(
            id="ds-bearing-events",
            project_id="manufacturing-demo-project",
            workspace_id="manufacturing-demo",
            slug="bearing-events",
            display_name="Bearing Events",
            description="Curated bearing condition records",
            source_type="fixture",
        ),
    )
    version = catalog.create_version(
        principal=principal,
        project_id=dataset.project_id,
        dataset_id=dataset.id,
        request=DatasetVersionCreateRequest(
            source_version="fixture-2026-08-02",
            checksum_sha256=CHECKSUM,
            schema={
                "fields": [
                    {"name": "equipment_id", "type": "string"},
                    {"name": "risk_score", "type": "number"},
                ]
            },
            profile={"null_ratio": 0.0},
            record_count=2,
        ),
    )
    mapping = catalog.save_mapping(
        principal=principal,
        project_id=dataset.project_id,
        dataset_id=dataset.id,
        version_id=version.id,
        request=OntologyMappingCreateRequest(
            object_type="EquipmentRiskObservation",
            identity_field="equipment_id",
            property_mapping={
                "equipment_id": "equipment_id",
                "risk_score": "risk_score",
                "note": "note",
            },
            content_fields=["equipment_id", "note"],
            allowed_roles=["process_engineer", "ml_validator", "fde"],
        ),
    )
    return dataset, version, mapping


def test_dataset_version_creates_three_pending_store_projections(setup) -> None:
    _, _, repository, catalog, principal = setup
    dataset, version, mapping = create_catalog_fixture(catalog, principal)

    detail = catalog.detail(
        principal=principal,
        project_id=dataset.project_id,
        dataset_id=dataset.id,
    )
    assert detail.versions[0].id == version.id
    assert detail.mappings[0].id == mapping.id
    assert {item.store_kind for item in detail.projections} == {
        "relational",
        "graph",
        "vector",
    }
    assert {item.status for item in detail.projections} == {"pending"}
    assert len({item.object_namespace for item in detail.projections}) == 1
    assert all(item.dataset_version_id == version.id for item in detail.projections)
    assert repository.list_datasets(
        organization_id=principal.organization_id,
        project_id=dataset.project_id,
    )[0]["projection_health"] == {
        "relational": "pending",
        "graph": "pending",
        "vector": "pending",
    }


def test_one_dataset_version_preserves_identity_across_all_store_ports(setup) -> None:
    _, _, repository, catalog, principal = setup
    dataset, version, _ = create_catalog_fixture(catalog, principal)
    batch = catalog.build_projection_batch(
        principal=principal,
        project_id=dataset.project_id,
        dataset_id=dataset.id,
        version_id=version.id,
        records=[
            {"equipment_id": "M-014", "risk_score": 0.91, "note": "bearing vibration"},
            {"equipment_id": "M-027", "risk_score": 0.42, "note": "monitor"},
        ],
    )
    ports = {
        "relational": InMemoryProjectionPort("relational"),
        "graph": InMemoryProjectionPort("graph"),
        "vector": InMemoryProjectionPort("vector"),
    }
    result = DatasetProjectionCoordinator(repository, ports).run(
        batch=batch,
        organization_id=principal.organization_id,
        project_id=dataset.project_id,
    )

    assert result == {"relational": 2, "graph": 2, "vector": 2}
    expected_ids = {item.object_id for item in batch.objects}
    assert expected_ids
    for port in ports.values():
        assert set(port.objects) == expected_ids
        assert {item.project_id for item in port.objects.values()} == {dataset.project_id}
        assert {item.dataset_version_id for item in port.objects.values()} == {version.id}
        assert {item.source_version for item in port.objects.values()} == {
            "fixture-2026-08-02"
        }
    detail = catalog.detail(
        principal=principal,
        project_id=dataset.project_id,
        dataset_id=dataset.id,
    )
    assert {item.status for item in detail.projections} == {"ready"}
    assert detail.versions[0].status == "ready"

    # A second run is idempotent and does not call already-ready store ports.
    second = DatasetProjectionCoordinator(repository, ports).run(
        batch=batch,
        organization_id=principal.organization_id,
        project_id=dataset.project_id,
    )
    assert second == result
    assert {port.calls for port in ports.values()} == {1}


def test_projection_failure_is_recorded_and_retryable(setup) -> None:
    _, _, repository, catalog, principal = setup
    dataset, version, _ = create_catalog_fixture(catalog, principal)
    batch = catalog.build_projection_batch(
        principal=principal,
        project_id=dataset.project_id,
        dataset_id=dataset.id,
        version_id=version.id,
        records=[{"equipment_id": "M-014", "risk_score": 0.91}],
    )

    class FailingPort(InMemoryProjectionPort):
        def project(self, batch):
            raise RuntimeError("neo4j unavailable")

    ports = {
        "relational": InMemoryProjectionPort("relational"),
        "graph": FailingPort("graph"),
        "vector": InMemoryProjectionPort("vector"),
    }
    with pytest.raises(RuntimeError, match="neo4j unavailable"):
        DatasetProjectionCoordinator(repository, ports).run(
            batch=batch,
            organization_id=principal.organization_id,
            project_id=dataset.project_id,
        )
    graph = next(
        item
        for item in repository.list_projections(
            organization_id=principal.organization_id,
            project_id=dataset.project_id,
            dataset_id=dataset.id,
            version_id=version.id,
        )
        if item["store_kind"] == "graph"
    )
    assert graph["status"] == "failed"
    assert "neo4j unavailable" in graph["last_error"]
    repository.retry_projection(
        organization_id=principal.organization_id,
        project_id=dataset.project_id,
        projection_id=graph["id"],
    )
    retried = next(
        item
        for item in repository.list_projections(
            organization_id=principal.organization_id,
            project_id=dataset.project_id,
            dataset_id=dataset.id,
            version_id=version.id,
        )
        if item["store_kind"] == "graph"
    )
    assert retried["status"] == "pending"
    assert retried["last_error"] is None


@pytest.fixture()
def api_client(setup):
    database_path, identity, _, catalog, _ = setup
    domain_service = build_manufacturing_service(database_path, root=ROOT)
    app.dependency_overrides[get_identity_service] = lambda: identity
    app.dependency_overrides[get_service] = lambda: domain_service
    app.dependency_overrides[get_dataset_catalog_service] = lambda: catalog
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def login(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = client.cookies.get(CSRF_COOKIE)
    assert token
    return {"X-CSRF-Token": token}


def test_dataset_api_is_project_scoped_and_permission_guarded(api_client: TestClient) -> None:
    csrf = login(api_client, "fde@ontology.local", "FDE!2026")
    created = api_client.post(
        "/api/projects/manufacturing-demo-project/dataset-catalog",
        headers=csrf,
        json={
            "id": "ds-api-fixture",
            "project_id": "manufacturing-demo-project",
            "workspace_id": "manufacturing-demo",
            "slug": "api-fixture",
            "display_name": "API Fixture",
            "source_type": "fixture",
        },
    )
    assert created.status_code == 201, created.text
    listed = api_client.get("/api/projects/manufacturing-demo-project/dataset-catalog")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == "ds-api-fixture"

    inactive = api_client.get("/api/projects/azure-fleet-maintenance-project/dataset-catalog")
    assert inactive.status_code == 409
    assert inactive.json()["error"]["code"] == "active_project_mismatch"

    api_client.post("/api/auth/logout", headers=csrf)
    login(api_client, "engineer@ontology.local", "Engineer!2026")
    forbidden = api_client.get("/api/projects/manufacturing-demo-project/dataset-catalog")
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "permission_denied"

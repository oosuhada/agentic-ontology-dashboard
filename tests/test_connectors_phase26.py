from __future__ import annotations

from pathlib import Path

from ontology_dashboard.connectors import (
    ConnectorRepository,
    ConnectorService,
    FixtureConnectorAdapter,
    connector_readiness,
    schema_drift,
)
from ontology_dashboard.distributed_runtime import DurableJobRepository, DurableWorker
from ontology_dashboard.migrations import migrate
from ontology_dashboard.projects import ProjectRepository


ORG = "org-ontology-demo"
PROJECT = "manufacturing-demo-project"
WORKSPACE = "manufacturing-demo"
ACTOR = "user-manager"


def setup(tmp_path: Path):
    database = tmp_path / "phase26.db"
    migrate(str(database))
    ProjectRepository(database)
    repository = ConnectorRepository(database)
    definition = repository.ensure_fixture(
        organization_id=ORG,
        project_id=PROJECT,
        workspace_id=WORKSPACE,
        actor=ACTOR,
    )
    jobs = DurableJobRepository(database)
    service = ConnectorService(repository, jobs, {"fixture": FixtureConnectorAdapter()})
    return database, repository, definition, service


def test_schema_drift_classifies_additive_and_breaking_changes() -> None:
    additive = schema_drift({"id": "str"}, {"id": "str", "value": "float"})
    breaking = schema_drift({"id": "str", "value": "float"}, {"id": "int"})
    assert additive.added == ("value",)
    assert additive.breaking is False
    assert breaking.removed == ("value",)
    assert breaking.type_changed["id"] == ("str", "int")
    assert breaking.breaking is True


def test_ingestion_commits_valid_records_and_quarantines_invalid_payload(tmp_path: Path) -> None:
    _, repository, definition, service = setup(tmp_path)
    run = service.execute(definition, actor=ACTOR)
    assert run.state == "succeeded"
    assert run.records_read == 3
    assert run.records_committed == 2
    assert run.records_quarantined == 1
    assert repository.checkpoint(definition) == {"offset": 3}
    assert repository.committed_records_count(ORG, PROJECT, definition.id) == 2
    runs = repository.list_runs(ORG, PROJECT)
    assert runs[0].id == run.id
    assert repository.last_quarantine_count == 1


def test_durable_connector_job_preserves_idempotent_checkpoint(tmp_path: Path) -> None:
    _, repository, definition, service = setup(tmp_path)
    job_id = service.enqueue(definition, actor=ACTOR)
    jobs = service.jobs
    worker = DurableWorker(
        jobs,
        worker_id="connector-worker",
        worker_version="phase26",
        runtime_checksum="connector-checksum",
        job_types=("connector_ingestion",),
        handlers={
            "connector_ingestion": lambda job: service.execute(
                repository.get(job.organization_id, job.project_id, job.payload["connector_id"]),
                actor=job.payload["actor_user_id"],
            ).model_dump(mode="json")
        },
    )
    completed = worker.process_once(organization_id=ORG, project_id=PROJECT)
    assert completed is not None
    assert completed.id == job_id
    assert completed.state == "succeeded"
    assert repository.checkpoint(definition) == {"offset": 3}
    second = service.execute(definition, actor=ACTOR)
    assert second.records_read == 0
    assert second.records_committed == 0
    assert repository.checkpoint(definition) == {"offset": 3}
    assert repository.committed_records_count(ORG, PROJECT, definition.id) == 2


def test_connector_readiness_uses_secret_references_only(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ONTOLOGY_DASHBOARD_CONNECTOR_POSTGRESQL_CREDENTIAL_REF", "secret://db/source-a")
    readiness = connector_readiness()
    assert readiness.providers["postgresql"]["state"] == "ready"
    assert readiness.providers["postgresql"]["credential_reference"] is True
    assert "secret://db/source-a" not in str(readiness.model_dump())
    assert readiness.state == "blocked"
    assert readiness.secret_handling.startswith("secret-manager reference")

"""Production connector contracts, checkpointing and quarantine semantics."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .distributed_runtime import DurableJobRepository
from .observability import METRICS
from .postgresql_compat import postgres_repository_connection
from .postgresql_repositories import is_postgresql


ConnectorType = Literal["fixture", "postgresql", "mysql", "sqlserver", "s3", "http", "kafka", "mqtt"]
ConnectorState = Literal["draft", "ready", "paused", "blocked", "error", "disabled"]


class ConnectorDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    organization_id: str
    project_id: str
    workspace_id: str | None = None
    name: str
    connector_type: ConnectorType
    config: dict[str, Any]
    credential_reference: str | None = None
    schema_contract: dict[str, str]
    checkpoint_policy: dict[str, Any]
    freshness_policy_seconds: int
    max_batch_records: int
    max_inflight_batches: int
    status: ConnectorState
    created_by: str
    created_at: datetime
    updated_at: datetime


class ConnectorRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str
    payload: dict[str, Any]
    checkpoint: dict[str, Any]
    event_time: datetime | None = None


class ConnectorBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    records: tuple[ConnectorRecord, ...]
    next_checkpoint: dict[str, Any]
    source_schema: dict[str, str]
    bytes_read: int
    exhausted: bool


class SchemaDrift(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    added: tuple[str, ...]
    removed: tuple[str, ...]
    type_changed: dict[str, tuple[str, str]]
    breaking: bool


class IngestionRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    connector_id: str
    state: str
    records_read: int
    records_committed: int
    records_quarantined: int
    bytes_read: int
    backpressure_events: int
    schema_drift: SchemaDrift
    checkpoint_before: dict[str, Any]
    checkpoint_after: dict[str, Any]
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ConnectorReadiness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: Literal["ready", "degraded", "not_configured", "blocked"]
    providers: dict[str, dict[str, Any]]
    checkpoint: str
    schema_drift: str
    quarantine: str
    backpressure: str
    secret_handling: str
    blockers: tuple[str, ...]


class ConnectorSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    readiness: ConnectorReadiness
    connectors: tuple[ConnectorDefinition, ...]
    runs: tuple[IngestionRun, ...]
    quarantine_count: int


class ConnectorRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=500)


class ConnectorAdapter(Protocol):
    def test(self, definition: ConnectorDefinition) -> dict[str, Any]: ...
    def read_batch(self, definition: ConnectorDefinition, checkpoint: dict[str, Any]) -> ConnectorBatch: ...


class FixtureConnectorAdapter:
    def __init__(self, records: Iterable[dict[str, Any]] | None = None) -> None:
        self.records = list(records or [
            {"machine_id": "M-001", "temperature": 71.2, "failure_probability": 0.12},
            {"machine_id": "M-002", "temperature": 92.4, "failure_probability": 0.81},
            {"machine_id": "M-003", "temperature": "invalid", "failure_probability": 0.45},
        ])

    def test(self, definition: ConnectorDefinition) -> dict[str, Any]:
        return {"state": "ready", "records_available": len(self.records), "credential_used": False}

    def read_batch(self, definition: ConnectorDefinition, checkpoint: dict[str, Any]) -> ConnectorBatch:
        offset = max(0, int(checkpoint.get("offset", 0)))
        selected = self.records[offset : offset + definition.max_batch_records]
        records = tuple(
            ConnectorRecord(
                key=str(item.get("machine_id", f"record-{offset + index}")),
                payload=dict(item),
                checkpoint={"offset": offset + index + 1},
            )
            for index, item in enumerate(selected)
        )
        schema: dict[str, str] = {}
        for item in selected:
            for key, value in item.items():
                schema.setdefault(key, type(value).__name__)
        return ConnectorBatch(
            records=records,
            next_checkpoint={"offset": offset + len(selected)},
            source_schema=schema,
            bytes_read=sum(len(json.dumps(item, ensure_ascii=False).encode()) for item in selected),
            exhausted=offset + len(selected) >= len(self.records),
        )


def schema_drift(contract: Mapping[str, str], source: Mapping[str, str]) -> SchemaDrift:
    contract_keys = set(contract)
    source_keys = set(source)
    changed = {
        key: (str(contract[key]), str(source[key]))
        for key in sorted(contract_keys & source_keys)
        if str(contract[key]) != str(source[key])
    }
    removed = tuple(sorted(contract_keys - source_keys))
    return SchemaDrift(
        added=tuple(sorted(source_keys - contract_keys)),
        removed=removed,
        type_changed=changed,
        breaking=bool(removed or changed),
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class ConnectorRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self.postgresql = is_postgresql(self.database)

    def _sqlite(self):
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _connection(self, organization_id: str, project_id: str):
        if self.postgresql:
            return postgres_repository_connection(self.database, organization_id=organization_id, project_id=project_id)
        repository = self
        class Context:
            def __enter__(self):
                self.connection = repository._sqlite()
                return self.connection
            def __exit__(self, exc_type, exc, tb):
                if exc_type is None: self.connection.commit()
                else: self.connection.rollback()
                self.connection.close()
        return Context()

    @staticmethod
    def _definition(row: Mapping[str, Any]) -> ConnectorDefinition:
        config = row["config_json"] if not isinstance(row["config_json"], str) else json.loads(row["config_json"])
        contract = row["schema_contract_json"] if not isinstance(row["schema_contract_json"], str) else json.loads(row["schema_contract_json"])
        checkpoint = row["checkpoint_policy_json"] if not isinstance(row["checkpoint_policy_json"], str) else json.loads(row["checkpoint_policy_json"])
        return ConnectorDefinition(
            id=str(row["id"]), organization_id=str(row["organization_id"]), project_id=str(row["project_id"]),
            workspace_id=row.get("workspace_id"), name=str(row["name"]), connector_type=str(row["connector_type"]),
            config=dict(config), credential_reference=row.get("credential_reference"), schema_contract=dict(contract),
            checkpoint_policy=dict(checkpoint), freshness_policy_seconds=int(row["freshness_policy_seconds"]),
            max_batch_records=int(row["max_batch_records"]), max_inflight_batches=int(row["max_inflight_batches"]),
            status=str(row["status"]), created_by=str(row["created_by"]), created_at=_parse(row["created_at"]),
            updated_at=_parse(row["updated_at"]),
        )

    def ensure_fixture(self, *, organization_id: str, project_id: str, workspace_id: str, actor: str) -> ConnectorDefinition:
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                "SELECT * FROM connector_definitions WHERE organization_id=? AND project_id=? AND name='Canonical fixture ingestion'",
                (organization_id, project_id),
            ).fetchone()
            if row is None:
                now = _utcnow().isoformat()
                connection.execute(
                    """INSERT INTO connector_definitions(
                    id,organization_id,project_id,workspace_id,name,connector_type,config_json,
                    schema_contract_json,checkpoint_policy_json,freshness_policy_seconds,
                    max_batch_records,max_inflight_batches,status,created_by,created_at,updated_at
                    ) VALUES (?,?,?,?,?,'fixture','{}',?,?,?,?,4,'ready',?,?,?)""",
                    (
                        "connector-canonical-fixture", organization_id, project_id, workspace_id,
                        "Canonical fixture ingestion",
                        json.dumps({"machine_id": "str", "temperature": "float", "failure_probability": "float"}),
                        json.dumps({"type": "offset", "commit": "after durable materialization"}),
                        300, 1000, actor, now, now,
                    ),
                )
                row = connection.execute("SELECT * FROM connector_definitions WHERE id='connector-canonical-fixture'").fetchone()
        return self._definition(dict(row))

    def list_definitions(self, organization_id: str, project_id: str) -> tuple[ConnectorDefinition, ...]:
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                "SELECT * FROM connector_definitions WHERE organization_id=? AND project_id=? ORDER BY name",
                (organization_id, project_id),
            ).fetchall()
        return tuple(self._definition(dict(row)) for row in rows)

    def get(self, organization_id: str, project_id: str, connector_id: str) -> ConnectorDefinition | None:
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                "SELECT * FROM connector_definitions WHERE id=? AND organization_id=? AND project_id=?",
                (connector_id, organization_id, project_id),
            ).fetchone()
        return None if row is None else self._definition(dict(row))

    def checkpoint(self, definition: ConnectorDefinition) -> dict[str, Any]:
        with self._connection(definition.organization_id, definition.project_id) as connection:
            row = connection.execute("SELECT checkpoint_json FROM connector_checkpoints WHERE connector_id=?", (definition.id,)).fetchone()
        if row is None: return {"offset": 0}
        value = row["checkpoint_json"]
        return dict(value if not isinstance(value, str) else json.loads(value))

    def execute(self, definition: ConnectorDefinition, adapter: ConnectorAdapter, *, actor: str) -> IngestionRun:
        before = self.checkpoint(definition)
        batch = adapter.read_batch(definition, before)
        drift = schema_drift(definition.schema_contract, batch.source_schema)
        run_id = f"ingestion-{uuid.uuid4()}"
        now = _utcnow()
        valid: list[ConnectorRecord] = []
        invalid: list[tuple[ConnectorRecord, str]] = []
        for record in batch.records:
            problems = []
            for key, expected in definition.schema_contract.items():
                if key not in record.payload:
                    problems.append(f"missing:{key}")
                elif type(record.payload[key]).__name__ != expected:
                    problems.append(f"type:{key}:{type(record.payload[key]).__name__}!={expected}")
            (invalid if problems else valid).append((record, ",".join(problems)) if problems else record)
        state = "quarantined" if drift.breaking and not valid else "succeeded"
        source_hash = hashlib.sha256(json.dumps(batch.source_schema, sort_keys=True).encode()).hexdigest()
        with self._connection(definition.organization_id, definition.project_id) as connection:
            connection.execute(
                """INSERT INTO connector_ingestion_runs(
                id,organization_id,project_id,workspace_id,connector_id,state,checkpoint_before_json,
                checkpoint_after_json,schema_hash,schema_drift_json,records_read,records_committed,
                records_quarantined,bytes_read,backpressure_events,created_by,created_at,started_at,completed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id, definition.organization_id, definition.project_id, definition.workspace_id,
                    definition.id, state, json.dumps(before), json.dumps(batch.next_checkpoint), source_hash,
                    json.dumps(drift.model_dump(mode="json")), len(batch.records), len(valid), len(invalid),
                    batch.bytes_read, 0, actor, now.isoformat(), now.isoformat(), now.isoformat(),
                ),
            )
            for record, reason in invalid:
                connection.execute(
                    """INSERT INTO connector_quarantine_records(
                    id,organization_id,project_id,workspace_id,connector_id,ingestion_run_id,
                    source_record_key,reason_code,reason_detail,payload_json,created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        f"quarantine-{uuid.uuid4()}", definition.organization_id, definition.project_id,
                        definition.workspace_id, definition.id, run_id, record.key, "schema_validation",
                        reason, json.dumps(record.payload, ensure_ascii=False), now.isoformat(),
                    ),
                )
            for record in valid:
                canonical_payload = json.dumps(
                    record.payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                payload_checksum = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
                if self.postgresql:
                    connection.execute(
                        """INSERT INTO connector_committed_records(
                        id,organization_id,project_id,workspace_id,connector_id,ingestion_run_id,
                        source_record_key,source_checkpoint_json,payload_json,payload_checksum_sha256,
                        committed_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(organization_id,project_id,connector_id,source_record_key,payload_checksum_sha256)
                        DO NOTHING""",
                        (
                            f"connector-record-{uuid.uuid4()}", definition.organization_id,
                            definition.project_id, definition.workspace_id, definition.id, run_id,
                            record.key, json.dumps(record.checkpoint), canonical_payload,
                            payload_checksum, now.isoformat(),
                        ),
                    )
                else:
                    connection.execute(
                        """INSERT OR IGNORE INTO connector_committed_records(
                        id,organization_id,project_id,workspace_id,connector_id,ingestion_run_id,
                        source_record_key,source_checkpoint_json,payload_json,payload_checksum_sha256,
                        committed_at
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            f"connector-record-{uuid.uuid4()}", definition.organization_id,
                            definition.project_id, definition.workspace_id, definition.id, run_id,
                            record.key, json.dumps(record.checkpoint), canonical_payload,
                            payload_checksum, now.isoformat(),
                        ),
                    )
            if valid:
                connection.execute(
                    """INSERT INTO connector_checkpoints(
                    connector_id,organization_id,project_id,checkpoint_json,source_schema_hash,
                    records_committed,watermark_at,committed_at,committed_run_id
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(connector_id) DO UPDATE SET checkpoint_json=excluded.checkpoint_json,
                    source_schema_hash=excluded.source_schema_hash,
                    records_committed=connector_checkpoints.records_committed+excluded.records_committed,
                    watermark_at=excluded.watermark_at,committed_at=excluded.committed_at,
                    committed_run_id=excluded.committed_run_id""",
                    (
                        definition.id, definition.organization_id, definition.project_id,
                        json.dumps(batch.next_checkpoint), source_hash, len(valid), now.isoformat(),
                        now.isoformat(), run_id,
                    ),
                )
        METRICS.inc("ontology_connector_runs_total", labels={"connector_type": definition.connector_type, "state": state})
        METRICS.inc("ontology_connector_records_total", len(valid), labels={"result": "committed"})
        METRICS.inc("ontology_connector_records_total", len(invalid), labels={"result": "quarantined"})
        return IngestionRun(
            id=run_id, connector_id=definition.id, state=state, records_read=len(batch.records),
            records_committed=len(valid), records_quarantined=len(invalid), bytes_read=batch.bytes_read,
            backpressure_events=0, schema_drift=drift, checkpoint_before=before,
            checkpoint_after=batch.next_checkpoint, created_at=now, completed_at=now,
        )

    def list_runs(self, organization_id: str, project_id: str, limit: int = 20) -> tuple[IngestionRun, ...]:
        with self._connection(organization_id, project_id) as connection:
            rows = connection.execute(
                "SELECT * FROM connector_ingestion_runs WHERE organization_id=? AND project_id=? ORDER BY created_at DESC LIMIT ?",
                (organization_id, project_id, limit),
            ).fetchall()
            quarantine = connection.execute(
                "SELECT count(*) AS count FROM connector_quarantine_records WHERE organization_id=? AND project_id=? AND replay_state='pending'",
                (organization_id, project_id),
            ).fetchone()
        result = []
        for raw in rows:
            row = dict(raw)
            drift = row["schema_drift_json"] if not isinstance(row["schema_drift_json"], str) else json.loads(row["schema_drift_json"])
            before = row["checkpoint_before_json"] or "{}"; after = row["checkpoint_after_json"] or "{}"
            result.append(IngestionRun(
                id=row["id"], connector_id=row["connector_id"], state=row["state"],
                records_read=int(row["records_read"]), records_committed=int(row["records_committed"]),
                records_quarantined=int(row["records_quarantined"]), bytes_read=int(row["bytes_read"]),
                backpressure_events=int(row["backpressure_events"]), schema_drift=SchemaDrift.model_validate(drift),
                checkpoint_before=before if isinstance(before, dict) else json.loads(before),
                checkpoint_after=after if isinstance(after, dict) else json.loads(after),
                error_code=row.get("error_code"), error_message=row.get("error_message"),
                created_at=_parse(row["created_at"]), completed_at=_parse(row.get("completed_at")),
            ))
        self.last_quarantine_count = int(quarantine["count"])
        return tuple(result)

    def committed_records_count(self, organization_id: str, project_id: str, connector_id: str) -> int:
        with self._connection(organization_id, project_id) as connection:
            row = connection.execute(
                """SELECT count(*) AS count FROM connector_committed_records
                WHERE organization_id=? AND project_id=? AND connector_id=?""",
                (organization_id, project_id, connector_id),
            ).fetchone()
        return int(row["count"])


@dataclass
class ConnectorService:
    repository: ConnectorRepository
    jobs: DurableJobRepository
    adapters: dict[str, ConnectorAdapter]

    def enqueue(self, definition: ConnectorDefinition, *, actor: str) -> str:
        run_id = f"connector-request-{uuid.uuid4()}"
        job, _ = self.jobs.enqueue(
            organization_id=definition.organization_id, project_id=definition.project_id,
            workspace_id=definition.workspace_id, job_type="connector_ingestion",
            idempotency_key=run_id, payload={"connector_id": definition.id, "actor_user_id": actor},
            created_by=actor, priority=90, max_attempts=5,
        )
        return job.id

    def execute(self, definition: ConnectorDefinition, *, actor: str) -> IngestionRun:
        adapter = self.adapters.get(definition.connector_type)
        if adapter is None:
            raise RuntimeError(f"connector adapter not configured: {definition.connector_type}")
        return self.repository.execute(definition, adapter, actor=actor)


def connector_readiness() -> ConnectorReadiness:
    providers = {}
    blockers = []
    for provider in ("postgresql", "mysql", "sqlserver", "s3", "http", "kafka", "mqtt"):
        env_name = f"ONTOLOGY_DASHBOARD_CONNECTOR_{provider.upper()}_CREDENTIAL_REF"
        configured = bool(os.getenv(env_name, "").strip())
        providers[provider] = {"state": "ready" if configured else "not_configured", "credential_reference": configured}
        if not configured: blockers.append(f"{provider} credential reference is not configured")
    providers["fixture"] = {"state": "ready", "credential_reference": False, "environment": "development/test"}
    production = os.getenv("APP_ENV", "development").lower() == "production"
    return ConnectorReadiness(
        state="blocked" if production and blockers else "degraded" if blockers else "ready",
        providers=providers,
        checkpoint="commit only after durable validation/materialization boundary",
        schema_drift="added fields reported; removed/type changes quarantine or block",
        quarantine="record payload + reason + replay lifecycle",
        backpressure="per-connector batch and inflight quotas + durable queue saturation",
        secret_handling="secret-manager reference only; never connector config or log payload",
        blockers=tuple(blockers),
    )


__all__ = [
    "ConnectorAdapter","ConnectorBatch","ConnectorDefinition","ConnectorReadiness","ConnectorRecord",
    "ConnectorRepository","ConnectorRunRequest","ConnectorService","ConnectorSnapshot","FixtureConnectorAdapter",
    "IngestionRun","SchemaDrift","connector_readiness","schema_drift",
]

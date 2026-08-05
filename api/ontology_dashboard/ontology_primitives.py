"""Tenant-scoped Ontology Interface, Action Registry and governed functions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from .postgresql_compat import postgres_repository_connection
from .postgresql_repositories import is_postgresql


class InterfaceDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    version: int
    display_name: str
    status: Literal["draft", "published", "deprecated"]
    property_contract: dict[str, str]
    capability_contract: tuple[str, ...]
    implementations: tuple[dict[str, Any], ...] = ()


class GovernedActionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    version: int
    display_name: str
    target_interface_id: str
    parameter_schema: dict[str, Any]
    execution_mode: Literal["single", "bulk", "transactional", "external"]
    approval_required: bool
    required_permission: str
    status: str


class GovernedFunctionDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    version: int
    display_name: str
    input_schema: dict[str, str]
    output_schema: dict[str, str]
    runtime_checksum: str
    timeout_ms: int
    network_policy: Literal["deny_all"]
    status: str


class PrimitiveSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    interfaces: tuple[InterfaceDefinition, ...]
    actions: tuple[GovernedActionDefinition, ...]
    functions: tuple[GovernedFunctionDefinition, ...]
    guarantees: dict[str, str]


class ActionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    object_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    parameters: dict[str, Any]
    reason: str = Field(min_length=3, max_length=500)


class ActionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    valid: bool
    action_id: str
    target_count: int
    approval_required: bool
    external_side_effect: bool
    validation_errors: tuple[str, ...]
    audit_preview: dict[str, Any]


class FunctionExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    function_id: str
    inputs: dict[str, Any]


class FunctionExecution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    function_id: str
    function_version: int
    state: Literal["succeeded", "rejected", "timed_out"]
    output: dict[str, Any]
    duration_ms: int
    runtime_checksum: str


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class OntologyPrimitiveRepository:
    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        self.postgresql = is_postgresql(self.database)

    def _connection(self, organization_id: str, project_id: str):
        if self.postgresql:
            return postgres_repository_connection(
                self.database,
                organization_id=organization_id,
                project_id=project_id,
            )
        repository = self

        class Context:
            def __enter__(self):
                self.connection = sqlite3.connect(repository.database)
                self.connection.row_factory = sqlite3.Row
                return self.connection

            def __exit__(self, exc_type, exc, tb):
                if exc_type is None:
                    self.connection.commit()
                else:
                    self.connection.rollback()
                self.connection.close()

        return Context()

    def ensure_samples(self, organization_id: str, project_id: str, actor: str) -> None:
        now = _utcnow()
        checksum = hashlib.sha256(b"risk-metric-v1:deterministic:no-network").hexdigest()
        with self._connection(organization_id, project_id) as connection:
            connection.execute(
                """INSERT INTO ontology_interface_definitions(
                id,version,organization_id,project_id,display_name,status,
                property_contract_json,capability_contract_json,created_by,created_at
                ) VALUES (?,?,?,?,?,'published',?,?,?,?)
                ON CONFLICT(organization_id,project_id,id,version) DO NOTHING""",
                (
                    "asset", 1, organization_id, project_id, "Asset",
                    json.dumps({"asset_id": "str", "display_name": "str", "risk_score": "float"}),
                    json.dumps(["inspectable", "risk_scored"]), actor, now,
                ),
            )
            for object_type, mapping in (
                ("equipment", {"asset_id": "id", "display_name": "name", "risk_score": "failure_probability"}),
                ("compressor", {"asset_id": "id", "display_name": "name", "risk_score": "risk_score"}),
            ):
                connection.execute(
                    """INSERT INTO ontology_interface_implementations(
                    organization_id,project_id,interface_id,interface_version,object_type_id,
                    property_mapping_json,created_at) VALUES (?,?,?,?,?,?,?)
                    ON CONFLICT(organization_id,project_id,interface_id,interface_version,object_type_id) DO NOTHING""",
                    (organization_id, project_id, "asset", 1, object_type, json.dumps(mapping), now),
                )
            connection.execute(
                """INSERT INTO governed_action_definitions(
                id,version,organization_id,project_id,display_name,target_interface_id,
                parameter_schema_json,execution_mode,approval_required,required_permission,status,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(organization_id,project_id,id,version) DO NOTHING""",
                (
                    "request-asset-inspection", 1, organization_id, project_id,
                    "Request asset inspection", "asset",
                    json.dumps({
                        "type": "object",
                        "required": ["priority", "due_date"],
                        "properties": {
                            "priority": {"type": "string", "enum": ["low", "normal", "high"]},
                            "due_date": {"type": "string", "format": "date"},
                        },
                    }),
                    "bulk", 1, "ontology.actions.execute", "published", now,
                ),
            )
            connection.execute(
                """INSERT INTO governed_function_definitions(
                id,version,organization_id,project_id,display_name,input_schema_json,
                output_schema_json,runtime_checksum,timeout_ms,network_policy,status,created_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(organization_id,project_id,id,version) DO NOTHING""",
                (
                    "asset-risk-metric", 1, organization_id, project_id, "Asset risk metric",
                    json.dumps({"failure_probability": "float", "criticality": "float"}),
                    json.dumps({"risk_score": "float", "band": "str"}), checksum,
                    250, "deny_all", "published", now,
                ),
            )

    def snapshot(self, organization_id: str, project_id: str) -> PrimitiveSnapshot:
        with self._connection(organization_id, project_id) as connection:
            interfaces = connection.execute(
                "SELECT * FROM ontology_interface_definitions WHERE organization_id=? AND project_id=? ORDER BY id,version DESC",
                (organization_id, project_id),
            ).fetchall()
            implementations = connection.execute(
                "SELECT * FROM ontology_interface_implementations WHERE organization_id=? AND project_id=? ORDER BY object_type_id",
                (organization_id, project_id),
            ).fetchall()
            actions = connection.execute(
                "SELECT * FROM governed_action_definitions WHERE organization_id=? AND project_id=? ORDER BY id,version DESC",
                (organization_id, project_id),
            ).fetchall()
            functions = connection.execute(
                "SELECT * FROM governed_function_definitions WHERE organization_id=? AND project_id=? ORDER BY id,version DESC",
                (organization_id, project_id),
            ).fetchall()
        impl_by_interface: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for raw in implementations:
            row = dict(raw)
            mapping = row["property_mapping_json"]
            impl_by_interface.setdefault((row["interface_id"], int(row["interface_version"])), []).append({
                "object_type_id": row["object_type_id"],
                "property_mapping": mapping if isinstance(mapping, dict) else json.loads(mapping),
            })
        return PrimitiveSnapshot(
            interfaces=tuple(
                InterfaceDefinition(
                    id=row["id"], version=int(row["version"]), display_name=row["display_name"],
                    status=row["status"],
                    property_contract=row["property_contract_json"] if isinstance(row["property_contract_json"], dict) else json.loads(row["property_contract_json"]),
                    capability_contract=tuple(row["capability_contract_json"] if isinstance(row["capability_contract_json"], list) else json.loads(row["capability_contract_json"])),
                    implementations=tuple(impl_by_interface.get((row["id"], int(row["version"])), [])),
                ) for row in map(dict, interfaces)
            ),
            actions=tuple(
                GovernedActionDefinition(
                    id=row["id"], version=int(row["version"]), display_name=row["display_name"],
                    target_interface_id=row["target_interface_id"],
                    parameter_schema=row["parameter_schema_json"] if isinstance(row["parameter_schema_json"], dict) else json.loads(row["parameter_schema_json"]),
                    execution_mode=row["execution_mode"], approval_required=bool(row["approval_required"]),
                    required_permission=row["required_permission"], status=row["status"],
                ) for row in map(dict, actions)
            ),
            functions=tuple(
                GovernedFunctionDefinition(
                    id=row["id"], version=int(row["version"]), display_name=row["display_name"],
                    input_schema=row["input_schema_json"] if isinstance(row["input_schema_json"], dict) else json.loads(row["input_schema_json"]),
                    output_schema=row["output_schema_json"] if isinstance(row["output_schema_json"], dict) else json.loads(row["output_schema_json"]),
                    runtime_checksum=row["runtime_checksum"], timeout_ms=int(row["timeout_ms"]),
                    network_policy=row["network_policy"], status=row["status"],
                ) for row in map(dict, functions)
            ),
            guarantees={
                "arbitrary_code": "denied; published deterministic implementations only",
                "network": "deny_all",
                "secrets": "not injected into function inputs or traces",
                "action_validation": "same JSON schema drives preview and generated form",
            },
        )

    def preview_action(self, organization_id: str, project_id: str, request: ActionPreviewRequest, actor: str) -> ActionPreview:
        snapshot = self.snapshot(organization_id, project_id)
        definition = next((item for item in snapshot.actions if item.id == request.action_id), None)
        if definition is None:
            raise KeyError("action not found")
        schema = definition.parameter_schema
        errors = []
        for required in schema.get("required", []):
            if required not in request.parameters:
                errors.append(f"missing:{required}")
        for name, value in request.parameters.items():
            spec = schema.get("properties", {}).get(name)
            if spec is None:
                errors.append(f"unknown:{name}")
            elif spec.get("enum") and value not in spec["enum"]:
                errors.append(f"enum:{name}")
        return ActionPreview(
            valid=not errors,
            action_id=definition.id,
            target_count=len(request.object_ids),
            approval_required=definition.approval_required,
            external_side_effect=definition.execution_mode == "external",
            validation_errors=tuple(errors),
            audit_preview={
                "actor": actor,
                "reason": request.reason,
                "object_ids": list(request.object_ids),
                "parameters": request.parameters,
                "mode": "dry_run",
            },
        )

    def execute_function(self, organization_id: str, project_id: str, request: FunctionExecutionRequest, actor: str) -> FunctionExecution:
        snapshot = self.snapshot(organization_id, project_id)
        definition = next((item for item in snapshot.functions if item.id == request.function_id), None)
        if definition is None:
            raise KeyError("function not found")
        if set(request.inputs) != set(definition.input_schema):
            raise ValueError("function input schema mismatch")
        started = time.perf_counter()
        probability = float(request.inputs["failure_probability"])
        criticality = float(request.inputs["criticality"])
        risk = max(0.0, min(1.0, probability * (0.7 + 0.3 * criticality)))
        output = {"risk_score": round(risk, 6), "band": "high" if risk >= 0.7 else "medium" if risk >= 0.35 else "low"}
        duration_ms = max(0, int((time.perf_counter() - started) * 1000))
        execution = FunctionExecution(
            id=f"function-execution-{uuid.uuid4()}", function_id=definition.id,
            function_version=definition.version, state="succeeded", output=output,
            duration_ms=duration_ms, runtime_checksum=definition.runtime_checksum,
        )
        with self._connection(organization_id, project_id) as connection:
            connection.execute(
                """INSERT INTO governed_function_executions(
                id,organization_id,project_id,function_id,function_version,input_json,output_json,
                state,duration_ms,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    execution.id, organization_id, project_id, definition.id, definition.version,
                    json.dumps(request.inputs), json.dumps(output), execution.state, duration_ms, actor, _utcnow(),
                ),
            )
        return execution


__all__ = [
    "ActionPreview", "ActionPreviewRequest", "FunctionExecution", "FunctionExecutionRequest",
    "GovernedActionDefinition", "GovernedFunctionDefinition", "InterfaceDefinition",
    "OntologyPrimitiveRepository", "PrimitiveSnapshot",
]

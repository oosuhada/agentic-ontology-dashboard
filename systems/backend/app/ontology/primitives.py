"""Ontology Interface/Action/Function contracts without persistence technology."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


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


__all__ = [
    "ActionPreview",
    "ActionPreviewRequest",
    "FunctionExecution",
    "FunctionExecutionRequest",
    "GovernedActionDefinition",
    "GovernedFunctionDefinition",
    "InterfaceDefinition",
    "PrimitiveSnapshot",
]

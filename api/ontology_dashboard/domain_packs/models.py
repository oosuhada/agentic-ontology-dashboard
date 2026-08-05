"""Domain-neutral contracts for governed domain-pack composition."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DomainPackStatus = Literal["active", "draft", "disabled"]
ContextKind = Literal["core", "supporting", "integration"]


class BoundedContextDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    display_name: str = Field(min_length=1, max_length=120)
    kind: ContextKind
    owns: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    publishes: tuple[str, ...] = ()


class DomainVocabulary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    object_label: str
    object_plural_label: str
    event_label: str
    action_label: str
    risk_label: str


class DomainPackDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    display_name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    status: DomainPackStatus
    namespace: str = Field(pattern=r"^[a-z][a-z0-9_.]{2,127}$")
    vocabulary: DomainVocabulary
    bounded_contexts: tuple[BoundedContextDefinition, ...]
    object_type_ids: tuple[str, ...] = ()
    interface_ids: tuple[str, ...] = ()
    action_type_ids: tuple[str, ...] = ()
    feature_flags: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_contexts(self) -> "DomainPackDefinition":
        context_ids = [item.id for item in self.bounded_contexts]
        if len(context_ids) != len(set(context_ids)):
            raise ValueError("bounded context IDs must be unique")
        return self


class ProjectApplicationDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    application_id: str
    application_version: Literal["v4"] = "v4"
    project_id: str
    workspace_ids: tuple[str, ...]
    domain_pack: DomainPackDefinition
    platform_namespace: str = "ontology_dashboard"
    compatibility_namespaces: tuple[str, ...] = ()
    configuration_source: Literal["project_metadata", "default_platform"]

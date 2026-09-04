"""Project metadata and lifecycle schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProjectStatus = Literal["draft", "active", "archived"]


class Project(BaseModel):
    id: str
    organization_id: str
    slug: str
    display_name: str
    description: str
    domain_pack_code: str
    status: ProjectStatus
    default_workspace_id: str | None
    created_at: str
    updated_at: str


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    display_name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=1000)
    domain_pack_code: str = Field(min_length=2, max_length=120)
    status: ProjectStatus = "draft"

    @field_validator("display_name", "description", "domain_pack_code")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    domain_pack_code: str | None = Field(default=None, min_length=2, max_length=120)
    status: ProjectStatus | None = None
    default_workspace_id: str | None = None

    @field_validator("display_name", "description", "domain_pack_code")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class ProjectMembershipUpdateRequest(BaseModel):
    """Project-owned membership lifecycle command payload."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "suspended"] = "active"
    roles: list[str] = Field(min_length=1)


__all__ = [
    "Project",
    "ProjectCreateRequest",
    "ProjectMembershipUpdateRequest",
    "ProjectStatus",
    "ProjectUpdateRequest",
]

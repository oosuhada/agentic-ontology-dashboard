from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ExportFormat = Literal["json", "csv", "pdf"]
ExportScope = Literal["dashboard", "event", "role_workspace"]


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: str
    format: ExportFormat
    scope: ExportScope = "dashboard"
    event_id: str | None = None
    title: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def require_event_id(self) -> "ExportRequest":
        if self.scope == "event" and not self.event_id:
            raise ValueError("event scope export requires event_id")
        if self.scope != "event" and self.event_id is not None:
            raise ValueError("event_id is only allowed for event scope export")
        return self


class ExportCheckpoint(BaseModel):
    id: str
    organization_id: str
    project_id: str
    workspace_id: str
    scope: ExportScope
    format: ExportFormat
    event_id: str | None
    filename: str
    media_type: str
    content_bytes: int
    snapshot_hash: str
    content_hash: str
    requested_by: str
    requested_by_name: str
    created_at: str


class ExportArtifact(BaseModel):
    checkpoint: ExportCheckpoint
    content: bytes

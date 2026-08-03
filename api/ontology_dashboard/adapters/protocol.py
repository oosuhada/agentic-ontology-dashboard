from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .models import DatasetManifest, QuarantinedRecord


@runtime_checkable
class DatasetAdapter(Protocol):
    code: str
    display_name: str

    def required_fields(self, manifest: DatasetManifest) -> set[str]: ...

    def normalize_record(
        self,
        record: dict[str, str],
        *,
        manifest: DatasetManifest,
        row_number: int,
    ) -> dict[str, Any] | QuarantinedRecord: ...

    def derive_metrics(
        self,
        records: list[dict[str, Any]],
        *,
        manifest: DatasetManifest,
    ) -> dict[str, Any]: ...


class SourceFilePolicy(Protocol):
    def validate(self, path: Path) -> Path: ...

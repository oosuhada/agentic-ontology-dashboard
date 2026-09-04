"""Read immutable Dataset materializations through the Dataset query contract."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .dataset_repository import DatasetRepositoryPort


class DatasetMaterializationSource:
    """Loads the latest ready materialization for a project-scoped Dataset.

    The source only accepts registered materialization artifacts. It never accepts
    arbitrary filesystem paths from consumer configuration.
    """

    def __init__(self, repository: DatasetRepositoryPort) -> None:
        self.repository = repository

    def load(
        self,
        *,
        organization_id: str,
        project_id: str,
        workspace_id: str,
        dataset_id: str,
        limit: int,
        version_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None, dict[str, Any]]:
        dataset = self.repository.get_dataset(
            organization_id=organization_id,
            project_id=project_id,
            dataset_id=dataset_id,
        )
        if dataset["workspace_id"] != workspace_id:
            raise ValueError("materialized Dataset belongs to another Workspace")
        materialization = self.repository.latest_materialization(
            organization_id=organization_id,
            project_id=project_id,
            dataset_id=dataset_id,
            version_id=version_id,
        )
        path = self._file_path(materialization["artifact_uri"])
        rows = self._read_rows(path, materialization["format"], max(1, limit))
        metadata = {
            "dataset_id": dataset_id,
            "dataset_version_id": materialization["dataset_version_id"],
            "materialization_id": materialization["id"],
            "artifact_uri": materialization["artifact_uri"],
            "format": materialization["format"],
            "source_reference": materialization["source_reference"],
            "checksum_sha256": materialization["checksum_sha256"],
            "registered_record_count": materialization["record_count"],
        }
        return rows, str(materialization["created_at"]), metadata

    @staticmethod
    def _file_path(uri: str) -> Path:
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            raise ValueError("only registered file:// materialization artifacts can be Dataset inputs")
        path = Path(unquote(parsed.path)).resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"materialization artifact is unavailable: {path}")
        return path

    @staticmethod
    def _read_rows(path: Path, format_name: str, limit: int) -> list[dict[str, Any]]:
        normalized = format_name.lower()
        if normalized == "parquet":
            try:
                import pyarrow.parquet as pq
            except ImportError as error:
                raise RuntimeError(
                    "Reading Parquet Dataset sources requires the polyglot/production extra (pyarrow)."
                ) from error
            table = pq.read_table(path)
            return [dict(row) for row in table.slice(0, limit).to_pylist()]
        if normalized == "jsonl":
            rows: list[dict[str, Any]] = []
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if len(rows) >= limit:
                        break
                    value = json.loads(line)
                    if isinstance(value, dict):
                        rows.append(value)
            return rows
        if normalized == "csv":
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for _, row in zip(range(limit), csv.DictReader(handle))]
        raise ValueError(f"unsupported materialization format: {format_name}")


__all__ = ["DatasetMaterializationSource"]

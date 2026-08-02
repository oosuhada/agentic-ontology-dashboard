"""Full Analysis-result materialization into immutable Parquet-backed Dataset Versions."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from ..analysis_models import AnalysisRunRequest
from ..analysis_service import AnalysisService
from ..identity import Principal
from ..ontology_service import OntologyService
from .models import (
    DatasetCreateRequest,
    DatasetFileCreate,
    DatasetRecord,
    DatasetVersionCreateRequest,
    DatasetVersionRecord,
    MaterializationCreateRequest,
    MaterializationRecord,
)
from .service import DatasetCatalogService


class AnalysisMaterializationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=3, max_length=160)
    workspace_id: str = Field(min_length=3, max_length=160)
    node_id: str = Field(min_length=1, max_length=240)
    version_policy: str = Field(default="pinned", pattern=r"^(pinned|latest_published)$")
    version: int | None = Field(default=None, ge=1)
    dataset_id: str | None = Field(default=None, min_length=3, max_length=160)
    dataset_slug: str | None = Field(default=None, max_length=120)
    dataset_name: str | None = Field(default=None, max_length=240)
    preview_limit: int = Field(default=500, ge=1, le=5000)
    full_limit: int = Field(default=5000, ge=1, le=5000)


class AnalysisMaterializationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: DatasetRecord
    version: DatasetVersionRecord
    materialization: MaterializationRecord
    analysis_run_id: str
    analysis_id: str
    analysis_version: int
    node_id: str
    preview_row_count: int
    materialized_row_count: int
    checksum_sha256: str
    artifact_uri: str


ParquetWriter = Callable[[list[dict[str, Any]], Path], None]


class AnalysisDatasetMaterializer:
    def __init__(
        self,
        *,
        analysis: AnalysisService,
        ontology: OntologyService,
        datasets: DatasetCatalogService,
        artifact_root: str | Path | None = None,
        parquet_writer: ParquetWriter | None = None,
    ) -> None:
        self.analysis = analysis
        self.ontology = ontology
        self.datasets = datasets
        configured = os.getenv("ONTOLOGY_DASHBOARD_MATERIALIZATION_ROOT", "").strip()
        self.artifact_root = Path(artifact_root or configured or "data/materializations").resolve()
        self.parquet_writer = parquet_writer or write_parquet

    def materialize(
        self,
        *,
        principal: Principal,
        analysis_id: str,
        request: AnalysisMaterializationRequest,
    ) -> AnalysisMaterializationResult:
        if request.project_id not in principal.project_scopes:
            raise ValueError("analysis materialization is outside the authenticated project scope")
        if request.workspace_id not in principal.workspace_scopes:
            raise ValueError("analysis materialization is outside the authenticated workspace scope")

        preview = self.analysis.run(
            analysis_id=analysis_id,
            request=AnalysisRunRequest(
                workspace_id=request.workspace_id,
                version_policy=request.version_policy,
                version=request.version,
                preview_limit=request.preview_limit,
            ),
            principal=principal,
            ontology=self.ontology,
        )
        if preview.status != "succeeded":
            raise RuntimeError(preview.error or "analysis preview run failed")
        preview_node = preview.node_results.get(request.node_id)
        if preview_node is None:
            raise KeyError(f"analysis node not found: {request.node_id}")

        full_run = self.analysis.run(
            analysis_id=analysis_id,
            request=AnalysisRunRequest(
                workspace_id=request.workspace_id,
                version_policy="pinned",
                version=preview.analysis_version,
                preview_limit=request.full_limit,
            ),
            principal=principal,
            ontology=self.ontology,
        )
        if full_run.status != "succeeded":
            raise RuntimeError(full_run.error or "analysis full materialization run failed")
        node = full_run.node_results.get(request.node_id)
        if node is None:
            raise KeyError(f"analysis node not found: {request.node_id}")
        rows = node.get("rows") if isinstance(node.get("rows"), list) else []
        normalized_rows = [row for row in rows if isinstance(row, dict)]

        dataset_id = request.dataset_id or deterministic_dataset_id(analysis_id, request.node_id)
        dataset = self._ensure_dataset(
            principal=principal,
            project_id=request.project_id,
            workspace_id=request.workspace_id,
            dataset_id=dataset_id,
            slug=request.dataset_slug or slugify(f"analysis-{analysis_id}-{request.node_id}"),
            name=request.dataset_name or f"{node.get('title') or request.node_id} · {analysis_id}",
        )
        source_version = (
            f"analysis:{analysis_id}:v{full_run.analysis_version}:"
            f"run:{full_run.id}:node:{request.node_id}"
        )
        artifact_path = self._artifact_path(
            project_id=request.project_id,
            dataset_id=dataset.id,
            analysis_version=full_run.analysis_version,
            run_id=full_run.id,
            node_id=request.node_id,
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        materialization_format = "parquet"
        media_type = "application/vnd.apache.parquet"
        temporary_path = artifact_path.with_suffix(".parquet.tmp")
        try:
            self.parquet_writer(normalized_rows, temporary_path)
        except RuntimeError as error:
            if "pyarrow" not in str(error).lower() and "parquet" not in str(error).lower():
                raise
            temporary_path.unlink(missing_ok=True)
            artifact_path = artifact_path.with_suffix(".jsonl")
            temporary_path = artifact_path.with_suffix(".jsonl.tmp")
            write_jsonl(normalized_rows, temporary_path)
            materialization_format = "jsonl"
            media_type = "application/x-ndjson"
        if not temporary_path.exists() or temporary_path.stat().st_size <= 0:
            raise RuntimeError(f"{materialization_format} writer did not create a non-empty artifact")
        temporary_path.replace(artifact_path)
        checksum = sha256_file(artifact_path)
        schema = infer_schema(node, normalized_rows)
        schema["format"] = materialization_format
        profile = {
            **(node.get("profile") if isinstance(node.get("profile"), dict) else {}),
            "analysis_id": analysis_id,
            "analysis_version": full_run.analysis_version,
            "analysis_run_id": full_run.id,
            "analysis_node_id": request.node_id,
            "preview_row_count": int(preview_node.get("row_count") or len(preview_node.get("rows") or [])),
            "materialized_row_count": len(normalized_rows),
            "materialization_format": materialization_format,
            "source_freshness_at": node.get("source_freshness_at"),
            "generated_at": node.get("generated_at"),
            "warnings": node.get("warnings") if isinstance(node.get("warnings"), list) else [],
        }
        version = self.datasets.create_version(
            principal=principal,
            project_id=request.project_id,
            dataset_id=dataset.id,
            request=DatasetVersionCreateRequest(
                source_version=source_version,
                version_label=f"analysis-v{full_run.analysis_version}-{full_run.id[-8:]}",
                checksum_sha256=checksum,
                schema=schema,
                profile=profile,
                record_count=len(normalized_rows),
                files=[
                    DatasetFileCreate(
                        uri=artifact_path.as_uri(),
                        media_type=media_type,
                        checksum_sha256=checksum,
                        size_bytes=artifact_path.stat().st_size,
                    )
                ],
            ),
        )
        materialization = self.datasets.create_materialization(
            principal=principal,
            project_id=request.project_id,
            dataset_id=dataset.id,
            version_id=version.id,
            request=MaterializationCreateRequest(
                source_kind="analysis_result",
                source_reference=source_version,
                format=materialization_format,
                artifact_uri=artifact_path.as_uri(),
                checksum_sha256=checksum,
                record_count=len(normalized_rows),
                metadata={
                    "analysis_id": analysis_id,
                    "analysis_version": full_run.analysis_version,
                    "analysis_run_id": full_run.id,
                    "analysis_node_id": request.node_id,
                    "preview_run_id": preview.id,
                    "downstream_dataset_version_id": version.id,
                },
            ),
        )
        return AnalysisMaterializationResult(
            dataset=dataset,
            version=version,
            materialization=materialization,
            analysis_run_id=full_run.id,
            analysis_id=analysis_id,
            analysis_version=full_run.analysis_version,
            node_id=request.node_id,
            preview_row_count=int(preview_node.get("row_count") or len(preview_node.get("rows") or [])),
            materialized_row_count=len(normalized_rows),
            checksum_sha256=checksum,
            artifact_uri=artifact_path.as_uri(),
        )

    def _ensure_dataset(
        self,
        *,
        principal: Principal,
        project_id: str,
        workspace_id: str,
        dataset_id: str,
        slug: str,
        name: str,
    ) -> DatasetRecord:
        existing = self.datasets.list_datasets(principal=principal, project_id=project_id)
        matched = next((item for item in existing if item.id == dataset_id), None)
        if matched is not None:
            if matched.workspace_id != workspace_id:
                raise ValueError("existing materialization dataset belongs to another workspace")
            return matched
        return self.datasets.create_dataset(
            principal=principal,
            request=DatasetCreateRequest(
                id=dataset_id,
                project_id=project_id,
                workspace_id=workspace_id,
                slug=slug,
                display_name=name,
                description="Reusable full materialization of an Analysis result node.",
                source_type="analysis_result",
            ),
        )

    def _artifact_path(
        self,
        *,
        project_id: str,
        dataset_id: str,
        analysis_version: int,
        run_id: str,
        node_id: str,
    ) -> Path:
        safe_node = slugify(node_id)
        return (
            self.artifact_root
            / slugify(project_id)
            / slugify(dataset_id)
            / f"analysis-v{analysis_version}-{run_id}-{safe_node}.parquet"
        )


def write_parquet(rows: list[dict[str, Any]], path: Path) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError(
            "Parquet materialization requires the polyglot/production extra (pyarrow)."
        ) from error
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path, compression="zstd", use_dictionary=True)


def write_jsonl(rows: list[dict[str, Any]], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deterministic_dataset_id(analysis_id: str, node_id: str) -> str:
    digest = hashlib.sha256(f"{analysis_id}:{node_id}".encode("utf-8")).hexdigest()[:20]
    return f"ds-analysis-{digest}"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = slug[:120].rstrip("-")
    return slug if len(slug) >= 3 else f"dataset-{hashlib.sha256(value.encode()).hexdigest()[:12]}"


def infer_schema(node: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    columns = node.get("columns") if isinstance(node.get("columns"), list) else []
    if columns:
        return {"format": "parquet", "fields": columns}
    keys = list(dict.fromkeys(key for row in rows[:100] for key in row))
    fields = []
    for key in keys:
        value = next((row.get(key) for row in rows if row.get(key) is not None), None)
        fields.append({"name": key, "type": type(value).__name__ if value is not None else "unknown"})
    return {"format": "parquet", "fields": fields}


__all__ = [
    "AnalysisDatasetMaterializer",
    "AnalysisMaterializationRequest",
    "AnalysisMaterializationResult",
    "deterministic_dataset_id",
    "infer_schema",
    "sha256_file",
    "slugify",
    "write_jsonl",
    "write_parquet",
]

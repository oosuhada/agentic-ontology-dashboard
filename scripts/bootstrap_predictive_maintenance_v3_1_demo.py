#!/usr/bin/env python3
"""Idempotently validate, ingest, materialize, activate, and verify the V3.1 demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


DATASET_NAME = (
    "UCI AI4I 2020 Manufacturing Predictive Maintenance — "
    "Physics & Maintenance Canonical V3.1"
)
SOURCE_VERSION = "canonical-ai4i-physics-v3.1"
MODEL_VERSION = "independent-logreg-v3.1"
RESULT_SCHEMA = "result-artifact-v1.0"
PREDICTION_TASK = "binary_failure_within_horizon"
MANIFEST_ID = "predictive-maintenance-canonical-v3-1"


def run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{detail}")


def verify_zip(package_root: Path) -> str:
    archive = package_root / "dist" / "predictive_maintenance_canonical_v3.1.zip"
    checksum_file = archive.with_suffix(archive.suffix + ".sha256")
    if not archive.is_file() or not checksum_file.is_file():
        raise FileNotFoundError("V3.1 distribution ZIP or SHA256 sidecar is missing")
    expected = checksum_file.read_text(encoding="utf-8").split()[0].strip().lower()
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError(f"V3.1 ZIP checksum mismatch: expected {expected}, got {actual}")
    return actual


def validate_package(root: Path, package_root: Path) -> dict[str, Any]:
    manifest_path = package_root / "canonical" / "dataset" / "dataset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_contract_path = package_root / "canonical" / "model_outputs" / "model_contract.json"
    model_contract = json.loads(model_contract_path.read_text(encoding="utf-8"))
    source_version = str(manifest.get("source_version") or manifest.get("dataset", {}).get("source_version") or "")
    rendered = json.dumps({"manifest": manifest, "model_contract": model_contract}, ensure_ascii=False)
    for expected in (SOURCE_VERSION, MODEL_VERSION, RESULT_SCHEMA, PREDICTION_TASK):
        if expected not in rendered:
            raise ValueError(f"dataset_manifest.json does not declare {expected}")
    if source_version and source_version != SOURCE_VERSION:
        raise ValueError(f"unexpected source version: {source_version}")
    with tempfile.TemporaryDirectory(prefix="pm-v3.1-release-") as temp_dir:
        output = Path(temp_dir) / "release.json"
        run([
            sys.executable,
            str(root / "scripts" / "verify_predictive_maintenance_v3_1_release.py"),
            "--root",
            str(root),
            "--package-root",
            str(package_root),
            "--run-package-validator",
            "--output",
            str(output),
        ])
        release = json.loads(output.read_text(encoding="utf-8"))
    return {"manifest": manifest, "model_contract": model_contract, "release": release}


def scoped_connection(database_url: str, organization_id: str, project_id: str):
    connection = psycopg.connect(database_url, row_factory=dict_row)
    connection.execute("SELECT set_config('app.organization_id', %s, false)", (organization_id,))
    connection.execute("SELECT set_config('app.project_id', %s, false)", (project_id,))
    return connection


def dataset_row(
    connection: psycopg.Connection[Any],
    organization_id: str,
    project_id: str,
    workspace_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT v.id AS dataset_version_id,v.dataset_id,v.source_version,
               v.checksum_sha256,v.record_count,v.status,v.profile_json,
               d.display_name AS dataset_name
        FROM dataset_versions v
        JOIN datasets d ON d.id=v.dataset_id
        WHERE v.organization_id=%s AND v.project_id=%s AND v.workspace_id=%s
          AND v.source_version=%s
        ORDER BY v.version_number DESC,v.created_at DESC
        LIMIT 1
        """,
        (organization_id, project_id, workspace_id, SOURCE_VERSION),
    ).fetchone()
    return None if row is None else dict(row)


def projection_status(connection: psycopg.Connection[Any], dataset_version_id: str) -> dict[str, Any]:
    rows = connection.execute(
        """
        SELECT store_kind,status,record_count,last_error,provider_run_id
        FROM store_projections WHERE dataset_version_id=%s
        """,
        (dataset_version_id,),
    ).fetchall()
    return {str(row["store_kind"]): dict(row) for row in rows}


def package_ingest(
    root: Path,
    package_root: Path,
    database_url: str,
    organization_id: str,
    project_id: str,
    workspace_id: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="pm-v3.1-ingest-") as temp_dir:
        temp = Path(temp_dir)
        run([
            sys.executable,
            str(root / "scripts" / "ingest_predictive_maintenance_bundle.py"),
            str(package_root),
            "--organization-id",
            organization_id,
            "--project-id",
            project_id,
            "--workspace-id",
            workspace_id,
            "--manifest-id",
            MANIFEST_ID,
            "--dataset-name",
            DATASET_NAME,
            "--allow-root",
            str(package_root),
            "--manifest-output",
            str(temp / "manifest.json"),
            "--output",
            str(temp / "validation.json"),
            "--ingestion-output",
            str(temp / "ingestion.json"),
            "--execute-postgresql",
            "--postgresql-dsn",
            database_url,
        ])


def materialize(
    root: Path,
    database_url: str,
    organization_id: str,
    project_id: str,
    workspace_id: str,
    dataset_id: str,
    dataset_version_id: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="pm-v3.1-materialize-") as temp_dir:
        run([
            sys.executable,
            str(root / "scripts" / "materialize_predictive_maintenance_ontology.py"),
            "--database-url",
            database_url,
            "--organization-id",
            organization_id,
            "--project-id",
            project_id,
            "--workspace-id",
            workspace_id,
            "--dataset-id",
            dataset_id,
            "--dataset-version-id",
            dataset_version_id,
            "--approve-default-mapping",
            "--approved-by",
            "predictive-maintenance-v3.1-demo-bootstrap",
            "--output",
            str(Path(temp_dir) / "materialization.json"),
        ])


def project_graph_if_available(
    root: Path,
    database_url: str,
    project3_url: str,
    organization_id: str,
    project_id: str,
    workspace_id: str,
    dataset_version_id: str,
) -> bool:
    try:
        with urllib.request.urlopen(f"{project3_url.rstrip('/')}/health", timeout=2) as response:
            if response.status >= 400:
                return False
    except (OSError, urllib.error.URLError):
        return False
    with tempfile.TemporaryDirectory(prefix="pm-v3.1-graph-") as temp_dir:
        run([
            sys.executable,
            str(root / "scripts" / "project_predictive_maintenance_graph.py"),
            "--database-url",
            database_url,
            "--project3-url",
            project3_url,
            "--organization-id",
            organization_id,
            "--project-id",
            project_id,
            "--workspace-id",
            workspace_id,
            "--dataset-version-id",
            dataset_version_id,
            "--output",
            str(Path(temp_dir) / "graph.json"),
        ])
    return True


def summarize(
    connection: psycopg.Connection[Any],
    row: dict[str, Any],
    *,
    activate: bool,
) -> dict[str, Any]:
    dataset_version_id = str(row["dataset_version_id"])
    counts = connection.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM pm_assets WHERE dataset_version_id=%s) AS asset_count,
          (SELECT COUNT(*) FROM pm_maintenance_events WHERE dataset_version_id=%s) AS maintenance_event_count,
          (SELECT COUNT(*) FROM pm_result_artifacts WHERE dataset_version_id=%s) AS result_artifact_count,
          (SELECT COUNT(*) FROM pm_prediction_timeline WHERE dataset_version_id=%s) AS prediction_timeline_count,
          (SELECT COUNT(*) FROM ontology_objects WHERE dataset_version_id=%s) AS ontology_object_count,
          (SELECT COUNT(*) FROM ontology_links WHERE dataset_version_id=%s) AS ontology_link_count,
          (SELECT model_version FROM pm_result_artifacts WHERE dataset_version_id=%s LIMIT 1) AS model_version,
          (SELECT schema_version FROM pm_result_artifacts WHERE dataset_version_id=%s LIMIT 1) AS result_schema,
          (SELECT prediction_task FROM pm_result_artifacts WHERE dataset_version_id=%s LIMIT 1) AS prediction_task
        """,
        (dataset_version_id,) * 9,
    ).fetchone()
    projections = projection_status(connection, dataset_version_id)
    ready = bool(
        counts["asset_count"]
        and counts["result_artifact_count"]
        and counts["prediction_timeline_count"]
        and counts["model_version"] == MODEL_VERSION
        and counts["result_schema"] == RESULT_SCHEMA
        and counts["prediction_task"] == PREDICTION_TASK
        and projections.get("relational", {}).get("status") == "ready"
    )
    if activate and ready and row["status"] != "published":
        connection.execute(
            "UPDATE dataset_versions SET status='published' WHERE id=%s",
            (dataset_version_id,),
        )
        row["status"] = "published"
    return {
        "dataset_id": str(row["dataset_id"]),
        "dataset_version_id": dataset_version_id,
        "source_version": str(row["source_version"]),
        "dataset_name": str(row["dataset_name"]),
        "model_version": counts["model_version"],
        "result_schema": counts["result_schema"],
        "prediction_task": counts["prediction_task"],
        "checksum": str(row["checksum_sha256"]),
        "record_count": int(row["record_count"]),
        "asset_count": int(counts["asset_count"]),
        "maintenance_event_count": int(counts["maintenance_event_count"]),
        "result_artifact_count": int(counts["result_artifact_count"]),
        "prediction_timeline_count": int(counts["prediction_timeline_count"]),
        "ontology_object_count": int(counts["ontology_object_count"]),
        "ontology_link_count": int(counts["ontology_link_count"]),
        "relational_projection_status": projections.get("relational", {}).get("status", "unavailable"),
        "graph_projection_status": projections.get("graph", {}).get("status", "unavailable"),
        "default_activation_status": (
            "canonical_v3_1_release_ready" if row["status"] == "published" and ready else "not_activated"
        ),
        "dataset_status": str(row["status"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-root", required=True)
    parser.add_argument("--organization-id", default="org-ontology-demo")
    parser.add_argument("--project-id", default="manufacturing-demo-project")
    parser.add_argument("--workspace-id", default="manufacturing-demo")
    parser.add_argument("--database-url", default=os.getenv("ONTOLOGY_DASHBOARD_DATABASE_URL"))
    parser.add_argument("--skip-graph", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--force-rematerialize", action="store_true")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url or ONTOLOGY_DASHBOARD_DATABASE_URL is required")

    root = Path(__file__).resolve().parents[1]
    package_root = Path(args.package_root).expanduser().resolve()
    zip_checksum = verify_zip(package_root)
    validation = validate_package(root, package_root)

    connection = scoped_connection(args.database_url, args.organization_id, args.project_id)
    try:
        row = dataset_row(connection, args.organization_id, args.project_id, args.workspace_id)
        if row is None and args.verify_only:
            raise RuntimeError("V3.1 Dataset Version is not ingested")
        if row is None:
            connection.close()
            package_ingest(
                root,
                package_root,
                args.database_url,
                args.organization_id,
                args.project_id,
                args.workspace_id,
            )
            connection = scoped_connection(args.database_url, args.organization_id, args.project_id)
            row = dataset_row(connection, args.organization_id, args.project_id, args.workspace_id)
            if row is None:
                raise RuntimeError("ingestion completed without a scoped V3.1 Dataset Version")

        projections = projection_status(connection, str(row["dataset_version_id"]))
        needs_materialization = (
            args.force_rematerialize
            or projections.get("relational", {}).get("status") != "ready"
        )
        if needs_materialization and not args.verify_only:
            connection.close()
            materialize(
                root,
                args.database_url,
                args.organization_id,
                args.project_id,
                args.workspace_id,
                str(row["dataset_id"]),
                str(row["dataset_version_id"]),
            )
            connection = scoped_connection(args.database_url, args.organization_id, args.project_id)
            row = dataset_row(connection, args.organization_id, args.project_id, args.workspace_id)

        graph_attempted = False
        if not args.skip_graph and not args.verify_only:
            connection.close()
            graph_attempted = project_graph_if_available(
                root,
                args.database_url,
                os.getenv("ONTOLOGY_DASHBOARD_PROJECT3_URL", "http://127.0.0.1:8001"),
                args.organization_id,
                args.project_id,
                args.workspace_id,
                str(row["dataset_version_id"]),
            )
            connection = scoped_connection(args.database_url, args.organization_id, args.project_id)
            row = dataset_row(connection, args.organization_id, args.project_id, args.workspace_id)

        summary = summarize(connection, row, activate=not args.verify_only)
        connection.commit()
        summary.update({
            "distribution_zip_checksum": zip_checksum,
            "package_validation_status": "pass",
            "release_verification": validation["release"].get("status", "pass"),
            "graph_projection_attempted": graph_attempted,
            "idempotent": True,
            "verify_only": args.verify_only,
        })
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        if summary["default_activation_status"] == "not_activated":
            return 2
        return 0
    finally:
        if not connection.closed:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())

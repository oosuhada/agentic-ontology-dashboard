#!/usr/bin/env python3
"""Ingest a checksum-pinned Dataset Manifest through the canonical File Adapter."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ontology_dashboard.adapters.file_adapter import FileAdapter
from ontology_dashboard.adapters.models import DatasetManifest
from ontology_dashboard.migrations import migrate
from ontology_dashboard.settings import database_location

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="Path to a Dataset Manifest JSON file")
    parser.add_argument(
        "--allow-root",
        action="append",
        dest="allow_roots",
        help="Allowed local dataset root. Repeat for multiple roots.",
    )
    parser.add_argument("--database", help="SQLite database path; defaults to runtime settings")
    parser.add_argument("--output", help="Optional JSON result artifact path")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve(strict=True)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = DatasetManifest.model_validate(payload)
    database = args.database or database_location(ROOT)
    if database.startswith(("postgresql://", "postgresql+psycopg://")):
        raise RuntimeError("File Adapter CLI currently requires the SQLite ingestion repository")
    migrate(database)

    configured_roots = [
        Path(value)
        for value in os.getenv("ONTOLOGY_DASHBOARD_DATA_ROOTS", "").split(os.pathsep)
        if value.strip()
    ]
    allowed_roots = [Path(value) for value in (args.allow_roots or [])]
    if not allowed_roots:
        allowed_roots = configured_roots or [manifest_path.parent, ROOT / "data" / "raw"]

    result = FileAdapter(database, allowed_roots=allowed_roots).ingest(manifest)
    rendered = json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

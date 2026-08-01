#!/usr/bin/env python3
"""Create a verified Ontology Dashboard SQLite or PostgreSQL backup artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ontology_dashboard.settings import database_location

ROOT = Path(__file__).resolve().parents[1]


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_backup(source: Path, output: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    output.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_connection, sqlite3.connect(output) as target_connection:
        source_connection.backup(target_connection)
        row = target_connection.execute("PRAGMA integrity_check").fetchone()
        if row is None or row[0] != "ok":
            raise RuntimeError(f"backup integrity check failed: {row}")


def postgres_backup(database_url: str, output: Path) -> None:
    pg_dump = shutil.which("pg_dump")
    if pg_dump is None:
        raise RuntimeError("pg_dump is required for PostgreSQL backups")
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            pg_dump,
            "--format=custom",
            "--no-owner",
            "--no-privileges",
            f"--file={output}",
            database_url,
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", help="Database URL/path; defaults to runtime settings")
    parser.add_argument("--output", required=True, help="Backup artifact path")
    args = parser.parse_args()

    database = args.database or database_location(ROOT)
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"backup output already exists: {output}")

    if database.startswith(("postgresql://", "postgresql+psycopg://")):
        backend = "postgresql"
        postgres_backup(database, output)
    else:
        backend = "sqlite"
        sqlite_backup(Path(database).expanduser().resolve(), output)

    metadata = {
        "artifact": str(output),
        "backend": backend,
        "sha256": checksum(output),
        "size_bytes": output.stat().st_size,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path = output.with_suffix(output.suffix + ".manifest.json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**metadata, "manifest": str(metadata_path)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

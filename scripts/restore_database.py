#!/usr/bin/env python3
"""Restore a verified Ontology Dashboard backup after explicit target confirmation."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

from ontology_dashboard.settings import database_location

ROOT = Path(__file__).resolve().parents[1]


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(backup: Path) -> dict[str, object]:
    manifest_path = backup.with_suffix(backup.suffix + ".manifest.json")
    if not manifest_path.exists():
        raise FileNotFoundError(f"backup manifest is missing: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = checksum(backup)
    if payload.get("sha256") != actual:
        raise RuntimeError("backup checksum does not match its manifest")
    return payload


def restore_sqlite(backup: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(backup) as source_connection:
        row = source_connection.execute("PRAGMA integrity_check").fetchone()
        if row is None or row[0] != "ok":
            raise RuntimeError(f"source backup integrity check failed: {row}")
        with sqlite3.connect(target) as target_connection:
            source_connection.backup(target_connection)
            restored = target_connection.execute("PRAGMA integrity_check").fetchone()
            if restored is None or restored[0] != "ok":
                raise RuntimeError(f"restored database integrity check failed: {restored}")


def restore_postgres(backup: Path, database_url: str) -> None:
    pg_restore = shutil.which("pg_restore")
    if pg_restore is None:
        raise RuntimeError("pg_restore is required for PostgreSQL restore")
    subprocess.run(
        [
            pg_restore,
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            f"--dbname={database_url}",
            str(backup),
        ],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", help="Backup artifact path")
    parser.add_argument("--database", help="Restore target URL/path; defaults to runtime settings")
    parser.add_argument(
        "--confirm-target",
        required=True,
        help="Must exactly match the resolved database URL/path",
    )
    args = parser.parse_args()

    backup = Path(args.backup).expanduser().resolve(strict=True)
    database = args.database or database_location(ROOT)
    if args.confirm_target != database:
        raise RuntimeError("--confirm-target must exactly match the restore target")
    manifest = verify_manifest(backup)

    if database.startswith(("postgresql://", "postgresql+psycopg://")):
        if manifest.get("backend") != "postgresql":
            raise RuntimeError("cannot restore a non-PostgreSQL artifact into PostgreSQL")
        restore_postgres(backup, database)
    else:
        if manifest.get("backend") != "sqlite":
            raise RuntimeError("cannot restore a non-SQLite artifact into SQLite")
        restore_sqlite(backup, Path(database).expanduser().resolve())

    print(
        json.dumps(
            {
                "restored": True,
                "backend": manifest.get("backend"),
                "target": database,
                "backup_sha256": manifest.get("sha256"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PREFIX = re.compile(r"^(\d{4})_.*\.sql$")


def test_backend_migration_number_prefixes_are_unique_per_dialect() -> None:
    duplicate_prefixes: dict[str, list[str]] = {}
    for dialect_dir in (ROOT / "systems" / "backend" / "migrations").iterdir():
        if not dialect_dir.is_dir():
            continue
        by_prefix: dict[str, list[str]] = defaultdict(list)
        for path in sorted(dialect_dir.glob("*.sql")):
            match = MIGRATION_PREFIX.match(path.name)
            assert match is not None, f"{path} must start with a four-digit migration prefix"
            by_prefix[match.group(1)].append(path.name)
        duplicates = [
            f"{prefix}: {', '.join(names)}"
            for prefix, names in sorted(by_prefix.items())
            if len(names) > 1
        ]
        if duplicates:
            duplicate_prefixes[dialect_dir.name] = duplicates

    assert duplicate_prefixes == {}

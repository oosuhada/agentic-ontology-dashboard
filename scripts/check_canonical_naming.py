#!/usr/bin/env python3
"""Reject new user-facing or runtime dependencies on deprecated product names."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEXT_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml",
    ".toml", ".md", ".sh", ".html", ".css", ".txt",
}

SCAN_PATHS = (
    ROOT / "README.md",
    ROOT / "systems" / "backend" / "README.md",
    ROOT / "systems" / "backend" / "ontology_dashboard",
    ROOT / "systems" / "frontend" / "src",
    ROOT / "contracts" / "schemas",
    ROOT / "infra",
    ROOT / ".github" / "workflows",
    ROOT / "evaluation",
    ROOT / "scripts",
)

RULES = (
    ("legacy_display_name", re.compile(r"Factory Signal Board", re.IGNORECASE)),
    ("legacy_schema_host", re.compile(r"factory-signal-board\.local", re.IGNORECASE)),
    ("legacy_ci_name", re.compile(r"factory-signal-board-ci", re.IGNORECASE)),
    ("legacy_runtime_import", re.compile(r"^(?:from|import)\s+factory_signal_board\b", re.MULTILINE)),
    ("legacy_ml_import", re.compile(r"^(?:from|import)\s+factory_signal_ml\b", re.MULTILINE)),
)

# Migration compatibility is intentionally isolated to these files. The checker
# itself contains the deprecated tokens so it must be excluded from self-scan.
EXCLUDED_FILES = {
    ROOT / "scripts" / "check_canonical_naming.py",
}


def iter_files(path: Path):
    if path.is_file():
        yield path
        return
    if not path.exists():
        return
    for candidate in path.rglob("*"):
        if not candidate.is_file() or candidate.suffix not in TEXT_EXTENSIONS:
            continue
        if any(part in {"node_modules", "dist", "__pycache__"} for part in candidate.parts):
            continue
        yield candidate


def main() -> int:
    violations: list[dict[str, object]] = []
    checked = 0
    for scan_path in SCAN_PATHS:
        for file_path in iter_files(scan_path):
            if file_path in EXCLUDED_FILES:
                continue
            checked += 1
            text = file_path.read_text(encoding="utf-8")
            for rule_name, pattern in RULES:
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    violations.append(
                        {
                            "rule": rule_name,
                            "path": str(file_path.relative_to(ROOT)),
                            "line": line,
                            "match": match.group(0),
                        }
                    )

    payload = {
        "check": "ontology-dashboard-canonical-naming",
        "checked_files": checked,
        "violations": violations,
        "pass": not violations,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not violations else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Validate committed visual review artifacts against their manifest."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_ROOT = ROOT / "docs" / "ui" / "screenshots" / "palantir-gap-v2"
MANIFEST_PATH = BASELINE_ROOT / "baseline-manifest.json"


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        signature = stream.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            raise ValueError(f"not a PNG: {path}")
        length = struct.unpack(">I", stream.read(4))[0]
        chunk = stream.read(4)
        if chunk != b"IHDR" or length < 8:
            raise ValueError(f"missing PNG IHDR: {path}")
        width, height = struct.unpack(">II", stream.read(8))
        return width, height


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    results: list[dict[str, object]] = []

    for filename, expected in sorted(manifest["artifacts"].items()):
        path = BASELINE_ROOT / filename
        if not path.is_file():
            failures.append(f"missing artifact: {filename}")
            continue
        width, height = png_dimensions(path)
        size = path.stat().st_size
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        actual = {
            "filename": filename,
            "width": width,
            "height": height,
            "bytes": size,
            "sha256": digest,
        }
        results.append(actual)
        for key in ("width", "height", "bytes", "sha256"):
            if actual[key] != expected[key]:
                failures.append(
                    f"{filename} {key}: expected {expected[key]!r}, got {actual[key]!r}"
                )

    required_support = ["README.md", "comparison.html"]
    for filename in required_support:
        if not (BASELINE_ROOT / filename).is_file():
            failures.append(f"missing visual review support file: {filename}")

    payload = {
        "check": "ontology-dashboard-visual-baselines",
        "manifest": str(MANIFEST_PATH.relative_to(ROOT)),
        "artifacts": results,
        "failures": failures,
        "pass": not failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

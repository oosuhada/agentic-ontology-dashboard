#!/usr/bin/env python3
"""Regenerate the six-image Palantir gap-review manifest after visual approval."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from check_visual_baselines import BASELINE_ROOT, MANIFEST_PATH, png_dimensions


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    artifacts: dict[str, dict[str, object]] = {}

    for filename in sorted(manifest["artifacts"]):
        path = BASELINE_ROOT / filename
        width, height = png_dimensions(path)
        artifacts[filename] = {
            "width": width,
            "height": height,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    manifest["generated_at"] = date.today().isoformat()
    manifest["artifacts"] = artifacts
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "manifest": str(MANIFEST_PATH),
                "artifacts": len(artifacts),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Regenerate the approved Palantir-overhaul visual manifest after an intentional review."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from check_palantir_overhaul_visuals import (
    EVIDENCE_ROOT,
    MANIFEST_PATH,
    image_delta,
    image_metadata,
)


def main() -> int:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    artifacts: dict[str, object] = {}
    pairs: dict[str, object] = {}

    for stage in ("baseline", "final"):
        stage_root = EVIDENCE_ROOT / stage
        for path in sorted(stage_root.glob("*/*.png")):
            relative_path = path.relative_to(EVIDENCE_ROOT).as_posix()
            artifacts[relative_path] = image_metadata(path)

    final_root = EVIDENCE_ROOT / "final"
    for final_path in sorted(final_root.glob("*/*.png")):
        relative_path = final_path.relative_to(final_root).as_posix()
        baseline_path = EVIDENCE_ROOT / "baseline" / relative_path
        mean_delta, changed_delta, structural_delta = image_delta(baseline_path, final_path)
        pairs[relative_path] = {
            "mean_pixel_delta_percent": round(mean_delta, 4),
            "changed_pixel_percent": round(changed_delta, 4),
            "structural_mean_pixel_delta_percent": round(structural_delta, 4),
        }

    manifest["generated_at"] = date.today().isoformat()
    manifest["description"] = (
        "Approved 48-image baseline/final set for the Palantir-inspired UI overhaul "
        "and Foundry shell plus workbench-precision convergence pass."
    )
    manifest["thresholds"]["baseline_final_mean_pixel_delta_percent_max"] = 50.0
    manifest["artifacts"] = artifacts
    manifest["pairs"] = pairs
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "manifest": str(MANIFEST_PATH.relative_to(Path(__file__).resolve().parents[1])),
                "artifacts": len(artifacts),
                "pairs": len(pairs),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

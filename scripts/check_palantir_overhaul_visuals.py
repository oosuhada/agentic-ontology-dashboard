#!/usr/bin/env python3
"""Validate the committed 48-image overhaul set and optional Playwright candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageFilter, ImageStat

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "docs" / "ui" / "palantir-overhaul"
MANIFEST_PATH = EVIDENCE_ROOT / "visual-manifest.json"
DEFAULT_CANDIDATE_ROOT = ROOT / "web" / "test-results" / "palantir-overhaul-candidate"


def image_metadata(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
    return {
        "width": width,
        "height": height,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def image_delta(reference: Path, candidate: Path) -> tuple[float, float, float]:
    with Image.open(reference) as ref_image, Image.open(candidate) as candidate_image:
        reference_rgb = ref_image.convert("RGB")
        candidate_rgb = candidate_image.convert("RGB")
        if reference_rgb.size != candidate_rgb.size:
            raise ValueError(
                f"dimension mismatch: {reference}={reference_rgb.size}, "
                f"{candidate}={candidate_rgb.size}"
            )
        difference = ImageChops.difference(reference_rgb, candidate_rgb)
        mean_percent = sum(ImageStat.Stat(difference).mean) / (3 * 255) * 100
        pixels = (
            difference.get_flattened_data()
            if hasattr(difference, "get_flattened_data")
            else difference.getdata()
        )
        changed_pixels = sum(1 for pixel in pixels if pixel != (0, 0, 0))
        changed_percent = changed_pixels / (reference_rgb.width * reference_rgb.height) * 100
        reference_structure = reference_rgb.convert("L").resize((180, 125)).filter(ImageFilter.GaussianBlur(1.5))
        candidate_structure = candidate_rgb.convert("L").resize((180, 125)).filter(ImageFilter.GaussianBlur(1.5))
        structural_difference = ImageChops.difference(reference_structure, candidate_structure)
        structural_mean_percent = ImageStat.Stat(structural_difference).mean[0] / 255 * 100
    return mean_percent, changed_percent, structural_mean_percent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--require-candidate", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    artifact_results: list[dict[str, Any]] = []
    pair_results: list[dict[str, Any]] = []
    candidate_results: list[dict[str, Any]] = []

    for relative_path, expected in sorted(manifest["artifacts"].items()):
        path = EVIDENCE_ROOT / relative_path
        if not path.is_file():
            failures.append(f"missing artifact: {relative_path}")
            continue
        actual = image_metadata(path)
        artifact_results.append({"path": relative_path, **actual})
        for key in ("width", "height", "bytes", "sha256"):
            if actual[key] != expected[key]:
                failures.append(
                    f"{relative_path} {key}: expected {expected[key]!r}, got {actual[key]!r}"
                )

    minimum_delta = float(manifest["thresholds"]["baseline_final_mean_pixel_delta_percent_min"])
    maximum_delta = float(manifest["thresholds"]["baseline_final_mean_pixel_delta_percent_max"])
    for relative_path, expected in sorted(manifest["pairs"].items()):
        baseline = EVIDENCE_ROOT / "baseline" / relative_path
        final = EVIDENCE_ROOT / "final" / relative_path
        if not baseline.is_file() or not final.is_file():
            failures.append(f"missing baseline/final pair: {relative_path}")
            continue
        mean_delta, changed_delta, structural_delta = image_delta(baseline, final)
        pair_results.append({
            "path": relative_path,
            "mean_pixel_delta_percent": round(mean_delta, 4),
            "changed_pixel_percent": round(changed_delta, 4),
            "structural_mean_pixel_delta_percent": round(structural_delta, 4),
        })
        if not minimum_delta <= mean_delta <= maximum_delta:
            failures.append(
                f"{relative_path} baseline/final mean delta {mean_delta:.4f}% "
                f"outside [{minimum_delta:.4f}, {maximum_delta:.4f}]"
            )
        if abs(mean_delta - float(expected["mean_pixel_delta_percent"])) > 0.0002:
            failures.append(
                f"{relative_path} baseline/final mean delta changed: "
                f"expected {expected['mean_pixel_delta_percent']}, got {mean_delta:.4f}"
            )

    candidate_requested = args.candidate_root is not None or args.require_candidate
    candidate_root = args.candidate_root.resolve() if args.candidate_root else DEFAULT_CANDIDATE_ROOT
    candidate_available = candidate_requested and candidate_root.is_dir()
    if args.require_candidate and not candidate_available:
        failures.append(f"candidate root is required but missing: {candidate_root}")

    capture_platform = str(manifest.get("capture_platform", "darwin"))
    current_platform = sys.platform
    same_platform = current_platform == capture_platform

    if candidate_available:
        mean_limit = float(manifest["thresholds"]["candidate_mean_pixel_delta_percent_max"])
        changed_limit = float(manifest["thresholds"]["candidate_changed_pixel_percent_max"])
        structural_limit = float(
            manifest["thresholds"][
                "candidate_structural_mean_pixel_delta_percent_max_same_platform"
                if same_platform
                else "candidate_structural_mean_pixel_delta_percent_max_cross_platform"
            ]
        )
        for relative_path in sorted(manifest["pairs"]):
            approved = EVIDENCE_ROOT / "final" / relative_path
            candidate = candidate_root / relative_path
            if not candidate.is_file():
                failures.append(f"missing candidate: {relative_path}")
                continue
            try:
                mean_delta, changed_delta, structural_delta = image_delta(approved, candidate)
            except ValueError as error:
                failures.append(str(error))
                continue
            candidate_results.append({
                "path": relative_path,
                "mean_pixel_delta_percent": round(mean_delta, 4),
                "changed_pixel_percent": round(changed_delta, 4),
                "structural_mean_pixel_delta_percent": round(structural_delta, 4),
            })
            if structural_delta > structural_limit:
                failures.append(
                    f"{relative_path} candidate structural delta {structural_delta:.4f}% "
                    f"exceeds {structural_limit:.4f}% for {current_platform}"
                )
            if same_platform and mean_delta > mean_limit:
                failures.append(
                    f"{relative_path} candidate mean delta {mean_delta:.4f}% exceeds {mean_limit:.4f}%"
                )
            if same_platform and changed_delta > changed_limit:
                failures.append(
                    f"{relative_path} candidate changed pixels {changed_delta:.4f}% exceeds {changed_limit:.4f}%"
                )

    payload = {
        "check": "palantir-overhaul-48-image-visual-regression",
        "manifest": str(MANIFEST_PATH.relative_to(ROOT)),
        "artifact_count": len(artifact_results),
        "pair_count": len(pair_results),
        "candidate_root": str(candidate_root) if candidate_requested else None,
        "candidate_available": candidate_available,
        "candidate_count": len(candidate_results),
        "capture_platform": capture_platform,
        "current_platform": current_platform,
        "same_platform_raw_pixel_gate": same_platform,
        "thresholds": manifest["thresholds"],
        "max_candidate_mean_pixel_delta_percent": max(
            (item["mean_pixel_delta_percent"] for item in candidate_results), default=None
        ),
        "max_candidate_changed_pixel_percent": max(
            (item["changed_pixel_percent"] for item in candidate_results), default=None
        ),
        "max_candidate_structural_mean_pixel_delta_percent": max(
            (item["structural_mean_pixel_delta_percent"] for item in candidate_results), default=None
        ),
        "failures": failures,
        "pass": not failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

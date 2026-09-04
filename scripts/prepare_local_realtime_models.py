"""Prepare the frozen Canonical V3.1 models for the local real-time runtime.

The launcher must not select a new algorithm or promote the newest local
candidate.  It reconstructs the approved ``independent-logreg-v3.1`` artifacts
from the immutable Canonical package when absent, verifies their lineage, and
pins exactly those versions in the active model set.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY_MODEL_VERSION = "independent-logreg-v3.1"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _manifest_candidates(models_store: Path, model_id: str) -> list[dict]:
    root = models_store / "artifacts" / model_id
    candidates: list[dict] = []
    if not root.exists():
        return candidates
    for manifest_path in root.glob("*/manifest.json"):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("model_id") == model_id and payload.get("model_version"):
            payload["_artifact_dir"] = str(manifest_path.parent)
            candidates.append(payload)
    return sorted(
        candidates,
        key=lambda item: (str(item.get("created_at") or ""), str(item["model_version"])),
    )


def _publish(command: str, *, gen_data_root: Path, models_store: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT),
            "DATA_DIR": str((gen_data_root / "canonical" / "dataset").resolve()),
            "MODELS_STORE_DIR": str(models_store.resolve()),
            "MODEL_ARTIFACT_URI": str((models_store / "artifacts").resolve()),
            "GENERATOR_TRAINING_N_JOBS": env.get("GENERATOR_TRAINING_N_JOBS", "-1"),
        }
    )
    subprocess.run(
        [sys.executable, "-m", "systems.generator.entrypoint", command],
        cwd=ROOT,
        env=env,
        check=True,
    )


def prepare(*, gen_data_root: Path, models_store: Path, force: bool = False) -> dict:
    os.environ["MODELS_STORE_DIR"] = str(models_store.resolve())
    from systems.generator.model.publisher import (
        ModelArtifactContractValidationError,
        validate_model_artifact,
    )

    def valid_candidates(model_id: str) -> list[dict]:
        result: list[dict] = []
        for candidate in _manifest_candidates(models_store, model_id):
            try:
                validate_model_artifact(
                    artifact_dir=Path(candidate["_artifact_dir"]),
                    expected_model_id=model_id,
                    expected_model_version=str(candidate["model_version"]),
                    load_model=True,
                    artifacts_root=models_store / "artifacts",
                )
            except ModelArtifactContractValidationError:
                continue
            result.append(candidate)
        return result

    required = ("compressor-failure-risk", "cnc-failure-risk")

    def pinned_candidate(model_id: str) -> dict | None:
        for candidate in valid_candidates(model_id):
            if candidate.get("model_version") != LEGACY_MODEL_VERSION:
                continue
            training_config = candidate.get("training_config") or {}
            provenance = candidate.get("provenance") or {}
            if (
                training_config.get("training_config_version")
                != "independent-logreg-v3.1-frozen-reconstruction-v1"
                or float(training_config.get("selected_threshold", -1.0)) != 0.50
                or provenance.get("reconstruction")
                != "deterministic_from_frozen_v3.1_recipe"
            ):
                raise RuntimeError(
                    f"pinned legacy artifact has incompatible lineage: "
                    f"{model_id}/{LEGACY_MODEL_VERSION}"
                )
            return candidate
        return None

    # ``force`` re-runs validation but never replaces an immutable artifact.
    # It is retained for CLI compatibility with earlier PR #160 invocations.
    pinned = {model_id: pinned_candidate(model_id) for model_id in required}
    if force or any(candidate is None for candidate in pinned.values()):
        print(
            f"[models] reconstructing frozen {LEGACY_MODEL_VERSION} artifacts "
            f"from {gen_data_root}",
            flush=True,
        )
        _publish(
            "reconstruct-publish-v3-1",
            gen_data_root=gen_data_root,
            models_store=models_store,
        )
        pinned = {model_id: pinned_candidate(model_id) for model_id in required}

    missing = [model_id for model_id, candidate in pinned.items() if candidate is None]
    if missing:
        raise RuntimeError(
            "legacy V3.1 publication produced no valid pinned artifact: "
            + ", ".join(missing)
        )
    selected = {
        model_id: {"model_version": LEGACY_MODEL_VERSION, "required": True}
        for model_id in required
    }

    from systems.generator.app.runtime_pipeline.active_model_set_service import (
        ActiveModelSetService,
    )
    from systems.generator.app.runtime_pipeline.pipeline_schema import ActiveModelSet

    model_set = ActiveModelSet(
        model_set_id="pdm-local-realtime",
        model_set_version="3.1.0-independent-logreg-pinned",
        updated_at=datetime.now(timezone.utc),
        models=selected,
    )
    published = ActiveModelSetService(models_store_dir=models_store).update_active_model_set(
        model_set,
        validate_artifacts=True,
    )
    return published.model_dump(mode="json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gen-data-root",
        type=Path,
        default=ROOT.parent / "gen_data",
    )
    parser.add_argument(
        "--models-store",
        type=Path,
        default=ROOT / "models_store" / "local-realtime",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    payload = prepare(
        gen_data_root=args.gen_data_root.resolve(),
        models_store=args.models_store.resolve(),
        force=args.force,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

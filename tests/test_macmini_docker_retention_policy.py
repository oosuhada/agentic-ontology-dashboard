from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_ephemeral_runtime_paths_do_not_create_docker_volume_leaks() -> None:
    compose_path = ROOT / "infra" / "macmini" / "docker-compose.yml"
    config = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    assert config["services"]["redis"]["tmpfs"] == ["/data:size=64m,mode=1777"]
    assert config["services"]["neo4j"]["tmpfs"] == ["/tmp:size=256m,mode=1777"]


def test_macmini_deploy_reuses_sha_images_on_retry() -> None:
    backend = (ROOT / "scripts" / "deploy_macmini_backend.sh").read_text(
        encoding="utf-8"
    )
    frontend = (ROOT / "scripts" / "deploy_macmini_frontend.sh").read_text(
        encoding="utf-8"
    )
    graph = (ROOT / "scripts" / "deploy_macmini_graph.sh").read_text(
        encoding="utf-8"
    )

    assert 'docker image inspect "$TARGET_IMAGE"' in backend
    assert 'Reusing existing backend image $TARGET_IMAGE' in backend
    assert 'docker image inspect "$TARGET_GENERATOR_IMAGE"' in backend
    assert "no reusable image exists; rebuilding" in backend
    assert 'docker image inspect "$TARGET_IMAGE"' in frontend
    assert 'Reusing existing frontend image $TARGET_IMAGE' in frontend
    assert 'docker image inspect "$PROJECT3_IMAGE"' in graph
    assert 'Reusing existing Project 3 image $PROJECT3_IMAGE' in graph


def test_release_watcher_has_failure_backoff_disk_gate_and_artifact_retention() -> None:
    watcher = (ROOT / "scripts" / "macmini_release_watcher.sh").read_text(
        encoding="utf-8"
    )
    pruner = (ROOT / "scripts" / "prune_macmini_docker_artifacts.sh").read_text(
        encoding="utf-8"
    )

    assert 'ONTOLOGY_RELEASE_RETRY_SECONDS:-900' in watcher
    assert 'ONTOLOGY_RELEASE_MIN_FREE_GB:-20' in watcher
    assert "last-deploy-failure" in watcher
    assert "df -Pk /System/Volumes/Data" in watcher
    assert "prune_macmini_docker_artifacts.sh" in watcher

    assert "ontology-dashboard-macmini-backend" in pruner
    assert "ontology-dashboard-macmini-frontend" in pruner
    assert "ontology-dashboard-macmini-generator-runtime" in pruner
    assert "ontology-dashboard-macmini-project3" in pruner
    assert 'docker builder prune -f --filter "until=$BUILD_CACHE_MAX_AGE"' in pruner
    assert "docker volume prune" not in pruner

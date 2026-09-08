from __future__ import annotations

from pathlib import Path

import yaml

from app.knowledge import worker as knowledge_worker


ROOT = Path(__file__).resolve().parents[1]


def test_macmini_background_services_are_not_restart_daemons() -> None:
    compose_path = ROOT / "infra" / "macmini" / "docker-compose.yml"
    compose = compose_path.read_text(encoding="utf-8")
    config = yaml.safe_load(compose)

    for service in ("generator-runtime", "live-ingestor", "knowledge-indexer"):
        assert config["services"][service]["restart"] == "no"

    assert "LIVE_PM_RUN_ONCE" in config["services"]["live-ingestor"]["environment"]
    assert config["services"]["knowledge-indexer"]["command"] == [
        "python",
        "-m",
        "app.knowledge.worker",
        "--once",
    ]


def test_backend_deploy_only_recreates_request_path_backend() -> None:
    script = (ROOT / "scripts" / "deploy_macmini_backend.sh").read_text(
        encoding="utf-8"
    )

    assert "up -d --no-deps --no-build backend\n" in script
    assert "backend live-ingestor knowledge-indexer" not in script
    assert "stop -t 20 live-ingestor knowledge-indexer generator-runtime" in script
    assert "rm -f -s live-ingestor knowledge-indexer generator-runtime" in script
    assert 'TARGET_GENERATOR_IMAGE="$GENERATOR_IMAGE_REPO:$TARGET_SHA"' in script
    assert 'docker tag "$current_backend_image_id" "$TARGET_IMAGE"' in script
    assert 'docker tag "$GENERATOR_IMAGE_REPO:latest" "$TARGET_GENERATOR_IMAGE"' in script


def test_background_refresh_wakes_drains_and_stops_generator() -> None:
    script = (ROOT / "scripts" / "run_macmini_background_refresh.sh").read_text(
        encoding="utf-8"
    )

    assert "up -d --no-deps --no-build generator-runtime" in script
    assert "LIVE_PM_RUN_ONCE=1" in script
    assert "prediction_delivery_status" in script
    assert "app.project3_refresh_current_projection" in script
    assert "compose run --rm --no-deps knowledge-indexer" in script
    assert "compose stop -t 20 generator-runtime" in script
    assert ".background-refresh-lock" in script


def test_background_refresh_launch_agent_defaults_to_ten_minutes() -> None:
    installer = (ROOT / "infra" / "macmini" / "install-background-refresh.sh").read_text(
        encoding="utf-8"
    )
    watcher = (ROOT / "scripts" / "macmini_release_watcher.sh").read_text(
        encoding="utf-8"
    )

    assert 'ONTOLOGY_MACMINI_BACKGROUND_REFRESH_SECONDS:-600' in installer
    assert "<key>RunAtLoad</key>\n  <false/>" in installer
    assert "<key>StartInterval</key>" in installer
    assert "ONTOLOGY_MACMINI_SOURCE_ROOT" in installer
    assert "install-background-refresh.sh" in watcher


def test_installed_background_runner_accepts_explicit_source_root() -> None:
    runner = (ROOT / "scripts" / "run_macmini_background_refresh.sh").read_text(
        encoding="utf-8"
    )

    assert "ONTOLOGY_MACMINI_SOURCE_ROOT" in runner
    assert "Ontology source root is invalid" in runner


def test_knowledge_worker_run_once_skips_clean_index(monkeypatch) -> None:
    class Repository:
        def index_state(self, **_scope):
            return {"status": "ready"}

    class Service:
        repository = Repository()

        def reindex(self, **_scope):  # pragma: no cover - must not run
            raise AssertionError("clean knowledge index must not be rebuilt")

    monkeypatch.setattr(
        knowledge_worker,
        "_scope",
        lambda: (Service(), "org-1", "project-1", "workspace-1"),
    )

    assert knowledge_worker.run_once() == {"status": "ready", "reindexed": False}


def test_knowledge_worker_run_once_reindexes_dirty_state(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class Repository:
        def index_state(self, **_scope):
            return {"status": "dirty"}

    class Service:
        repository = Repository()

        def reindex(self, **scope):
            calls.append(scope)
            return {"status": "ready", "chunk_count": 12}

    monkeypatch.setattr(
        knowledge_worker,
        "_scope",
        lambda: (Service(), "org-1", "project-1", "workspace-1"),
    )

    result = knowledge_worker.run_once()

    assert result == {"status": "ready", "chunk_count": 12, "reindexed": True}
    assert calls == [
        {
            "organization_id": "org-1",
            "project_id": "project-1",
            "workspace_id": "workspace-1",
            "actor_user_id": "knowledge-indexer",
            "force": False,
        }
    ]

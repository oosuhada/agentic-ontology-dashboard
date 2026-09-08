from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "infra" / "macmini" / "home_server_idle_supervisor.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("home_server_idle_supervisor", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_idle_supervisor_http_surface_is_fixed() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert 'self.path == "/activity"' in source
    assert 'self.path == "/status"' in source
    assert 'self.path == "/wake"' in source
    assert 'self.path == "/sleep"' in source
    assert "--no-build" in source


def test_idle_runtime_stops_services_in_declared_order() -> None:
    module = _load_module()
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def runner(args, **_kwargs):
        calls.append(args)
        return Result()

    runtime = module.ComposeRuntime(
        docker_bin="docker",
        project="demo",
        compose_file=Path("/tmp/compose.yml"),
        working_dir=Path("/tmp"),
        env_file=None,
        start_services=("db", "api", "web"),
        stop_services=("web", "api", "db"),
        ready_urls=(),
        ready_tcp=(),
        runner=runner,
    )

    runtime.stop()

    assert [call[-1] for call in calls] == ["web", "api", "db"]


def test_idle_installer_targets_only_expected_demo_projects() -> None:
    installer = (ROOT / "infra" / "macmini" / "install-idle-demo-supervisors.sh").read_text(
        encoding="utf-8"
    )
    assert "factorygraph-rca" in installer
    assert "instagram-orbstack" in installer
    assert "2700" in installer
    assert "3600" in installer
    assert "--no-build" not in installer  # wake behavior lives in the supervisor
    assert "trap rollback ERR" in installer
    assert "restoring previous nginx/cloudflared configuration" in installer
    assert 'had-$label-plist' in installer
    assert 'grep -q "server_name text2cypher.oosu.dev;"' in installer


def test_release_watcher_reinstalls_idle_demo_policy() -> None:
    watcher = (ROOT / "scripts" / "macmini_release_watcher.sh").read_text(encoding="utf-8")

    assert "install-idle-demo-supervisors.sh" in watcher
    assert '/bin/bash "$SOURCE_ROOT/infra/macmini/install-idle-demo-supervisors.sh"' in watcher
    assert "HOST_POLICY_EVALUATED_SHA" in watcher
    assert '"$PROD_ROOT/host-policy-base-sha"' in watcher

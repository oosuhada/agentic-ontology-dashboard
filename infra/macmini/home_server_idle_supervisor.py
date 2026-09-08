#!/usr/bin/env python3
"""Small localhost-only wake/sleep supervisor for Mac mini demo stacks.

The HTTP surface is intentionally fixed: status, activity, wake, and sleep.
Container names or shell commands are never accepted from requests.  Startup
uses an allow-listed Docker Compose file/project from environment variables and
never builds images on the request path.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def _csv(name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.environ.get(name, "").split(",") if item.strip())


@dataclass(slots=True)
class IdleStatus:
    name: str
    state: str
    last_activity: float
    last_wake: float
    idle_seconds: int
    min_up_seconds: int
    project: str


class ComposeRuntime:
    def __init__(
        self,
        *,
        docker_bin: str,
        project: str,
        compose_file: Path,
        working_dir: Path,
        env_file: Path | None,
        start_services: tuple[str, ...],
        stop_services: tuple[str, ...],
        ready_urls: tuple[str, ...],
        ready_tcp: tuple[str, ...],
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.docker_bin = docker_bin
        self.project = project
        self.compose_file = compose_file
        self.working_dir = working_dir
        self.env_file = env_file
        self.start_services = start_services
        self.stop_services = stop_services or tuple(reversed(start_services))
        self.ready_urls = ready_urls
        self.ready_tcp = ready_tcp
        self.runner = runner

    def _compose_base(self) -> list[str]:
        args = [self.docker_bin, "compose"]
        if self.env_file is not None:
            args.extend(["--env-file", str(self.env_file)])
        args.extend(["-p", self.project, "-f", str(self.compose_file)])
        return args

    def _run(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        return self.runner(
            args,
            check=check,
            cwd=str(self.working_dir),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def _service_rows(self) -> dict[str, str]:
        result = self._run(
            [
                self.docker_bin,
                "ps",
                "-a",
                "--filter",
                f"label=com.docker.compose.project={self.project}",
                "--format",
                '{{.Label "com.docker.compose.service"}}|{{.State}}',
            ]
        )
        rows: dict[str, str] = {}
        for raw in result.stdout.splitlines():
            service, sep, state = raw.partition("|")
            if sep and service:
                rows[service.strip()] = state.strip()
        return rows

    def has_any_running(self) -> bool:
        rows = self._service_rows()
        return any(rows.get(service) == "running" for service in self.start_services)

    @staticmethod
    def _http_ready(url: str) -> bool:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "home-idle-supervisor/1"})
            with urllib.request.urlopen(request, timeout=3) as response:
                return 200 <= int(response.status) < 500
        except urllib.error.HTTPError as exc:
            return 200 <= int(exc.code) < 500
        except Exception:
            return False

    @staticmethod
    def _tcp_ready(target: str) -> bool:
        host, sep, port_raw = target.rpartition(":")
        if not sep:
            return False
        try:
            port = int(port_raw)
        except ValueError:
            return False
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except OSError:
            return False

    def is_ready(self) -> bool:
        if self.ready_urls and not all(self._http_ready(url) for url in self.ready_urls):
            return False
        if self.ready_tcp and not all(self._tcp_ready(target) for target in self.ready_tcp):
            return False
        if self.ready_urls or self.ready_tcp:
            return True
        rows = self._service_rows()
        return all(rows.get(service) == "running" for service in self.start_services)

    def start(self, *, timeout: int = 180) -> None:
        if not self.start_services:
            raise RuntimeError("HOME_IDLE_START_SERVICES must not be empty")
        command = [*self._compose_base(), "up", "-d", "--no-build", *self.start_services]
        result = self._run(command, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"compose wake failed: {result.stderr.strip() or result.stdout.strip()}")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_ready():
                return
            time.sleep(2)
        raise TimeoutError(f"timed out waiting for {self.project} readiness")

    def stop(self) -> None:
        for service in self.stop_services:
            result = self._run(
                [*self._compose_base(), "stop", "-t", "20", service],
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"compose stop failed for {service}: "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )


class IdleSupervisor:
    def __init__(
        self,
        runtime: ComposeRuntime,
        *,
        name: str,
        idle_seconds: int,
        min_up_seconds: int,
        state_path: Path,
        disabled_file: Path,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.runtime = runtime
        self.name = name
        self.idle_seconds = idle_seconds
        self.min_up_seconds = min_up_seconds
        self.state_path = state_path
        self.disabled_file = disabled_file
        self.clock = clock
        self._lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._last_activity = 0.0
        self._last_wake = 0.0
        self._last_persist = 0.0
        self._state = "unknown"
        self._load_state()
        now = self.clock()
        try:
            ready = self.runtime.is_ready()
            any_running = self.runtime.has_any_running()
        except Exception:
            ready = False
            any_running = False
        if ready:
            self._state = "running"
            self._last_activity = self._last_activity or now
            self._last_wake = self._last_wake or now
        elif any_running:
            self._state = "partial"
        else:
            self._state = "sleeping"
        self._persist(force=True)

    def _load_state(self) -> None:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._last_activity = float(payload.get("last_activity") or 0.0)
        self._last_wake = float(payload.get("last_wake") or 0.0)

    def status(self) -> IdleStatus:
        with self._lock:
            return IdleStatus(
                name=self.name,
                state=self._state,
                last_activity=self._last_activity,
                last_wake=self._last_wake,
                idle_seconds=self.idle_seconds,
                min_up_seconds=self.min_up_seconds,
                project=self.runtime.project,
            )

    def _persist(self, *, force: bool = False) -> None:
        now = self.clock()
        if not force and now - self._last_persist < 15:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temp.write_text(json.dumps(asdict(self.status()), indent=2), encoding="utf-8")
        temp.replace(self.state_path)
        self._last_persist = now

    def activity(self) -> str:
        now = self.clock()
        with self._lock:
            self._last_activity = now
            state = self._state
            self._persist()
        if state in {"sleeping", "partial", "error", "unknown"} and not self.disabled_file.exists():
            self.request_wake()
            return "starting"
        return state

    def request_wake(self) -> None:
        with self._lock:
            if self._state in {"starting", "running"} or self.disabled_file.exists():
                return
            self._state = "starting"
            self._last_activity = self.clock()
            self._persist(force=True)
        threading.Thread(target=self._wake, name=f"{self.name}-wake", daemon=True).start()

    def _wake(self) -> None:
        with self._operation_lock:
            try:
                self.runtime.start(timeout=_env_int("HOME_IDLE_START_TIMEOUT_SECONDS", 180))
            except Exception as exc:
                with self._lock:
                    self._state = "error"
                    self._persist(force=True)
                print(f"{self.name} wake failed: {type(exc).__name__}: {exc}", flush=True)
                return
            with self._lock:
                now = self.clock()
                self._state = "running"
                self._last_wake = now
                self._last_activity = now
                self._persist(force=True)

    def request_sleep(self) -> None:
        with self._lock:
            if self._state in {"sleeping", "stopping"}:
                return
            self._state = "stopping"
            self._persist(force=True)
        threading.Thread(target=self._sleep, name=f"{self.name}-sleep", daemon=True).start()

    def _sleep(self) -> None:
        with self._operation_lock:
            try:
                self.runtime.stop()
            except Exception as exc:
                with self._lock:
                    self._state = "error"
                    self._persist(force=True)
                print(f"{self.name} sleep failed: {type(exc).__name__}: {exc}", flush=True)
                return
            with self._lock:
                self._state = "sleeping"
                self._persist(force=True)
                wake_again = self._last_activity > self.clock() - 30 and not self.disabled_file.exists()
            if wake_again:
                self.request_wake()

    def monitor_once(self) -> None:
        now = self.clock()
        with self._lock:
            state = self._state
            last_activity = self._last_activity
            last_wake = self._last_wake
        if state != "running":
            return
        if now - last_wake < self.min_up_seconds:
            return
        if now - last_activity >= self.idle_seconds:
            self.request_sleep()


class SupervisorHandler(BaseHTTPRequestHandler):
    supervisor: IdleSupervisor

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/activity":
            state = self.supervisor.activity()
            self.send_response(HTTPStatus.NO_CONTENT)
            self.send_header("X-Home-Idle-State", state)
            self.end_headers()
            return
        if self.path == "/status":
            self._json(HTTPStatus.OK, asdict(self.supervisor.status()))
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/wake":
            if self.supervisor.disabled_file.exists():
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"state": "maintenance"})
                return
            self.supervisor.activity()
            self._json(HTTPStatus.ACCEPTED, asdict(self.supervisor.status()))
            return
        if self.path == "/sleep":
            self.supervisor.request_sleep()
            self._json(HTTPStatus.ACCEPTED, asdict(self.supervisor.status()))
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})


def _build_supervisor() -> IdleSupervisor:
    name = os.environ.get("HOME_IDLE_NAME", "demo").strip() or "demo"
    project = os.environ["HOME_IDLE_PROJECT"].strip()
    compose_file = Path(os.environ["HOME_IDLE_COMPOSE_FILE"]).expanduser().resolve()
    working_dir = Path(
        os.environ.get("HOME_IDLE_WORKING_DIR", str(compose_file.parent))
    ).expanduser().resolve()
    env_raw = os.environ.get("HOME_IDLE_ENV_FILE", "").strip()
    env_file = Path(env_raw).expanduser().resolve() if env_raw else None
    if not compose_file.is_file():
        raise RuntimeError(f"compose file does not exist: {compose_file}")
    if env_file is not None and not env_file.is_file():
        raise RuntimeError(f"env file does not exist: {env_file}")
    state_root = Path.home() / "Services/home-idle-runtime/state"
    runtime = ComposeRuntime(
        docker_bin=os.environ.get(
            "HOME_IDLE_DOCKER_BIN",
            "/Applications/OrbStack.app/Contents/MacOS/xbin/docker",
        ),
        project=project,
        compose_file=compose_file,
        working_dir=working_dir,
        env_file=env_file,
        start_services=_csv("HOME_IDLE_START_SERVICES"),
        stop_services=_csv("HOME_IDLE_STOP_SERVICES"),
        ready_urls=_csv("HOME_IDLE_READY_URLS"),
        ready_tcp=_csv("HOME_IDLE_READY_TCP"),
    )
    return IdleSupervisor(
        runtime,
        name=name,
        idle_seconds=_env_int("HOME_IDLE_SECONDS", 2700),
        min_up_seconds=_env_int("HOME_IDLE_MIN_UP_SECONDS", 300),
        state_path=Path(
            os.environ.get("HOME_IDLE_STATE_PATH", str(state_root / f"{name}.json"))
        ).expanduser(),
        disabled_file=Path(
            os.environ.get("HOME_IDLE_DISABLED_FILE", str(state_root / f"{name}.disabled"))
        ).expanduser(),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    supervisor = _build_supervisor()
    if args.check:
        print(json.dumps(asdict(supervisor.status()), indent=2))
        return 0

    host = os.environ.get("HOME_IDLE_HOST", "127.0.0.1")
    port = _env_int("HOME_IDLE_PORT", 8232)
    SupervisorHandler.supervisor = supervisor
    server = ThreadingHTTPServer((host, port), SupervisorHandler)

    def monitor() -> None:
        while True:
            try:
                supervisor.monitor_once()
            except Exception as exc:
                print(f"{supervisor.name} monitor failed: {type(exc).__name__}: {exc}", flush=True)
            time.sleep(15)

    threading.Thread(target=monitor, name=f"{supervisor.name}-monitor", daemon=True).start()
    server.serve_forever(poll_interval=0.5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

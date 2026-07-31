#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None, timeout: int = 600) -> dict[str, Any]:
    started = time.monotonic()
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "output": result.stdout[-12000:],
        "pass": result.returncode == 0,
    }


def wait_http(url: str, timeout_seconds: float = 40.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"service did not become ready: {url}: {last_error}")


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Factory Signal Board release gates")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--with-e2e", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join([str(root / "api"), str(root / "ml" / "src")])
    environment["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp(prefix="factory-signal-pycache-")
    environment["FACTORY_SIGNAL_DB"] = str(Path(tempfile.mkdtemp(prefix="factory-signal-db-")) / "release.db")

    checks: list[dict[str, Any]] = []
    checks.append(run([sys.executable, "-m", "factory_signal_ml.cli", "validate-fixtures", "--root", str(root)], cwd=root, env=environment))
    checks.append(run([sys.executable, "-m", "pytest", "-q", "tests/test_mvp.py"], cwd=root, env=environment))
    checks.append(run([sys.executable, "scripts/evaluate_gold.py", "--root", str(root)], cwd=root, env=environment))
    checks.append(run([sys.executable, "-m", "compileall", "-q", "api", "ml/src", "scripts"], cwd=root, env=environment))

    node_available = shutil.which("npm") is not None
    frontend_temp: Path | None = None
    if node_available:
        frontend_temp = Path(tempfile.mkdtemp(prefix="factory-signal-web-")) / "web"
        shutil.copytree(root / "web", frontend_temp)
        checks.append(run(["npm", "install", "--no-audit", "--no-fund"], cwd=frontend_temp, timeout=600))
        if checks[-1]["pass"]:
            checks.append(run(["npm", "test"], cwd=frontend_temp, timeout=300))
            checks.append(run(["npm", "run", "lint"], cwd=frontend_temp, timeout=300))
            checks.append(run(["npm", "run", "build"], cwd=frontend_temp, timeout=300))
    else:
        checks.append({"command": ["npm"], "returncode": 127, "duration_seconds": 0, "output": "npm not found", "pass": False})

    e2e_result: dict[str, Any] | None = None
    if args.with_e2e and frontend_temp is not None and all(check["pass"] for check in checks):
        install_browser = run(["npx", "playwright", "install", "chromium"], cwd=frontend_temp, timeout=600)
        checks.append(install_browser)
        if install_browser["pass"]:
            api_port = reserve_port()
            web_port = reserve_port()
            while web_port == api_port:
                web_port = reserve_port()
            api_url = f"http://127.0.0.1:{api_port}"
            web_url = f"http://127.0.0.1:{web_port}"
            web_environment = os.environ.copy()
            web_environment["VITE_API_BASE_URL"] = api_url
            web_environment["PLAYWRIGHT_BASE_URL"] = web_url
            api_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "factory_signal_board.main:app", "--host", "127.0.0.1", "--port", str(api_port)],
                cwd=root,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            web_process = subprocess.Popen(
                ["npx", "vite", "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
                cwd=frontend_temp,
                env=web_environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                wait_http(f"{api_url}/health")
                wait_http(f"{web_url}/")
                e2e_result = run(["npm", "run", "test:e2e"], cwd=frontend_temp, env=web_environment, timeout=300)
            except Exception as exc:  # noqa: BLE001
                e2e_result = {
                    "command": ["npm", "run", "test:e2e"],
                    "returncode": 1,
                    "duration_seconds": 0,
                    "output": str(exc),
                    "pass": False,
                }
            finally:
                for process in (api_process, web_process):
                    process.terminate()
                for process in (api_process, web_process):
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
            checks.append(e2e_result)

    e2e_requirement_passed = not args.with_e2e or (e2e_result is not None and e2e_result["pass"])
    passed = all(check["pass"] for check in checks) and e2e_requirement_passed
    report = {
        "release_gate": "factory-signal-board-v1",
        "root": str(root),
        "with_e2e": args.with_e2e,
        "e2e_executed": e2e_result is not None,
        "checks": checks,
        "passed_checks": sum(1 for check in checks if check["pass"]),
        "failed_checks": sum(1 for check in checks if not check["pass"]),
        "pass": passed,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()

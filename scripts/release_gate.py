#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
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
    parser = argparse.ArgumentParser(description="Run Ontology Dashboard release gates")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--with-e2e", action="store_true")
    parser.add_argument("--with-live-project3", action="store_true")
    parser.add_argument("--live-project2-url", default="http://127.0.0.1:8000")
    parser.add_argument("--live-project3-url", default="http://127.0.0.1:8001")
    parser.add_argument(
        "--e2e-artifact-dir",
        help="Copy Playwright visual candidates and sanitized environment metadata to this directory.",
    )
    parser.add_argument("--output")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join([str(root / "api"), str(root / "ml" / "src")])
    environment["PYTHONPYCACHEPREFIX"] = tempfile.mkdtemp(prefix="factory-signal-pycache-")
    environment["ONTOLOGY_DASHBOARD_DB"] = str(Path(tempfile.mkdtemp(prefix="ontology-dashboard-db-")) / "release.db")
    environment["APP_ENV"] = "test"
    environment["SEED_DEMO_ACCOUNTS"] = "1"

    checks: list[dict[str, Any]] = []
    checks.append(run([sys.executable, "scripts/check_canonical_naming.py"], cwd=root, env=environment))
    checks.append(run([sys.executable, "scripts/check_visual_baselines.py"], cwd=root, env=environment))
    checks.append(run([sys.executable, "scripts/check_palantir_overhaul_visuals.py"], cwd=root, env=environment))
    checks.append(run([sys.executable, "scripts/check_postgresql_migration.py"], cwd=root, env=environment, timeout=180))
    checks.append(run([sys.executable, "scripts/check_postgresql_runtime.py"], cwd=root, env=environment, timeout=240))
    checks.append(run([sys.executable, "-m", "ontology_dashboard_manufacturing_ml.cli", "validate-fixtures", "--root", str(root)], cwd=root, env=environment))
    checks.append(run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=root, env=environment))
    checks.append(run([sys.executable, "scripts/evaluate_gold.py", "--root", str(root)], cwd=root, env=environment))
    checks.append(run([sys.executable, "-m", "compileall", "-q", "api", "ml/src", "scripts"], cwd=root, env=environment))

    node_available = shutil.which("npm") is not None
    frontend_temp: Path | None = None
    if node_available:
        frontend_temp = Path(tempfile.mkdtemp(prefix="factory-signal-web-")) / "web"
        shutil.copytree(
            root / "web",
            frontend_temp,
            ignore=shutil.ignore_patterns(
                "node_modules",
                "dist",
                "test-results",
                "playwright-report",
                ".vite",
            ),
        )
        visual_audit_source = root / "docs" / "ui" / "screenshots" / "palantir-gap-v2"
        if visual_audit_source.is_dir():
            shutil.copytree(
                visual_audit_source,
                frontend_temp.parent / "docs" / "ui" / "screenshots" / "palantir-gap-v2",
            )
        checks.append(run(["npm", "install", "--no-audit", "--no-fund"], cwd=frontend_temp, timeout=600))
        if checks[-1]["pass"]:
            checks.append(run(["npm", "test"], cwd=frontend_temp, timeout=300))
            checks.append(run(["npm", "run", "lint"], cwd=frontend_temp, timeout=300))
            checks.append(run(["npm", "run", "build"], cwd=frontend_temp, timeout=300))
    else:
        checks.append({"command": ["npm"], "returncode": 127, "duration_seconds": 0, "output": "npm not found", "pass": False})

    e2e_result: dict[str, Any] | None = None
    visual_capture_result: dict[str, Any] | None = None
    visual_candidate_result: dict[str, Any] | None = None
    if args.with_e2e and frontend_temp is not None and all(check["pass"] for check in checks):
        demo_dataset_seed = run(
            [
                sys.executable,
                "scripts/seed_demo_dataset_catalog.py",
                "--database",
                environment["ONTOLOGY_DASHBOARD_DB"],
                "--artifact-root",
                str(Path(environment["ONTOLOGY_DASHBOARD_DB"]).parent / "demo-datasets"),
            ],
            cwd=root,
            env=environment,
            timeout=120,
        )
        checks.append(demo_dataset_seed)
        if not demo_dataset_seed["pass"]:
            args.with_e2e = False

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
            web_environment["PLAYWRIGHT_API_URL"] = api_url
            web_environment["PLAYWRIGHT_EXTERNAL_SERVERS"] = "1"
            api_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "ontology_dashboard.app:app", "--host", "127.0.0.1", "--port", str(api_port)],
                cwd=root,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                text=True,
            )
            web_process = subprocess.Popen(
                [str(frontend_temp / "node_modules" / ".bin" / "vite"), "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
                cwd=frontend_temp,
                env=web_environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                wait_http(f"{api_url}/health")
                wait_http(f"{web_url}/")
                e2e_result = run(["npm", "run", "test:e2e"], cwd=frontend_temp, env=web_environment, timeout=600)
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
            if e2e_result["pass"]:
                visual_database_root = Path(tempfile.mkdtemp(prefix="ontology-dashboard-visual-db-"))
                visual_environment = environment.copy()
                visual_environment["ONTOLOGY_DASHBOARD_DB"] = str(visual_database_root / "visual.db")
                visual_seed_result = run(
                    [
                        sys.executable,
                        "scripts/seed_demo_dataset_catalog.py",
                        "--database",
                        visual_environment["ONTOLOGY_DASHBOARD_DB"],
                        "--artifact-root",
                        str(visual_database_root / "demo-datasets"),
                    ],
                    cwd=root,
                    env=visual_environment,
                    timeout=120,
                )
                checks.append(visual_seed_result)

                if visual_seed_result["pass"]:
                    candidate_root = frontend_temp / "test-results" / "palantir-overhaul-candidate"
                    shutil.rmtree(candidate_root, ignore_errors=True)
                    visual_api_port = reserve_port()
                    visual_web_port = reserve_port()
                    while visual_web_port == visual_api_port:
                        visual_web_port = reserve_port()
                    visual_api_url = f"http://127.0.0.1:{visual_api_port}"
                    visual_web_url = f"http://127.0.0.1:{visual_web_port}"
                    visual_web_environment = os.environ.copy()
                    visual_web_environment["VITE_API_BASE_URL"] = visual_api_url
                    visual_web_environment["PLAYWRIGHT_BASE_URL"] = visual_web_url
                    visual_web_environment["PLAYWRIGHT_API_URL"] = visual_api_url
                    visual_web_environment["PLAYWRIGHT_EXTERNAL_SERVERS"] = "1"
                    visual_api_process = subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "uvicorn",
                            "ontology_dashboard.app:app",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            str(visual_api_port),
                        ],
                        cwd=root,
                        env=visual_environment,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    visual_web_process = subprocess.Popen(
                        [
                            str(frontend_temp / "node_modules" / ".bin" / "vite"),
                            "--host",
                            "127.0.0.1",
                            "--port",
                            str(visual_web_port),
                            "--strictPort",
                        ],
                        cwd=frontend_temp,
                        env=visual_web_environment,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                    try:
                        wait_http(f"{visual_api_url}/health")
                        wait_http(f"{visual_web_url}/")
                        visual_capture_result = run(
                            ["npm", "run", "test:e2e:overhaul"],
                            cwd=frontend_temp,
                            env=visual_web_environment,
                            timeout=600,
                        )
                    except Exception as exc:  # noqa: BLE001
                        visual_capture_result = {
                            "command": ["npm", "run", "test:e2e:overhaul"],
                            "returncode": 1,
                            "duration_seconds": 0,
                            "output": str(exc),
                            "pass": False,
                        }
                    finally:
                        for process in (visual_api_process, visual_web_process):
                            process.terminate()
                        for process in (visual_api_process, visual_web_process):
                            try:
                                process.wait(timeout=10)
                            except subprocess.TimeoutExpired:
                                process.kill()
                    checks.append(visual_capture_result)

                    if visual_capture_result["pass"]:
                        visual_candidate_result = run(
                            [
                                sys.executable,
                                "scripts/check_palantir_overhaul_visuals.py",
                                "--candidate-root",
                                str(candidate_root),
                                "--require-candidate",
                            ],
                            cwd=root,
                            env=visual_environment,
                            timeout=180,
                        )
                        checks.append(visual_candidate_result)

    if args.e2e_artifact_dir:
        artifact_dir = Path(args.e2e_artifact_dir)
        if not artifact_dir.is_absolute():
            artifact_dir = root / artifact_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)
        candidate_source = (
            frontend_temp / "test-results" / "palantir-overhaul-candidate"
            if frontend_temp is not None
            else None
        )
        candidate_destination = artifact_dir / "candidate"
        if candidate_source is not None and candidate_source.is_dir():
            shutil.copytree(candidate_source, candidate_destination, dirs_exist_ok=True)
        metadata = {
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_arch": os.environ.get("RUNNER_ARCH"),
            "image_os": os.environ.get("ImageOS"),
            "image_version": os.environ.get("ImageVersion"),
            "platform": platform.platform(),
            "python": sys.version,
            "node": subprocess.run(
                ["node", "--version"],
                cwd=root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            ).stdout.strip(),
            "playwright": subprocess.run(
                ["npx", "playwright", "--version"],
                cwd=frontend_temp if frontend_temp is not None else root / "web",
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            ).stdout.strip(),
            "candidate_count": (
                len(list(candidate_destination.rglob("*.png")))
                if candidate_destination.is_dir()
                else 0
            ),
        }
        (artifact_dir / "environment.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if visual_candidate_result is not None:
            (artifact_dir / "visual-check.json").write_text(
                visual_candidate_result["output"],
                encoding="utf-8",
            )

    live_project3_result: dict[str, Any] | None = None
    if args.with_live_project3 and all(check["pass"] for check in checks):
        live_project3_result = run(
            [
                sys.executable,
                "scripts/verify_live_project3_hybrid.py",
                "--project2-url",
                args.live_project2_url,
                "--project3-url",
                args.live_project3_url,
            ],
            cwd=root,
            env=environment,
            timeout=180,
        )
        checks.append(live_project3_result)

    e2e_requirement_passed = not args.with_e2e or (e2e_result is not None and e2e_result["pass"])
    live_project3_requirement_passed = not args.with_live_project3 or (
        live_project3_result is not None and live_project3_result["pass"]
    )
    passed = (
        all(check["pass"] for check in checks)
        and e2e_requirement_passed
        and live_project3_requirement_passed
    )
    report = {
        "release_gate": "ontology-dashboard-v0.7",
        "root": str(root),
        "with_e2e": args.with_e2e,
        "e2e_executed": e2e_result is not None,
        "with_live_project3": args.with_live_project3,
        "live_project3_executed": live_project3_result is not None,
        "checks": checks,
        "passed_checks": sum(1 for check in checks if check["pass"]),
        "failed_checks": sum(1 for check in checks if not check["pass"]),
        "pass": passed,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(rendered, encoding="utf-8")
        print(json.dumps({
            "release_gate": report["release_gate"],
            "report_path": str(output_path),
            "with_e2e": report["with_e2e"],
            "e2e_executed": report["e2e_executed"],
            "with_live_project3": report["with_live_project3"],
            "live_project3_executed": report["live_project3_executed"],
            "passed_checks": report["passed_checks"],
            "failed_checks": report["failed_checks"],
            "pass": report["pass"],
        }, ensure_ascii=False, indent=2))
    else:
        print(rendered)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()

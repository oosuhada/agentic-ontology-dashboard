#!/usr/bin/env python3
"""Run the current MVP release gate."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def run(command: list[str], root: Path, env: dict[str, str]) -> dict[str, object]:
    started = time.monotonic()
    result = subprocess.run(command, cwd=root, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    return {
        "command": command,
        "returncode": result.returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "output": result.stdout[-12000:],
        "pass": result.returncode == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Predictive Maintenance MVP release checks")
    parser.add_argument("--with-e2e", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(root / "api"), str(root / "ml" / "src")])
    commands = [
        [sys.executable, "scripts/preflight.py"],
        [sys.executable, "-m", "compileall", "-q", "api/ontology_dashboard", "ml/src", "scripts"],
        [sys.executable, "-m", "pytest", "-q", "tests"],
        ["npm", "--prefix", "web", "run", "lint"],
        ["npm", "--prefix", "web", "run", "test"],
        ["npm", "--prefix", "web", "run", "build"],
    ]
    if args.with_e2e:
        commands.append(["npm", "--prefix", "web", "run", "test:e2e"])
    checks = [run(command, root, env) for command in commands]
    payload = {"check": "current-mvp-release-gate", "checks": checks, "pass": all(item["pass"] for item in checks)}
    output = json.dumps(payload, ensure_ascii=False, indent=2)
    print(output)
    if args.output:
        Path(args.output).write_text(output + "\n", encoding="utf-8")
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

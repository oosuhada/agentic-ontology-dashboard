#!/usr/bin/env python3
"""Check production prerequisites for the current MVP."""

from __future__ import annotations

import argparse
import json
import os
import socket
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def tcp_probe(url: str, default_port: int) -> tuple[bool, str]:
    parsed = urlparse(url)
    host, port = parsed.hostname, parsed.port or default_port
    if not host:
        return False, "host missing"
    try:
        with socket.create_connection((host, port), timeout=3):
            return True, f"{host}:{port} reachable"
    except OSError as error:
        return False, str(error)


def http_probe(base: str, path: str) -> tuple[bool, str]:
    try:
        with urlopen(Request(f"{base.rstrip('/')}{path}", headers={"User-Agent": "mvp-preflight"}), timeout=5) as response:
            return response.status == 200, f"HTTP {response.status}"
    except Exception as error:  # noqa: BLE001
        return False, str(error)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--public-url", default=os.getenv("ONTOLOGY_DASHBOARD_PUBLIC_URL", "https://dashboard.oosu.dev"))
    args = parser.parse_args()
    database_url = os.getenv("ONTOLOGY_DASHBOARD_DATABASE_URL", "") or os.getenv("ONTOLOGY_DASHBOARD_DB", "")
    postgres = tcp_probe(database_url, 5432) if database_url.startswith(("postgresql://", "postgresql+psycopg://")) else (False, "PostgreSQL URL not configured")
    health = http_probe(args.public_url, "/health")
    login = http_probe(args.public_url, "/login")
    checks = {
        "postgresql": {"pass": postgres[0], "evidence": postgres[1]},
        "public_health": {"pass": health[0], "evidence": health[1]},
        "public_login": {"pass": login[0], "evidence": login[1]},
    }
    passed = all(item["pass"] for item in checks.values())
    print(json.dumps({"check": "current-mvp-production-environment", "public_url": args.public_url, "checks": checks, "pass": passed}, ensure_ascii=False, indent=2))
    return 0 if passed or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())

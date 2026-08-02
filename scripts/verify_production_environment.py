#!/usr/bin/env python3
"""Report whether production-completion drills can run in the current environment.

The default mode is informational and exits successfully while distinguishing
ready, degraded and blocked capabilities. ``--strict`` fails when any requested
capability is not ready, making the same script usable in staging CI.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import sys
from dataclasses import asdict, dataclass
from urllib.parse import urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Capability:
    name: str
    state: str
    evidence: str
    action: str


def tcp_probe(value: str, default_port: int) -> tuple[bool, str]:
    parsed = urlparse(value if "://" in value else f"tcp://{value}")
    host = parsed.hostname
    port = parsed.port or default_port
    if not host:
        return False, "host is missing"
    try:
        with socket.create_connection((host, port), timeout=2):
            return True, f"tcp://{host}:{port} reachable"
    except OSError as exc:
        return False, f"tcp://{host}:{port} unavailable: {exc}"


def http_probe(value: str, path: str = "/health") -> tuple[bool, str]:
    base = value.rstrip("/")
    try:
        request = Request(f"{base}{path}", headers={"User-Agent": "ontology-dashboard-preflight"})
        with urlopen(request, timeout=3) as response:
            return response.status < 500, f"{base}{path} returned {response.status}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{base}{path} unavailable: {exc}"


def configured(name: str) -> str:
    return os.getenv(name, "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify production drill prerequisites")
    parser.add_argument("--strict", action="store_true", help="fail unless all requested capabilities are ready")
    parser.add_argument(
        "--require",
        action="append",
        choices=["compose", "postgresql", "redis", "neo4j", "project3", "oidc", "connectors", "object-storage", "observability"],
        help="capability required in strict mode; may be repeated",
    )
    args = parser.parse_args()
    requested = set(args.require or ["compose", "postgresql", "redis", "neo4j", "project3"])

    capabilities: list[Capability] = []

    docker = shutil.which("docker")
    compose_ready = False
    compose_evidence = "Docker CLI is not installed"
    if docker:
        import subprocess

        result = subprocess.run(
            [docker, "compose", "version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=10,
        )
        compose_ready = result.returncode == 0
        compose_evidence = result.stdout.strip() or f"docker compose exited {result.returncode}"
    capabilities.append(Capability(
        "compose",
        "ready" if compose_ready else "blocked",
        compose_evidence,
        "Install Docker Desktop/Engine with Compose v2, then run the cold-start and rollback runbook.",
    ))

    database_url = configured("ONTOLOGY_DASHBOARD_DATABASE_URL")
    if database_url:
        ready, evidence = tcp_probe(database_url, 5432)
        state = "ready" if ready else "blocked"
    else:
        state, evidence = "blocked", "ONTOLOGY_DASHBOARD_DATABASE_URL is not configured"
    capabilities.append(Capability(
        "postgresql",
        state,
        evidence,
        "Provide a non-superuser PostgreSQL URL with migration, RLS, backup and failover privileges required by the runbook.",
    ))

    redis_url = configured("ONTOLOGY_DASHBOARD_REDIS_URL")
    if redis_url:
        ready, evidence = tcp_probe(redis_url, 6379)
        state = "ready" if ready else "blocked"
    else:
        state, evidence = "blocked", "ONTOLOGY_DASHBOARD_REDIS_URL is not configured"
    capabilities.append(Capability(
        "redis",
        state,
        evidence,
        "Provide Redis credentials and run distributed rate-limit/outbox worker load tests.",
    ))

    neo4j_uri = configured("ONTOLOGY_DASHBOARD_NEO4J_URI") or configured("NEO4J_URI")
    neo4j_password = configured("ONTOLOGY_DASHBOARD_NEO4J_PASSWORD") or configured("NEO4J_PASSWORD")
    if neo4j_uri and neo4j_password:
        ready, evidence = tcp_probe(neo4j_uri, 7687)
        state = "ready" if ready else "blocked"
    elif neo4j_uri:
        state, evidence = "blocked", "Neo4j URI exists but password is missing"
    else:
        state, evidence = "blocked", "Neo4j URI and credentials are not configured"
    capabilities.append(Capability(
        "neo4j",
        state,
        evidence,
        "Provide scoped Neo4j credentials and verify projection, reconnect and backup behavior.",
    ))

    project3_url = configured("ONTOLOGY_DASHBOARD_PROJECT3_URL")
    if project3_url:
        ready, evidence = http_probe(project3_url)
        state = "ready" if ready else "blocked"
    else:
        state, evidence = "blocked", "ONTOLOGY_DASHBOARD_PROJECT3_URL is not configured"
    capabilities.append(Capability(
        "project3",
        state,
        evidence,
        "Start Project 3 and run scripts/verify_live_project3_hybrid.py with the same Project identity map.",
    ))

    oidc_issuer = configured("ONTOLOGY_DASHBOARD_OIDC_ISSUER")
    oidc_client = configured("ONTOLOGY_DASHBOARD_OIDC_CLIENT_ID")
    oidc_secret = configured("ONTOLOGY_DASHBOARD_OIDC_CLIENT_SECRET")
    oidc_ready = bool(oidc_issuer and oidc_client and oidc_secret)
    capabilities.append(Capability(
        "oidc",
        "ready" if oidc_ready else "blocked",
        "OIDC issuer/client credentials configured" if oidc_ready else "OIDC issuer, client ID or client secret is missing",
        "Register the staging callback and validate invitation, reset, role mapping and session revocation with the selected IdP.",
    ))

    connector_names = {
        "rest": "ONTOLOGY_DASHBOARD_REST_CONNECTOR_URL",
        "kafka": "ONTOLOGY_DASHBOARD_KAFKA_BOOTSTRAP_SERVERS",
        "mqtt": "ONTOLOGY_DASHBOARD_MQTT_URL",
        "opcua": "ONTOLOGY_DASHBOARD_OPCUA_URL",
    }
    configured_connectors = [name for name, env_name in connector_names.items() if configured(env_name)]
    capabilities.append(Capability(
        "connectors",
        "ready" if configured_connectors else "blocked",
        f"configured connectors: {', '.join(configured_connectors)}" if configured_connectors else "no production connector endpoint is configured",
        "Select one customer protocol first and provide credentials, replay fixtures and retry/backpressure acceptance thresholds.",
    ))

    object_endpoint = configured("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_ENDPOINT")
    object_bucket = configured("ONTOLOGY_DASHBOARD_OBJECT_STORAGE_BUCKET")
    object_ready = bool(object_endpoint and object_bucket)
    capabilities.append(Capability(
        "object-storage",
        "ready" if object_ready else "blocked",
        "object storage endpoint and bucket configured" if object_ready else "object storage endpoint or bucket is missing",
        "Configure an S3-compatible bucket, retention policy, signed URL expiry and checksum verification.",
    ))

    otel_endpoint = configured("OTEL_EXPORTER_OTLP_ENDPOINT")
    capabilities.append(Capability(
        "observability",
        "ready" if otel_endpoint else "blocked",
        f"OTLP endpoint: {otel_endpoint}" if otel_endpoint else "OTEL_EXPORTER_OTLP_ENDPOINT is not configured",
        "Provide an OTLP collector and validate request/run correlation, logs, traces and alert routing.",
    ))

    required_items = [item for item in capabilities if item.name in requested]
    passed = all(item.state == "ready" for item in required_items)
    payload = {
        "check": "ontology-dashboard-production-environment",
        "python": sys.version.split()[0],
        "strict": args.strict,
        "required": sorted(requested),
        "capabilities": [asdict(item) for item in capabilities],
        "ready": [item.name for item in capabilities if item.state == "ready"],
        "blocked": [item.name for item in capabilities if item.state != "ready"],
        "pass": passed,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if (passed or not args.strict) else 1


if __name__ == "__main__":
    raise SystemExit(main())

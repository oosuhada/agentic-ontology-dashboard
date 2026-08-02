#!/usr/bin/env python3
"""Verify a real Project 2 -> Project 3 three-store Agent run over HTTP.

Both services must already be running. The check intentionally uses only public
HTTP contracts and proves that one persisted hybrid run contains relational,
Neo4j and Project 3 RAG evidence.
"""

from __future__ import annotations

import argparse
import json
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

REQUIRED_STORES = {"postgresql", "neo4j", "project3_rag"}


def json_request(
    url: str,
    *,
    opener=None,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> dict:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        url,
        data=data,
        method=method,
        headers={"Accept": "application/json", **({"Content-Type": "application/json"} if data else {}), **(headers or {})},
    )
    client = opener.open if opener is not None else urlopen
    try:
        with client(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as error:
        body = error.read().decode("utf-8", errors="replace") if isinstance(error, HTTPError) else ""
        raise RuntimeError(f"HTTP request failed for {url}: {error}: {body[:1000]}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify live Project 2 / Project 3 hybrid evidence")
    parser.add_argument("--project2-url", default="http://127.0.0.1:8000")
    parser.add_argument("--project3-url", default="http://127.0.0.1:8001")
    parser.add_argument("--email", default="fde@ontology.local")
    parser.add_argument("--password", default="FDE!2026")
    parser.add_argument("--project-id", default="manufacturing-demo-project")
    parser.add_argument("--workspace-id", default="manufacturing-demo")
    parser.add_argument("--object-type", default="risk_event")
    parser.add_argument("--object-id", default="risk_event:EVT-GS-002")
    parser.add_argument(
        "--question",
        default="압력검사에 실패한 완제품과 그 구성품, 구성품별 공정 이상 및 품질검사 결과를 보여줘.",
    )
    args = parser.parse_args()

    p2 = args.project2_url.rstrip("/")
    p3 = args.project3_url.rstrip("/")
    project3_health = json_request(f"{p3}/api/v1/health")
    if project3_health.get("status") != "ready":
        raise SystemExit(f"Project 3 is not ready: {json.dumps(project3_health, ensure_ascii=False)[:2000]}")

    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies))
    login = json_request(
        f"{p2}/api/auth/login",
        opener=opener,
        method="POST",
        payload={"email": args.email, "password": args.password},
    )
    if not login.get("user"):
        raise SystemExit("Project 2 login did not return a user")
    csrf = next((cookie.value for cookie in cookies if cookie.name == "ontology_csrf"), None)
    if not csrf:
        raise SystemExit("Project 2 login did not set ontology_csrf")

    response = json_request(
        f"{p2}/api/agent/query",
        opener=opener,
        method="POST",
        headers={"X-CSRF-Token": csrf},
        payload={
            "project_id": args.project_id,
            "workspace_id": args.workspace_id,
            "route": "hybrid",
            "object_type": args.object_type,
            "object_id": args.object_id,
            "question": args.question,
            "top_k": 3,
        },
        timeout=90,
    )
    state = response.get("state") or {}
    evidence = state.get("evidence") or []
    stores = {item.get("store") for item in evidence if isinstance(item, dict)}
    missing = REQUIRED_STORES - stores
    if state.get("status") != "succeeded" or missing:
        raise SystemExit(
            json.dumps(
                {
                    "status": state.get("status"),
                    "stores": sorted(store for store in stores if store),
                    "missing": sorted(missing),
                    "caveats": state.get("caveats"),
                    "steps": state.get("steps"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

    result = {
        "pass": True,
        "project3_status": project3_health.get("status"),
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "stores": sorted(stores),
        "evidence_counts": {
            store: sum(1 for item in evidence if item.get("store") == store)
            for store in sorted(stores)
        },
        "claim_count": len(state.get("claims") or []),
        "checkpoint_sequence": state.get("checkpoint_sequence"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

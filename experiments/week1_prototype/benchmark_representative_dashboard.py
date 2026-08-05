"""Benchmark three symmetric FastAPI/Flask product features over local HTTP."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx

from framework_comparison.fastapi_app import (
    maintenance_recommendation as fastapi_recommendation_handler,
    manufacturing_dashboard as fastapi_dashboard_handler,
    risk_event_search as fastapi_search_handler,
)
from framework_comparison.flask_app import (
    _float_query,
    _int_query,
    _optional_choice_query,
    maintenance_recommendation as flask_recommendation_handler,
    manufacturing_dashboard as flask_dashboard_handler,
    risk_event_search as flask_search_handler,
)


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "framework_comparison" / "representative_dashboard_benchmark.json"


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    title: str
    method: str
    endpoint: str
    json_body: dict | None
    comparison_scope: str
    fastapi_functions: tuple[Callable, ...]
    flask_functions: tuple[Callable, ...]


FEATURES = (
    FeatureSpec(
        key="manufacturing_dashboard",
        title="제조 Dashboard 집계",
        method="GET",
        endpoint="/benchmark/manufacturing-dashboard?risk_threshold=0.0&limit=8",
        json_body=None,
        comparison_scope="Aggregate eight risk events, line summaries and sensor series",
        fastapi_functions=(fastapi_dashboard_handler,),
        flask_functions=(flask_dashboard_handler, _float_query, _int_query),
    ),
    FeatureSpec(
        key="risk_event_search",
        title="위험 이벤트 검색·필터",
        method="GET",
        endpoint=(
            "/benchmark/risk-events?risk_threshold=0.6&status=warning&"
            "sort=probability_desc&limit=5&offset=0"
        ),
        json_body=None,
        comparison_scope="Filter, sort and paginate product risk events",
        fastapi_functions=(fastapi_search_handler,),
        flask_functions=(
            flask_search_handler,
            _float_query,
            _int_query,
            _optional_choice_query,
        ),
    ),
    FeatureSpec(
        key="maintenance_recommendation",
        title="정비 조치 추천",
        method="POST",
        endpoint="/benchmark/maintenance-recommendation",
        json_body={
            "event_id": "EVT-GS-004",
            "operator_role": "process_manager",
            "include_evidence": True,
        },
        comparison_scope="Validate a POST body and apply a deterministic maintenance rule",
        fastapi_functions=(fastapi_recommendation_handler,),
        flask_functions=(flask_recommendation_handler,),
    ),
)


VALIDATION_CASES = (
    {
        "feature": "manufacturing_dashboard",
        "name": "limit below minimum",
        "method": "GET",
        "endpoint": "/benchmark/manufacturing-dashboard?limit=0",
        "json_body": None,
        "expected_status": 422,
    },
    {
        "feature": "risk_event_search",
        "name": "unsupported sort value",
        "method": "GET",
        "endpoint": "/benchmark/risk-events?sort=unsupported",
        "json_body": None,
        "expected_status": 422,
    },
    {
        "feature": "risk_event_search",
        "name": "valid empty result",
        "method": "GET",
        "endpoint": "/benchmark/risk-events?risk_threshold=1&status=normal",
        "json_body": None,
        "expected_status": 200,
    },
    {
        "feature": "maintenance_recommendation",
        "name": "invalid operator role",
        "method": "POST",
        "endpoint": "/benchmark/maintenance-recommendation",
        "json_body": {"event_id": "EVT-GS-004", "operator_role": "unknown"},
        "expected_status": 422,
    },
    {
        "feature": "maintenance_recommendation",
        "name": "unknown event",
        "method": "POST",
        "endpoint": "/benchmark/maintenance-recommendation",
        "json_body": {"event_id": "EVT-NOT-FOUND", "operator_role": "process_manager"},
        "expected_status": 404,
    },
)


def _percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, round((len(ordered) - 1) * ratio))
    return ordered[index]


def _function_loc(functions: tuple[Callable, ...]) -> int:
    total = 0
    seen: set[tuple[str, str]] = set()
    for function in functions:
        identity = (function.__module__, function.__name__)
        if identity in seen:
            continue
        seen.add(identity)
        for line in inspect.getsource(function).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", '"""')):
                continue
            total += 1
    return total


def _wait_until_ready(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=0.5)
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Server did not become ready: {url}")


def _request_once(
    method: str,
    url: str,
    json_body: dict | None,
) -> tuple[float, int, bytes]:
    started = time.perf_counter_ns()
    try:
        with httpx.Client(headers={"Connection": "close"}, timeout=5.0) as client:
            response = client.request(method, url, json=json_body)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        return elapsed_ms, response.status_code, response.content
    except httpx.HTTPError as error:
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        return elapsed_ms, 0, str(error).encode("utf-8")


def _benchmark(
    method: str,
    url: str,
    json_body: dict | None,
    *,
    requests: int,
    concurrency: int,
) -> dict:
    for _ in range(20):
        elapsed, status, _ = _request_once(method, url, json_body)
        if status != 200:
            raise RuntimeError(f"Warmup failed for {url}: status={status}, {elapsed=}")

    samples: list[float] = []
    failures = 0
    payload_hashes: set[str] = set()
    payload_sizes: set[int] = set()
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(_request_once, method, url, json_body)
            for _ in range(requests)
        ]
        for future in as_completed(futures):
            elapsed_ms, status, payload = future.result()
            samples.append(elapsed_ms)
            if status != 200:
                failures += 1
                continue
            payload_hashes.add(hashlib.sha256(payload).hexdigest())
            payload_sizes.add(len(payload))
    wall_seconds = time.perf_counter() - started
    successes = requests - failures
    return {
        "request_count": requests,
        "concurrency": concurrency,
        "connection_mode": "new HTTP connection per request",
        "success_count": successes,
        "error_count": failures,
        "error_rate_percent": round(failures / requests * 100, 4),
        "mean_ms": round(statistics.fmean(samples), 4),
        "p50_ms": round(statistics.median(samples), 4),
        "p95_ms": round(_percentile(samples, 0.95), 4),
        "p99_ms": round(_percentile(samples, 0.99), 4),
        "throughput_rps": round(successes / wall_seconds, 2),
        "wall_seconds": round(wall_seconds, 4),
        "stable_payload": len(payload_hashes) == 1,
        "payload_sha256": next(iter(payload_hashes), None),
        "payload_bytes": next(iter(payload_sizes), None),
    }


def _aggregate_rounds(rounds: list[dict]) -> dict:
    if not rounds:
        raise ValueError("At least one benchmark round is required")
    medians = {
        key: round(statistics.median(item[key] for item in rounds), 4)
        for key in (
            "mean_ms",
            "p50_ms",
            "p95_ms",
            "p99_ms",
            "throughput_rps",
            "wall_seconds",
        )
    }
    total_requests = sum(item["request_count"] for item in rounds)
    total_errors = sum(item["error_count"] for item in rounds)
    return {
        "round_count": len(rounds),
        "requests_per_round": rounds[0]["request_count"],
        "request_count": total_requests,
        "concurrency": rounds[0]["concurrency"],
        "connection_mode": rounds[0]["connection_mode"],
        "success_count": total_requests - total_errors,
        "error_count": total_errors,
        "error_rate_percent": round(total_errors / total_requests * 100, 4),
        **medians,
        "stable_payload": all(item["stable_payload"] for item in rounds),
        "payload_sha256": rounds[0]["payload_sha256"],
        "payload_bytes": rounds[0]["payload_bytes"],
        "round_metrics": [
            {
                key: item[key]
                for key in (
                    "p50_ms",
                    "p95_ms",
                    "p99_ms",
                    "throughput_rps",
                    "error_rate_percent",
                )
            }
            for item in rounds
        ],
    }


def _performance_scores(results: dict[str, dict]) -> dict[str, float]:
    metrics = {
        "sequential_p95": {
            name: item["sequential"]["p95_ms"] for name, item in results.items()
        },
        "sequential_rps": {
            name: item["sequential"]["throughput_rps"]
            for name, item in results.items()
        },
        "concurrent_p95": {
            name: item["concurrent"]["p95_ms"] for name, item in results.items()
        },
        "concurrent_rps": {
            name: item["concurrent"]["throughput_rps"]
            for name, item in results.items()
        },
    }
    scores: dict[str, float] = {}
    for name in results:
        components = [
            5 * min(metrics["sequential_p95"].values()) / metrics["sequential_p95"][name],
            5 * metrics["sequential_rps"][name] / max(metrics["sequential_rps"].values()),
            5 * min(metrics["concurrent_p95"].values()) / metrics["concurrent_p95"][name],
            5 * metrics["concurrent_rps"][name] / max(metrics["concurrent_rps"].values()),
        ]
        scores[name] = round(statistics.fmean(components), 2)
    return scores


def _canonical_payload_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validation_report(base_urls: dict[str, str]) -> dict:
    rows: list[dict] = []
    for case in VALIDATION_CASES:
        statuses: dict[str, int] = {}
        payloads: dict[str, dict | list | str] = {}
        for framework, base_url in base_urls.items():
            response = httpx.request(
                case["method"],
                f"{base_url}{case['endpoint']}",
                json=case["json_body"],
                timeout=5.0,
            )
            statuses[framework] = response.status_code
            try:
                payloads[framework] = response.json()
            except json.JSONDecodeError:
                payloads[framework] = response.text
        rows.append(
            {
                **case,
                "statuses": statuses,
                "status_match": len(set(statuses.values())) == 1,
                "expected_status_match": all(
                    status == case["expected_status"] for status in statuses.values()
                ),
                "payload_equal_when_successful": (
                    payloads["FastAPI"] == payloads["Flask"]
                    if case["expected_status"] == 200
                    else None
                ),
            }
        )
    return {
        "case_count": len(rows),
        "all_statuses_match": all(item["status_match"] for item in rows),
        "all_expected_statuses": all(item["expected_status_match"] for item in rows),
        "successful_payloads_equal": all(
            item["payload_equal_when_successful"] is not False for item in rows
        ),
        "cases": rows,
    }


def run_benchmark(
    *,
    sequential_requests: int = 300,
    concurrent_requests: int = 300,
    concurrency: int = 10,
    rounds: int = 3,
    fastapi_port: int = 5120,
    flask_port: int = 5121,
) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    commands = {
        "FastAPI": [
            sys.executable,
            "-m",
            "uvicorn",
            "framework_comparison.fastapi_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(fastapi_port),
            "--log-level",
            "warning",
        ],
        "Flask": [
            sys.executable,
            "-m",
            "flask",
            "--app",
            "framework_comparison.flask_app:app",
            "run",
            "--host",
            "127.0.0.1",
            "--port",
            str(flask_port),
            "--no-debugger",
            "--no-reload",
        ],
    }
    processes: list[subprocess.Popen] = []
    try:
        for command in commands.values():
            processes.append(
                subprocess.Popen(
                    command,
                    cwd=ROOT,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
        base_urls = {
            "FastAPI": f"http://127.0.0.1:{fastapi_port}",
            "Flask": f"http://127.0.0.1:{flask_port}",
        }
        _wait_until_ready(f"{base_urls['FastAPI']}/health")
        _wait_until_ready(f"{base_urls['Flask']}/health")

        feature_reports: dict[str, dict] = {}
        for feature_index, feature in enumerate(FEATURES):
            urls = {
                name: f"{base_url}{feature.endpoint}"
                for name, base_url in base_urls.items()
            }
            payloads: dict[str, dict] = {}
            for name, url in urls.items():
                response = httpx.request(
                    feature.method,
                    url,
                    json=feature.json_body,
                    timeout=5.0,
                )
                response.raise_for_status()
                payloads[name] = response.json()
            parity = {
                "responses_equal": payloads["FastAPI"] == payloads["Flask"],
                "fastapi_payload_sha256": _canonical_payload_hash(payloads["FastAPI"]),
                "flask_payload_sha256": _canonical_payload_hash(payloads["Flask"]),
                "payload_bytes": {
                    name: len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
                    for name, payload in payloads.items()
                },
            }
            if not parity["responses_equal"]:
                raise RuntimeError(f"FastAPI and Flask payloads differ: {feature.key}")

            round_results = {
                "FastAPI": {"sequential": [], "concurrent": []},
                "Flask": {"sequential": [], "concurrent": []},
            }
            for round_index in range(rounds):
                fast_first = (round_index + feature_index) % 2 == 0
                order = ["FastAPI", "Flask"] if fast_first else ["Flask", "FastAPI"]
                for name in order:
                    round_results[name]["sequential"].append(
                        _benchmark(
                            feature.method,
                            urls[name],
                            feature.json_body,
                            requests=sequential_requests,
                            concurrency=1,
                        )
                    )
                for name in reversed(order):
                    round_results[name]["concurrent"].append(
                        _benchmark(
                            feature.method,
                            urls[name],
                            feature.json_body,
                            requests=concurrent_requests,
                            concurrency=concurrency,
                        )
                    )
            results = {
                name: {
                    "sequential": _aggregate_rounds(item["sequential"]),
                    "concurrent": _aggregate_rounds(item["concurrent"]),
                }
                for name, item in round_results.items()
            }
            feature_reports[feature.key] = {
                "title": feature.title,
                "method": feature.method,
                "endpoint": feature.endpoint,
                "request_body": feature.json_body,
                "comparison_scope": feature.comparison_scope,
                "parity": parity,
                "implementation": {
                    "fastapi_adapter_loc": _function_loc(feature.fastapi_functions),
                    "flask_adapter_loc": _function_loc(feature.flask_functions),
                },
                "results": results,
                "performance_scores": _performance_scores(results),
            }

        aggregate_scores = {
            framework: round(
                statistics.fmean(
                    feature["performance_scores"][framework]
                    for feature in feature_reports.values()
                ),
                2,
            )
            for framework in ("FastAPI", "Flask")
        }
        validation = _validation_report(base_urls)
        total_loc = {
            "FastAPI": _function_loc(
                tuple(
                    function
                    for feature in FEATURES
                    for function in feature.fastapi_functions
                )
            ),
            "Flask": _function_loc(
                tuple(
                    function
                    for feature in FEATURES
                    for function in feature.flask_functions
                )
            ),
        }
        return {
            "status": "measured",
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "feature_count": len(FEATURES),
            "page": "/app/projects/manufacturing-demo-project",
            "comparison_scope": (
                "Three symmetric product features using the same GS fixtures, risk snapshot "
                "and shared business functions; only HTTP adapters differ"
            ),
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "measurement": "local loopback HTTP, separate server processes",
                "rounds": rounds,
                "round_order": "alternating framework-first order across rounds and features",
                "connection_mode": "new HTTP connection per request for both servers",
                "fastapi_server": "Uvicorn single worker",
                "flask_server": "Werkzeug development server, threaded",
                "production_benchmark": False,
            },
            "parity": {
                "all_feature_responses_equal": all(
                    item["parity"]["responses_equal"]
                    for item in feature_reports.values()
                ),
                "feature_count": len(feature_reports),
                "validation_statuses_match": validation["all_statuses_match"],
                "validation_expected_statuses": validation["all_expected_statuses"],
            },
            "validation": validation,
            "implementation": {
                "shared_service": "framework_comparison.representative_dashboard",
                "fastapi_adapter_loc": total_loc["FastAPI"],
                "flask_adapter_loc": total_loc["Flask"],
                "fastapi_validation": "Declarative query/body constraints + response_model",
                "flask_validation": "Manual query parsing + Pydantic body/shared payload",
            },
            "features": feature_reports,
            "performance_score_formula": (
                "Per feature: equal average of normalized sequential p95, sequential throughput, "
                "concurrent p95 and concurrent throughput. Overall: arithmetic mean of three feature scores."
            ),
            "performance_scores": aggregate_scores,
            "limitations": [
                "Local Mac loopback measurement; not a cloud production benchmark.",
                "FastAPI and Flask use their normal local servers, so the result includes server-stack overhead.",
                "The shared functions use eight product GS fixtures and do not include a remote database or external model call.",
            ],
        }
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sequential-requests", type=int, default=300)
    parser.add_argument("--concurrent-requests", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run_benchmark(
        sequential_requests=max(50, args.sequential_requests),
        concurrent_requests=max(50, args.concurrent_requests),
        concurrency=max(1, args.concurrency),
        rounds=max(1, args.rounds),
    )
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output}: features={report['feature_count']} "
        f"parity={report['parity']['all_feature_responses_equal']} "
        f"scores={report['performance_scores']}"
    )


if __name__ == "__main__":
    main()

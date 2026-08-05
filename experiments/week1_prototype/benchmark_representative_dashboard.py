"""Benchmark the same manufacturing dashboard over real local HTTP servers."""

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx

from framework_comparison.fastapi_app import manufacturing_dashboard as fastapi_handler
from framework_comparison.flask_app import (
    _float_query,
    _int_query,
    manufacturing_dashboard as flask_handler,
)


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "framework_comparison" / "representative_dashboard_benchmark.json"
QUERY = "risk_threshold=0.0&limit=8"
ENDPOINT = f"/benchmark/manufacturing-dashboard?{QUERY}"


def _percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, round((len(ordered) - 1) * ratio))
    return ordered[index]


def _function_loc(functions: list[Callable]) -> int:
    total = 0
    for function in functions:
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


def _request_once(url: str) -> tuple[float, int, bytes]:
    started = time.perf_counter_ns()
    try:
        with httpx.Client(headers={"Connection": "close"}, timeout=5.0) as client:
            response = client.get(url)
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        return elapsed_ms, response.status_code, response.content
    except httpx.HTTPError as error:
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        return elapsed_ms, 0, str(error).encode("utf-8")


def _benchmark(url: str, *, requests: int, concurrency: int) -> dict:
    for _ in range(25):
        elapsed, status, _ = _request_once(url)
        if status != 200:
            raise RuntimeError(f"Warmup failed for {url}: status={status}, {elapsed=}")

    samples: list[float] = []
    failures = 0
    payload_hashes: set[str] = set()
    payload_sizes: set[int] = set()
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(_request_once, url) for _ in range(requests)]
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
    numeric_medians = {
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
        **numeric_medians,
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
    """Average normalized sequential/concurrent p95 and throughput scores."""

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


def run_benchmark(
    *,
    sequential_requests: int = 500,
    concurrent_requests: int = 500,
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
        fastapi_url = f"http://127.0.0.1:{fastapi_port}{ENDPOINT}"
        flask_url = f"http://127.0.0.1:{flask_port}{ENDPOINT}"
        _wait_until_ready(fastapi_url)
        _wait_until_ready(flask_url)

        fastapi_payload = httpx.get(fastapi_url, timeout=5.0).json()
        flask_payload = httpx.get(flask_url, timeout=5.0).json()
        parity = {
            "responses_equal": fastapi_payload == flask_payload,
            "fastapi_payload_sha256": hashlib.sha256(
                json.dumps(fastapi_payload, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "flask_payload_sha256": hashlib.sha256(
                json.dumps(flask_payload, sort_keys=True).encode("utf-8")
            ).hexdigest(),
            "visible_events": fastapi_payload["summary"]["visible_events"],
            "sensor_points": len(fastapi_payload["sensor_series"]),
        }
        if not parity["responses_equal"]:
            raise RuntimeError("FastAPI and Flask representative payloads differ")

        urls = {"FastAPI": fastapi_url, "Flask": flask_url}
        round_results = {
            "FastAPI": {"sequential": [], "concurrent": []},
            "Flask": {"sequential": [], "concurrent": []},
        }
        for round_index in range(rounds):
            order = ["FastAPI", "Flask"] if round_index % 2 == 0 else ["Flask", "FastAPI"]
            for name in order:
                round_results[name]["sequential"].append(
                    _benchmark(
                        urls[name],
                        requests=sequential_requests,
                        concurrency=1,
                    )
                )
            for name in reversed(order):
                round_results[name]["concurrent"].append(
                    _benchmark(
                        urls[name],
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
        performance_scores = _performance_scores(results)
        return {
            "status": "measured",
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "endpoint": ENDPOINT,
            "page": "/app/projects/manufacturing-demo-project",
            "comparison_scope": (
                "Same product GS fixtures, same risk snapshot, same aggregation function, "
                "different FastAPI/Flask HTTP adapters"
            ),
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "measurement": "local loopback HTTP, separate server processes",
                "rounds": rounds,
                "round_order": "alternating FastAPI-first and Flask-first",
                "connection_mode": "new HTTP connection per request for both servers",
                "fastapi_server": "Uvicorn single worker",
                "flask_server": "Werkzeug development server, threaded",
                "production_benchmark": False,
            },
            "implementation": {
                "shared_service": "framework_comparison.representative_dashboard",
                "fastapi_adapter_loc": _function_loc([fastapi_handler]),
                "flask_adapter_loc": _function_loc(
                    [flask_handler, _float_query, _int_query]
                ),
                "fastapi_validation": "Query constraints + Pydantic response_model",
                "flask_validation": "Manual query parsing + Pydantic shared payload",
            },
            "parity": parity,
            "results": results,
            "performance_score_formula": (
                "equal average of normalized sequential p95, sequential throughput, "
                "concurrent p95 and concurrent throughput; best metric receives 5"
            ),
            "performance_scores": performance_scores,
            "limitations": [
                "Local Mac loopback measurement; not a cloud production benchmark.",
                "FastAPI and Flask use their normal local servers, so the result includes server-stack overhead.",
                "The shared business function uses eight product GS fixtures and does not include a remote database or external model call.",
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
    parser.add_argument("--sequential-requests", type=int, default=500)
    parser.add_argument("--concurrent-requests", type=int, default=500)
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
        f"wrote {args.output}: parity={report['parity']['responses_equal']} "
        f"scores={report['performance_scores']}"
    )


if __name__ == "__main__":
    main()


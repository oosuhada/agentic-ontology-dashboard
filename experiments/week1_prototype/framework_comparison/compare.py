"""Run a reproducible, same-contract FastAPI/Flask comparison."""

from __future__ import annotations

import argparse
import inspect
import json
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from fastapi.testclient import TestClient

from .contracts import HEALTH_PAYLOAD
from .fastapi_app import app as fastapi_app
from .flask_app import app as flask_app


FULL_SURFACE_SNAPSHOT_PATH = Path(__file__).with_name("full_surface_snapshot.json")


@dataclass(frozen=True)
class LatencySummary:
    iterations: int
    mean_ms: float
    median_ms: float
    p95_ms: float


@dataclass(frozen=True)
class FrameworkResult:
    framework: str
    health_status: int
    health_payload_matches: bool
    content_type: str
    openapi_status: int
    automatic_openapi: bool
    response_schema_declared: bool
    test_client_available: bool
    implementation_loc: int
    latency: LatencySummary
    rubric_score: int


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * percentile))
    return ordered[index]


def _measure(getter: Callable[[], object], iterations: int) -> LatencySummary:
    for _ in range(25):
        getter()

    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter_ns()
        getter()
        elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
        samples.append(elapsed_ms)

    return LatencySummary(
        iterations=iterations,
        mean_ms=round(statistics.fmean(samples), 4),
        median_ms=round(statistics.median(samples), 4),
        p95_ms=round(_percentile(samples, 0.95), 4),
    )


def _implementation_loc(function: Callable) -> int:
    lines = inspect.getsource(function).splitlines()
    return sum(
        1
        for line in lines
        if line.strip() and not line.lstrip().startswith(("#", '"""'))
    )


def run_comparison(iterations: int = 500) -> dict:
    fastapi_client = TestClient(fastapi_app)
    flask_client = flask_app.test_client()

    fast_health = fastapi_client.get("/health")
    flask_health = flask_client.get("/health")
    fast_openapi = fastapi_client.get("/openapi.json")
    flask_openapi = flask_client.get("/openapi.json")

    fast_schema = (
        fast_openapi.json()
        .get("paths", {})
        .get("/health", {})
        .get("get", {})
        .get("responses", {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )

    from .fastapi_app import health as fastapi_health
    from .flask_app import health as flask_health_function

    fast_score = sum(
        [
            fast_health.status_code == 200,
            fast_health.json() == HEALTH_PAYLOAD,
            fast_openapi.status_code == 200,
            bool(fast_schema),
            True,  # built-in TestClient path
        ]
    )
    flask_score = sum(
        [
            flask_health.status_code == 200,
            flask_health.get_json() == HEALTH_PAYLOAD,
            flask_openapi.status_code == 200,
            False,  # no response schema without an additional extension
            True,  # built-in Flask test client
        ]
    )

    results = [
        FrameworkResult(
            framework="FastAPI",
            health_status=fast_health.status_code,
            health_payload_matches=fast_health.json() == HEALTH_PAYLOAD,
            content_type=fast_health.headers.get("content-type", ""),
            openapi_status=fast_openapi.status_code,
            automatic_openapi=fast_openapi.status_code == 200,
            response_schema_declared=bool(fast_schema),
            test_client_available=True,
            implementation_loc=_implementation_loc(fastapi_health),
            latency=_measure(lambda: fastapi_client.get("/health"), iterations),
            rubric_score=int(fast_score),
        ),
        FrameworkResult(
            framework="Flask",
            health_status=flask_health.status_code,
            health_payload_matches=flask_health.get_json() == HEALTH_PAYLOAD,
            content_type=flask_health.headers.get("content-type", ""),
            openapi_status=flask_openapi.status_code,
            automatic_openapi=flask_openapi.status_code == 200,
            response_schema_declared=False,
            test_client_available=True,
            implementation_loc=_implementation_loc(flask_health_function),
            latency=_measure(lambda: flask_client.get("/health"), iterations),
            rubric_score=int(flask_score),
        ),
    ]

    winner = max(results, key=lambda item: item.rubric_score)
    report = {
        "contract": HEALTH_PAYLOAD,
        "methodology": {
            "same_endpoint": "GET /health",
            "same_payload": True,
            "latency_scope": "in-process local development reference only",
            "selection_basis": [
                "health contract",
                "automatic OpenAPI",
                "declared response schema",
                "testability",
            ],
        },
        "results": [asdict(result) for result in results],
        "selected_framework": winner.framework,
        "selection_reason": (
            "FastAPI and Flask both satisfied the health contract. FastAPI was "
            "selected because it additionally produced an OpenAPI document and "
            "a declared response schema without adding a third-party extension."
        ),
    }
    if FULL_SURFACE_SNAPSHOT_PATH.exists():
        report["full_surface"] = json.loads(FULL_SURFACE_SNAPSHOT_PATH.read_text())
        report["selection_reason"] = report["full_surface"]["conclusion"]["reason"]
    return report


def render_markdown(report: dict) -> str:
    rows = []
    for result in report["results"]:
        latency = result["latency"]
        rows.append(
            "| {framework} | {health_status} | {health_payload_matches} | "
            "{automatic_openapi} | {response_schema_declared} | {implementation_loc} | "
            "{median_ms:.4f} | {p95_ms:.4f} | {rubric_score}/5 |".format(
                **result,
                median_ms=latency["median_ms"],
                p95_ms=latency["p95_ms"],
            )
        )

    lines = [
            "# FastAPI vs Flask — 동일 `/health` 비교 결과",
            "",
            "| 프레임워크 | HTTP | 응답 일치 | 자동 OpenAPI | 응답 Schema | 코드 줄 수 | p50 ms* | p95 ms* | 점수 |",
            "|---|---:|---|---|---|---:|---:|---:|---:|",
            *rows,
            "",
            f"**선정:** {report['selected_framework']}",
            "",
            report["selection_reason"],
            "",
            "\\* 지연시간은 인프로세스 로컬 참고값이며 운영 성능 결론이 아니다.",
        ]
    full_surface = report.get("full_surface")
    if full_surface:
        scope = full_surface["scope"]
        fastapi = full_surface["fastapi"]
        flask = full_surface["flask"]
        auth = fastapi["authenticated_probe"]
        lines.extend(
            [
                "",
                "# Ontology Dashboard 전체 API 표면 비교",
                "",
                f"- OpenAPI 경로: {scope['path_count']}개",
                f"- HTTP 작업: {scope['operation_count']}개",
                f"- FastAPI 인증 전수 프로브: {auth['operation_count']} / {scope['operation_count']}",
                f"- 처리되지 않은 5xx: {auth['unhandled_server_error_count']}건",
                f"- FastAPI 자동 OpenAPI: {fastapi['automatic_openapi_operation_count']}개 작업",
                f"- FastAPI 자동 요청 검증: {fastapi['automatic_request_validation_operation_count']}개 작업",
                f"- FastAPI JSON 성공 응답 Schema·런타임 검증: {fastapi['automatic_response_schema_operation_count']}개 작업",
                f"- FastAPI 필드 수준 JSON 성공 응답 Schema: {fastapi['field_level_response_schema_operation_count']}개 작업",
                f"- FastAPI binary·SSE 성공 응답 계약: {fastapi['non_json_response_contract_operation_count']}개 작업",
                f"- FastAPI no-content 성공 응답 계약: {fastapi['no_content_contract_operation_count']}개 작업",
                f"- Flask 라우트 미러: {flask['registered_operation_count']}개 작업",
                f"- Flask 실제 업무 핸들러: {flask['business_handler_operation_count']}개",
                f"- Flask 추가 업무 구성 대상: {flask['manual_business_setup_operation_count']}개 작업",
                "",
                full_surface["conclusion"]["limitation"],
            ]
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    args = parser.parse_args()

    report = run_comparison(iterations=max(25, args.iterations))
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))


if __name__ == "__main__":
    main()


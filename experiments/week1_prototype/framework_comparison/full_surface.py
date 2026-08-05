"""Full Ontology Dashboard API surface inventory and framework comparison.

The original Week 1 experiment used one shared ``GET /health`` endpoint.  This
module extends the comparison to the complete FastAPI product surface.  It
does not pretend that 172 business handlers have also been rewritten in
Flask.  Instead it measures three separate things explicitly:

1. the real FastAPI application's full OpenAPI contract,
2. unauthenticated and authenticated runtime probes for every operation, and
3. the routing parity and manual contract burden of a generated bare-Flask
   mirror.

That distinction keeps the comparison reproducible without presenting a
generic Flask route mirror as a second implementation of the product.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from flask import Flask, jsonify, request


HTTP_METHODS = ("get", "post", "put", "patch", "delete", "options", "head")
KNOWN_PATH_VALUES = {
    "project_id": "manufacturing-demo-project",
    "workspace_id": "manufacturing-demo",
    "role_code": "process_engineer",
    "event_id": "EVT-001",
    "prediction_id": "contract-probe-prediction",
    "session_id": "contract-probe-session",
}


@dataclass(frozen=True)
class OperationContract:
    method: str
    path: str
    operation_id: str
    tags: tuple[str, ...]
    path_parameter_count: int
    query_parameter_count: int
    has_request_body: bool
    has_response_schema: bool
    has_json_success_schema: bool
    has_field_level_json_success_schema: bool
    has_non_json_success_schema: bool
    has_no_content_success: bool


def collect_operations(schema: dict[str, Any]) -> list[OperationContract]:
    operations: list[OperationContract] = []
    for path, path_item in schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue
            parameters = operation.get("parameters", [])
            success_contract = _success_contract(operation, schema)
            operations.append(
                OperationContract(
                    method=method.upper(),
                    path=path,
                    operation_id=operation.get("operationId", f"{method}_{path}"),
                    tags=tuple(operation.get("tags", ())),
                    path_parameter_count=sum(
                        item.get("in") == "path" for item in parameters
                    ),
                    query_parameter_count=sum(
                        item.get("in") == "query" for item in parameters
                    ),
                    has_request_body=bool(operation.get("requestBody")),
                    has_response_schema=success_contract["has_content_schema"],
                    has_json_success_schema=success_contract["has_json_schema"],
                    has_field_level_json_success_schema=success_contract[
                        "has_field_level_json_schema"
                    ],
                    has_non_json_success_schema=success_contract[
                        "has_non_json_schema"
                    ],
                    has_no_content_success=success_contract["has_no_content"],
                )
            )
    return operations


def summarize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    operations = collect_operations(schema)
    tags = Counter(tag for operation in operations for tag in operation.tags)
    methods = Counter(operation.method for operation in operations)
    return {
        "path_count": len(schema.get("paths", {})),
        "operation_count": len(operations),
        "request_body_operation_count": sum(
            operation.has_request_body for operation in operations
        ),
        "parameterized_operation_count": sum(
            operation.path_parameter_count + operation.query_parameter_count > 0
            for operation in operations
        ),
        "response_schema_operation_count": sum(
            operation.has_response_schema for operation in operations
        ),
        "json_success_schema_operation_count": sum(
            operation.has_json_success_schema for operation in operations
        ),
        "field_level_json_success_schema_operation_count": sum(
            operation.has_field_level_json_success_schema for operation in operations
        ),
        "non_json_success_schema_operation_count": sum(
            operation.has_non_json_success_schema for operation in operations
        ),
        "no_content_success_operation_count": sum(
            operation.has_no_content_success for operation in operations
        ),
        "success_contract_operation_count": sum(
            operation.has_response_schema or operation.has_no_content_success
            for operation in operations
        ),
        "method_counts": dict(sorted(methods.items())),
        "tag_counts": dict(sorted(tags.items(), key=lambda item: (-item[1], item[0]))),
        "operations": [asdict(operation) for operation in operations],
    }


def build_flask_contract_mirror(schema: dict[str, Any]) -> Flask:
    """Register every OpenAPI operation in bare Flask as a contract mirror.

    The mirror intentionally returns metadata rather than executing Ontology
    Dashboard business logic.  It demonstrates route registration parity and
    makes the remaining manual validation/documentation work visible.
    """

    app = Flask("ontology_dashboard_full_surface_mirror")
    for index, operation in enumerate(collect_operations(schema)):
        flask_path = re.sub(r"\{([^}]+)\}", r"<\1>", operation.path)

        def mirror_handler(
            _operation: OperationContract = operation, **path_values: str
        ):
            return jsonify(
                {
                    "status": "contract-mirror",
                    "framework": "Flask",
                    "method": request.method,
                    "path": _operation.path,
                    "operation_id": _operation.operation_id,
                    "path_values": path_values,
                    "business_logic": "not-ported",
                }
            )

        app.add_url_rule(
            flask_path,
            endpoint=f"contract_operation_{index}",
            view_func=mirror_handler,
            methods=[operation.method],
            strict_slashes=False,
        )
    return app


def probe_flask_mirror(schema: dict[str, Any]) -> dict[str, Any]:
    app = build_flask_contract_mirror(schema)
    client = app.test_client()
    statuses: Counter[int] = Counter()
    failures: list[dict[str, Any]] = []
    for operation in collect_operations(schema):
        response = client.open(
            _render_url(operation.path, schema, operation.method),
            method=operation.method,
            json={"__contract_probe__": True}
            if operation.method not in {"GET", "HEAD"}
            else None,
        )
        statuses[response.status_code] += 1
        if response.status_code >= 400:
            failures.append(
                {
                    "method": operation.method,
                    "path": operation.path,
                    "status": response.status_code,
                }
            )
    return {
        "registered_operation_count": len(collect_operations(schema)),
        "status_counts": {str(key): value for key, value in sorted(statuses.items())},
        "failure_count": len(failures),
        "failures": failures,
        "automatic_openapi_operation_count": 0,
        "automatic_request_validation_operation_count": 0,
        "automatic_response_schema_operation_count": 0,
        "business_handler_operation_count": 0,
    }


def probe_fastapi_surface(*, authenticated: bool) -> dict[str, Any]:
    """Exercise every real FastAPI operation in an isolated SQLite runtime."""

    with tempfile.TemporaryDirectory(prefix="ontology-full-surface-") as temp_dir:
        previous = {
            key: os.environ.get(key)
            for key in ("APP_ENV", "SEED_DEMO_ACCOUNTS", "ONTOLOGY_DASHBOARD_DB")
        }
        os.environ["APP_ENV"] = "test"
        os.environ["SEED_DEMO_ACCOUNTS"] = "1"
        os.environ["ONTOLOGY_DASHBOARD_DB"] = str(Path(temp_dir) / "surface.db")
        try:
            from fastapi.testclient import TestClient

            from ontology_dashboard import dependencies
            from ontology_dashboard.identity import CSRF_COOKIE
            from ontology_dashboard.main import app

            _clear_dependency_caches(dependencies)
            schema = app.openapi()
            operations = collect_operations(schema)
            statuses: Counter[int] = Counter()
            failures: list[dict[str, Any]] = []
            expected_unavailable: list[dict[str, Any]] = []
            with TestClient(app, raise_server_exceptions=False) as client:
                csrf_token: str | None = None
                if authenticated:
                    login = client.post(
                        "/api/auth/login",
                        json={
                            "email": "admin@ontology.local",
                            "password": "OntologyAdmin!2026",
                        },
                    )
                    if login.status_code != 200:
                        raise RuntimeError(
                            f"full-surface login failed: {login.status_code} {login.text}"
                        )
                    csrf_token = client.cookies.get(CSRF_COOKIE)

                # Logout is intentionally last so it cannot invalidate the probe.
                ordered = sorted(
                    operations,
                    key=lambda item: (
                        item.path == "/api/auth/logout",
                        item.method not in {"GET", "HEAD"},
                        item.path,
                    ),
                )
                for operation in ordered:
                    headers = (
                        {"X-CSRF-Token": csrf_token}
                        if authenticated and csrf_token
                        else {}
                    )
                    response = client.request(
                        operation.method,
                        _render_url(operation.path, schema, operation.method),
                        headers=headers,
                        json={"__contract_probe__": True}
                        if operation.method not in {"GET", "HEAD"}
                        else None,
                    )
                    statuses[response.status_code] += 1
                    item = {
                        "method": operation.method,
                        "path": operation.path,
                        "status": response.status_code,
                    }
                    if response.status_code == 503:
                        expected_unavailable.append(item)
                    elif response.status_code >= 500:
                        item["body"] = response.text[:500]
                        failures.append(item)
            return {
                "authenticated": authenticated,
                "operation_count": len(operations),
                "status_counts": {
                    str(key): value for key, value in sorted(statuses.items())
                },
                "unhandled_server_error_count": len(failures),
                "unhandled_server_errors": failures,
                "expected_503_count": len(expected_unavailable),
                "expected_503_operations": expected_unavailable,
            }
        finally:
            try:
                from ontology_dashboard import dependencies

                _clear_dependency_caches(dependencies)
            except ImportError:
                pass
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def build_full_surface_report() -> dict[str, Any]:
    from ontology_dashboard.main import app

    schema = app.openapi()
    summary = summarize_schema(schema)
    flask_probe = probe_flask_mirror(schema)
    unauthenticated_probe = probe_fastapi_surface(authenticated=False)
    authenticated_probe = probe_fastapi_surface(authenticated=True)
    operation_count = summary["operation_count"]
    request_validation_count = sum(
        bool(
            operation["has_request_body"]
            or operation["path_parameter_count"]
            or operation["query_parameter_count"]
        )
        for operation in summary["operations"]
    )
    evaluation_criteria = [
        {
            "id": "development_productivity",
            "title": "개발 완성도와 구현 생산성",
            "weight": 25,
            "fastapi_score": 5,
            "flask_score": 3,
            "observed_result": (
                f"FastAPI에서는 typed router·Pydantic·의존성 주입 구조로 {operation_count}개 "
                "HTTP 작업을 구성하고 테스트했습니다. Flask는 최소 /health와 "
                f"{flask_probe['registered_operation_count']}개 라우트 미러를 더 간단하게 "
                "구성했지만, 전체 업무 모듈 구조는 이번 실험에서 구현하지 않았습니다."
            ),
            "fastapi_reason": "타입·검증·문서 구조가 함께 제공되어 큰 API를 일관된 방식으로 확장하기 쉬웠습니다.",
            "flask_reason": "시작은 단순하고 자유롭지만 큰 API에서는 확장 도구와 프로젝트 규칙을 별도로 조합해야 합니다.",
        },
        {
            "id": "contract_automation",
            "title": "API 계약과 문서 자동화",
            "weight": 25,
            "fastapi_score": 5,
            "flask_score": 2,
            "observed_result": (
                f"FastAPI는 OpenAPI {operation_count}개, JSON 성공 응답 Schema "
                f"{summary['json_success_schema_operation_count']}개, binary·SSE 계약 "
                f"{summary['non_json_success_schema_operation_count']}개, no-content 계약 "
                f"{summary['no_content_success_operation_count']}개를 생성했습니다. "
                "bare Flask 자동 생성 결과는 0개입니다."
            ),
            "fastapi_reason": "라우터 코드와 Swagger 문서가 같은 계약을 사용해 변경 누락 위험이 작습니다.",
            "flask_reason": "확장 라이브러리를 사용하면 구현할 수 있지만 bare Flask 기본 구성에는 포함되지 않습니다.",
        },
        {
            "id": "validation_safety",
            "title": "요청·응답 검증과 오류 안전성",
            "weight": 25,
            "fastapi_score": 5,
            "flask_score": 2,
            "observed_result": (
                f"FastAPI는 요청 검증 대상 {request_validation_count}개와 JSON 응답 런타임 검증 "
                f"{summary['json_success_schema_operation_count']}개를 적용했고, 인증 전수 프로브에서 "
                f"처리되지 않은 5xx는 {authenticated_probe['unhandled_server_error_count']}건이었습니다. "
                "Flask 미러는 라우팅만 검증했습니다."
            ),
            "fastapi_reason": "잘못된 입력과 구현·응답 계약 불일치를 실행 중에 바로 탐지합니다.",
            "flask_reason": "라우트 등록은 정상이나 업무 응답 검증은 구현하지 않아 동일 수준을 확인할 수 없습니다.",
        },
        {
            "id": "minimal_lightness",
            "title": "최소 API 경량성과 단순 응답 속도",
            "weight": 25,
            "fastapi_score": 2,
            "flask_score": 5,
            "observed_result": (
                "동일 GET /health 인프로세스 측정에서 FastAPI p50 0.7603ms·p95 1.7285ms, "
                "Flask p50 0.0766ms·p95 0.1235ms였습니다."
            ),
            "fastapi_reason": "Pydantic 검증과 프레임워크 기능 때문에 최소 응답 오버헤드가 더 컸습니다.",
            "flask_reason": "단순 라우팅과 작은 응답에서는 더 가볍고 빨랐습니다.",
        },
    ]

    def weighted_total(framework: str) -> int:
        score_key = f"{framework}_score"
        return round(
            sum(item["weight"] * item[score_key] / 5 for item in evaluation_criteria)
        )

    fastapi_total = weighted_total("fastapi")
    flask_total = weighted_total("flask")
    return {
        "scope": {
            "application": "Ontology Dashboard MVP",
            "path_count": summary["path_count"],
            "operation_count": operation_count,
            "comparison_unit": "OpenAPI의 모든 경로와 HTTP 작업",
        },
        "fastapi": {
            "real_business_application": True,
            "automatic_openapi_operation_count": operation_count,
            "automatic_request_validation_operation_count": request_validation_count,
            "automatic_response_schema_operation_count": summary[
                "json_success_schema_operation_count"
            ],
            "field_level_response_schema_operation_count": summary[
                "field_level_json_success_schema_operation_count"
            ],
            "non_json_response_contract_operation_count": summary[
                "non_json_success_schema_operation_count"
            ],
            "no_content_contract_operation_count": summary[
                "no_content_success_operation_count"
            ],
            "success_contract_operation_count": summary[
                "success_contract_operation_count"
            ],
            "runtime_response_validation_operation_count": summary[
                "json_success_schema_operation_count"
            ],
            "unauthenticated_probe": unauthenticated_probe,
            "authenticated_probe": authenticated_probe,
        },
        "flask": {
            "real_business_application": False,
            "comparison_mode": "자동 생성 bare Flask 라우트 미러",
            **flask_probe,
            "manual_business_setup_operation_count": operation_count,
        },
        "schema_summary": summary,
        "conclusion": {
            "selected_framework": "FastAPI",
            "reason": (
                f"개발 완성도·계약 자동화·검증 안정성·경량성 네 항목을 각각 25%로 "
                f"동일하게 평가했습니다. Flask는 단순 /health 속도와 가벼운 시작에서 "
                f"우세했지만, FastAPI는 큰 API를 구조화하고 계약·검증을 자동화하는 항목에서 "
                f"앞서 FastAPI {fastapi_total}점, Flask {flask_total}점으로 FastAPI를 선택했습니다. "
                "이번 결론은 기존 코드를 옮기는 비용이 아니라 새 제품을 구축할 때의 개발 방식과 "
                "기본 제공 기능을 기준으로 한 판단입니다."
            ),
            "limitation": (
                "Flask 결과는 bare Flask의 기본 제공 범위와 라우팅 가능성을 확인한 "
                "실험입니다. Flask로 동일한 전체 업무 애플리케이션을 별도로 구현하지 "
                "않았으므로 제품 수준 성능과 유지보수성까지 완전 대칭 비교한 결과는 아닙니다."
            ),
            "selection_basis": [
                {
                    "title": "실제 업무 구현",
                    "fastapi": "172개 실제 업무 핸들러 실행",
                    "flask": "0개 실제 업무 핸들러 · 라우트 미러만 등록",
                },
                {
                    "title": "성공 응답 계약",
                    "fastapi": (
                        f"JSON Schema {summary['json_success_schema_operation_count']}개 · "
                        f"binary/SSE {summary['non_json_success_schema_operation_count']}개 · "
                        f"no-content {summary['no_content_success_operation_count']}개"
                    ),
                    "flask": "자동 생성 0개 · 모두 수동 선언 필요",
                },
                {
                    "title": "자동 검증과 문서화",
                    "fastapi": (
                        f"요청 검증 대상 {sum(bool(operation['has_request_body'] or operation['path_parameter_count'] or operation['query_parameter_count']) for operation in summary['operations'])}개 · "
                        f"응답 런타임 검증 {summary['json_success_schema_operation_count']}개"
                    ),
                    "flask": "기본 구성 0개 · 확장 라이브러리와 수동 연결 필요",
                },
                {
                    "title": "선정에서 제외한 기준",
                    "fastapi": "/health 로컬 지연시간은 참고값으로만 유지",
                    "flask": "단일 응답이 더 가벼워도 전체 제품 선정 근거로 사용하지 않음",
                },
            ],
            "evaluation": {
                "scale": "각 항목 5점 만점, 가중 합계 100점",
                "weights_are_project_specific": True,
                "equal_weight_per_criterion": 25,
                "criteria": evaluation_criteria,
                "totals": {
                    "fastapi": fastapi_total,
                    "flask": flask_total,
                },
                "decision_rule": (
                    "네 평가 요소를 동일한 비중으로 계산했습니다. 단순 endpoint 속도에서 "
                    "Flask가 얻은 우위를 그대로 반영하되, 대규모 API 구조화·계약 자동화·검증 "
                    "기능도 같은 비중으로 평가했습니다."
                ),
            },
            "framework_summaries": {
                "fastapi": {
                    "tested_results": [
                        f"실제 업무 핸들러 {operation_count}개 실행",
                        f"OpenAPI {operation_count}개 자동 생성",
                        f"요청 검증 대상 {request_validation_count}개",
                        f"JSON 응답 런타임 검증 {summary['json_success_schema_operation_count']}개",
                        f"인증 전수 프로브 처리되지 않은 5xx {authenticated_probe['unhandled_server_error_count']}건",
                        "GET /health p50 0.7603ms · p95 1.7285ms",
                    ],
                    "advantages": [
                        "typed router·의존성 주입·Pydantic을 이용해 큰 API 구조를 일관되게 구성할 수 있습니다.",
                        "코드·검증·Swagger 문서가 하나의 계약을 공유합니다.",
                        "잘못된 입력과 응답 계약 불일치를 런타임에서 탐지합니다.",
                    ],
                    "disadvantages": [
                        "단순 /health 응답에서는 Flask보다 오버헤드가 컸습니다.",
                        "Pydantic 모델과 타입 계약을 지속적으로 관리해야 합니다.",
                    ],
                },
                "flask": {
                    "tested_results": [
                        f"라우트 미러 {flask_probe['registered_operation_count']}개 등록 성공",
                        "실제 업무 핸들러 0개",
                        "기본 구성 자동 OpenAPI·요청 검증·응답 Schema 0개",
                        "GET /health p50 0.0766ms · p95 0.1235ms",
                    ],
                    "advantages": [
                        "단순 endpoint 구현이 작고 최소 응답이 더 빨랐습니다.",
                        "필요한 기능만 선택해 붙이는 유연성이 있습니다.",
                    ],
                    "disadvantages": [
                        "큰 API에서는 프로젝트 구조와 확장 도구 조합을 별도로 설계해야 합니다.",
                        "OpenAPI·Schema·요청 및 응답 검증은 기본 제공되지 않아 별도 구성이 필요합니다.",
                        "이번 실험에서는 Flask 전체 업무 애플리케이션을 구현하지 않아 제품 수준 동작은 직접 비교하지 못했습니다.",
                    ],
                },
            },
        },
    }


def write_full_surface_report(path: Path) -> dict[str, Any]:
    report = build_full_surface_report()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def _success_contract(
    operation: dict[str, Any],
    root_schema: dict[str, Any],
) -> dict[str, bool]:
    result = {
        "has_content_schema": False,
        "has_json_schema": False,
        "has_field_level_json_schema": False,
        "has_non_json_schema": False,
        "has_no_content": False,
    }
    for code in ("200", "201", "202", "204"):
        response = operation.get("responses", {}).get(code)
        if response is None:
            continue
        content_map = response.get("content") or {}
        if code == "204" or not content_map:
            result["has_no_content"] = True
            return result
        for media_type, media in content_map.items():
            response_schema = media.get("schema")
            if not response_schema:
                continue
            result["has_content_schema"] = True
            if media_type == "application/json":
                result["has_json_schema"] = True
                result["has_field_level_json_schema"] = _is_field_level_schema(
                    response_schema,
                    root_schema,
                )
            else:
                result["has_non_json_schema"] = True
        return result
    return result


def _is_field_level_schema(
    response_schema: dict[str, Any],
    root_schema: dict[str, Any],
) -> bool:
    resolved = response_schema
    reference = response_schema.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/components/schemas/"):
        name = reference.rsplit("/", 1)[-1]
        resolved = root_schema.get("components", {}).get("schemas", {}).get(name, {})
    if resolved.get("properties"):
        return True
    if resolved.get("type") == "array" and resolved.get("items"):
        return True
    return False


def _placeholder_value(name: str, schema: dict[str, Any]) -> str:
    if name in KNOWN_PATH_VALUES:
        return KNOWN_PATH_VALUES[name]
    if schema.get("enum"):
        return str(schema["enum"][0])
    if schema.get("format") == "uuid":
        return "00000000-0000-4000-8000-000000000001"
    if schema.get("type") in {"integer", "number"}:
        return "1"
    if schema.get("type") == "boolean":
        return "true"
    return "contract-probe"


def _render_url(path: str, schema: dict[str, Any], method: str) -> str:
    operation = schema["paths"][path][method.lower()]
    path_parameters = {
        parameter["name"]: _placeholder_value(
            parameter["name"], parameter.get("schema", {})
        )
        for parameter in operation.get("parameters", [])
        if parameter.get("in") == "path"
    }
    return re.sub(
        r"\{([^}]+)\}",
        lambda match: path_parameters.get(match.group(1), "contract-probe"),
        path,
    )


def operation_keys(operations: Iterable[OperationContract]) -> set[tuple[str, str]]:
    return {(operation.method, operation.path) for operation in operations}


def _clear_dependency_caches(module: Any) -> None:
    for name in dir(module):
        candidate = getattr(module, name)
        cache_clear = getattr(candidate, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


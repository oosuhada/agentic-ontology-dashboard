"""FastAPI implementation and public comparison report for Week 1."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from html import escape
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse

from .contracts import HEALTH_PAYLOAD, HealthResponse
from .representative_dashboard import (
    MaintenanceRecommendationRequest,
    MaintenanceRecommendationResponse,
    ManufacturingDashboardResponse,
    RepresentativeEventNotFound,
    RiskEventSearchResponse,
    RiskSort,
    RiskStatus,
    build_maintenance_recommendation,
    build_manufacturing_dashboard,
    build_risk_event_search,
)


FULL_SURFACE_SNAPSHOT_PATH = Path(__file__).with_name("full_surface_snapshot.json")
REPRESENTATIVE_BENCHMARK_PATH = Path(__file__).with_name(
    "representative_dashboard_benchmark.json"
)


def _load_full_surface_snapshot() -> dict:
    if not FULL_SURFACE_SNAPSHOT_PATH.exists():
        return {
            "scope": {"path_count": 0, "operation_count": 0},
            "fastapi": {
                "automatic_openapi_operation_count": 0,
                "automatic_request_validation_operation_count": 0,
                "automatic_response_schema_operation_count": 0,
                "field_level_response_schema_operation_count": 0,
                "non_json_response_contract_operation_count": 0,
                "no_content_contract_operation_count": 0,
                "success_contract_operation_count": 0,
                "runtime_response_validation_operation_count": 0,
                "authenticated_probe": {
                    "operation_count": 0,
                    "status_counts": {},
                    "unhandled_server_error_count": 0,
                    "expected_503_count": 0,
                },
            },
            "flask": {
                "registered_operation_count": 0,
                "business_handler_operation_count": 0,
                "manual_business_setup_operation_count": 0,
            },
            "conclusion": {
                "reason": "전체 API 비교 스냅샷이 아직 생성되지 않았습니다.",
                "limitation": "run_full_surface_comparison.sh를 실행해야 합니다.",
                "selection_basis": [],
            },
        }
    return json.loads(FULL_SURFACE_SNAPSHOT_PATH.read_text())


FULL_SURFACE_SNAPSHOT = _load_full_surface_snapshot()


def _load_representative_benchmark() -> dict:
    if not REPRESENTATIVE_BENCHMARK_PATH.exists():
        return {
            "status": "not-generated",
            "feature_count": 0,
            "parity": {"all_feature_responses_equal": False},
            "validation": {"case_count": 0, "all_statuses_match": False},
            "features": {},
            "performance_scores": {"FastAPI": 0.0, "Flask": 0.0},
        }
    return json.loads(REPRESENTATIVE_BENCHMARK_PATH.read_text(encoding="utf-8"))


REPRESENTATIVE_BENCHMARK = _load_representative_benchmark()


COMPARISON_SNAPSHOT = {
    "methodology": {
        "endpoint": "GET /health",
        "same_payload": True,
        "iterations": 500,
        "latency_scope": "in-process local development reference only",
    },
    "results": [
        {
            "framework": "FastAPI",
            "health_status": 200,
            "payload_matches": True,
            "automatic_openapi": True,
            "response_schema": True,
            "test_client": True,
            "implementation_loc": 3,
            "median_ms": 0.7603,
            "p95_ms": 1.7285,
        },
        {
            "framework": "Flask",
            "health_status": 200,
            "payload_matches": True,
            "automatic_openapi": False,
            "response_schema": False,
            "test_client": True,
            "implementation_loc": 3,
            "median_ms": 0.0766,
            "p95_ms": 0.1235,
        },
    ],
    "selected_framework": "FastAPI",
    "selection_reason": (
        "두 프레임워크 모두 동일한 /health 계약을 충족했다. Flask는 최소 응답에서 "
        "더 가벼웠지만, FastAPI는 별도 확장 없이 응답 스키마 검증과 OpenAPI 문서를 "
        "제공해 데이터셋·예측 API 확장에 더 적합했다."
    ),
    "source": {
        "repository": "oosuhada/agentic-ontology-dashboard",
        "branch": "experiment/week1-streamlit-plotly-framework-comparison",
        "commit": "3556b7d",
    },
}


def _overall_average_scores() -> dict[str, float]:
    criteria = FULL_SURFACE_SNAPSHOT["conclusion"]["evaluation"]["criteria"]
    if not criteria:
        return {"FastAPI": 0.0, "Flask": 0.0}
    return {
        "FastAPI": round(
            sum(item["fastapi_score"] for item in criteria) / len(criteria),
            2,
        ),
        "Flask": round(
            sum(item["flask_score"] for item in criteria) / len(criteria),
            2,
        ),
    }


def _baseline_comparison_payload() -> dict:
    average_scores = _overall_average_scores()
    results = [
        {
            **item,
            "overall_average_score": average_scores[item["framework"]],
            "score_basis": "4개 평가 요소의 동일 가중치 산술평균",
        }
        for item in COMPARISON_SNAPSHOT["results"]
    ]
    return {
        **COMPARISON_SNAPSHOT,
        "results": results,
        "overall_average_scores": average_scores,
    }


app = FastAPI(
    title="Week 1 FastAPI vs Flask comparison",
    version="2.0.0",
    description=(
        "동일 /health 기준선과 Ontology Dashboard 전체 162개 경로·172개 HTTP "
        "작업을 함께 비교한 실험 결과입니다."
    ),
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(**HEALTH_PAYLOAD)


@app.get(
    "/benchmark/manufacturing-dashboard",
    response_model=ManufacturingDashboardResponse,
    tags=["representative-benchmark"],
)
def manufacturing_dashboard(
    risk_threshold: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=8, ge=1, le=100),
    line: str | None = None,
) -> ManufacturingDashboardResponse:
    return build_manufacturing_dashboard(
        risk_threshold=risk_threshold,
        limit=limit,
        line=line,
    )


@app.get(
    "/benchmark/risk-events",
    response_model=RiskEventSearchResponse,
    tags=["representative-benchmark"],
)
def risk_event_search(
    risk_threshold: float = Query(default=0.6, ge=0.0, le=1.0),
    status: RiskStatus | None = None,
    failure_type: str | None = None,
    line: str | None = None,
    sort: RiskSort = "probability_desc",
    limit: int = Query(default=5, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RiskEventSearchResponse:
    return build_risk_event_search(
        risk_threshold=risk_threshold,
        status=status,
        failure_type=failure_type,
        line=line,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@app.post(
    "/benchmark/maintenance-recommendation",
    response_model=MaintenanceRecommendationResponse,
    tags=["representative-benchmark"],
)
def maintenance_recommendation(
    request: MaintenanceRecommendationRequest,
) -> MaintenanceRecommendationResponse:
    try:
        return build_maintenance_recommendation(request)
    except RepresentativeEventNotFound as error:
        raise HTTPException(status_code=404, detail="event not found") from error


@app.get("/comparison.json", tags=["comparison"])
def comparison_json() -> dict:
    return {
        "baseline": _baseline_comparison_payload(),
        "representative_dashboard": REPRESENTATIVE_BENCHMARK,
        "representative_features": REPRESENTATIVE_BENCHMARK,
        "full_surface": FULL_SURFACE_SNAPSHOT,
    }


@app.get("/full-comparison.json", tags=["comparison"])
def full_comparison_json() -> dict:
    return FULL_SURFACE_SNAPSHOT


@app.get("/representative-benchmark.json", tags=["comparison"])
def representative_benchmark_json() -> dict:
    return REPRESENTATIVE_BENCHMARK


@app.get("/flask-health", tags=["comparison"])
def flask_health_proxy() -> JSONResponse:
    """Expose the locally running Flask experiment through the report origin."""

    try:
        with urllib.request.urlopen("http://127.0.0.1:5111/health", timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return JSONResponse(payload, status_code=response.status)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return JSONResponse(
            {"status": "unavailable", "framework": "Flask", "detail": str(error)},
            status_code=503,
        )


def _flask_proxy(
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
) -> JSONResponse:
    data = None
    headers: dict[str, str] = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"http://127.0.0.1:5111{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return JSONResponse(payload, status_code=response.status)
    except urllib.error.HTTPError as error:
        try:
            payload = json.loads(error.read().decode("utf-8"))
        except json.JSONDecodeError:
            payload = {"detail": str(error)}
        return JSONResponse(payload, status_code=error.code)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        return JSONResponse(
            {"status": "unavailable", "framework": "Flask", "detail": str(error)},
            status_code=503,
        )


@app.get("/flask-dashboard", tags=["representative-benchmark"])
def flask_dashboard_proxy(
    risk_threshold: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=8, ge=1, le=100),
    line: str | None = None,
) -> JSONResponse:
    query = urllib.parse.urlencode(
        {
            "risk_threshold": risk_threshold,
            "limit": limit,
            **({"line": line} if line else {}),
        }
    )
    return _flask_proxy(f"/benchmark/manufacturing-dashboard?{query}")


@app.get("/flask-risk-events", tags=["representative-benchmark"])
def flask_risk_events_proxy(
    risk_threshold: float = Query(default=0.6, ge=0.0, le=1.0),
    status: RiskStatus | None = None,
    failure_type: str | None = None,
    line: str | None = None,
    sort: RiskSort = "probability_desc",
    limit: int = Query(default=5, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    query = urllib.parse.urlencode(
        {
            "risk_threshold": risk_threshold,
            "sort": sort,
            "limit": limit,
            "offset": offset,
            **({"status": status} if status else {}),
            **({"failure_type": failure_type} if failure_type else {}),
            **({"line": line} if line else {}),
        }
    )
    return _flask_proxy(f"/benchmark/risk-events?{query}")


@app.post("/flask-maintenance-recommendation", tags=["representative-benchmark"])
def flask_maintenance_recommendation_proxy(
    request: MaintenanceRecommendationRequest,
) -> JSONResponse:
    return _flask_proxy(
        "/benchmark/maintenance-recommendation",
        method="POST",
        body=request.model_dump(mode="json"),
    )


def _comparison_rows() -> str:
    cells: list[str] = []
    average_scores = _overall_average_scores()
    for item in COMPARISON_SNAPSHOT["results"]:
        selected = item["framework"] == COMPARISON_SNAPSHOT["selected_framework"]
        badge = '<span class="badge selected">최종 선택</span>' if selected else '<span class="badge">비교 대상</span>'
        cells.append(
            "<tr>"
            f"<td><strong>{escape(item['framework'])}</strong>{badge}</td>"
            f"<td>{item['health_status']}</td>"
            f"<td>{'일치' if item['payload_matches'] else '불일치'}</td>"
            f"<td>{'자동 생성' if item['automatic_openapi'] else '기본 미제공'}</td>"
            f"<td>{'선언·검증' if item['response_schema'] else '수동 처리'}</td>"
            f"<td>{item['implementation_loc']}줄</td>"
            f"<td>{item['median_ms']:.4f}ms</td>"
            f"<td>{item['p95_ms']:.4f}ms</td>"
            f"<td><strong>{average_scores[item['framework']]:.2f}/5</strong>"
            '<span class="weighted">4개 평가 요소 평균</span></td>'
            "</tr>"
        )
    return "".join(cells)


def _full_surface_rows() -> str:
    scope = FULL_SURFACE_SNAPSHOT["scope"]
    fastapi = FULL_SURFACE_SNAPSHOT["fastapi"]
    flask = FULL_SURFACE_SNAPSHOT["flask"]
    rows = [
        {
            "framework": "FastAPI",
            "surface": f"{scope['path_count']}개 경로 / {scope['operation_count']}개 작업",
            "business": f"전체 제품 업무 핸들러 {scope['operation_count']}개",
            "openapi": fastapi["automatic_openapi_operation_count"],
            "validation": fastapi["automatic_request_validation_operation_count"],
            "response": (
                f"JSON {fastapi['automatic_response_schema_operation_count']} · "
                f"binary/SSE {fastapi['non_json_response_contract_operation_count']} · "
                f"no-content {fastapi['no_content_contract_operation_count']}"
            ),
            "response_validation": fastapi[
                "runtime_response_validation_operation_count"
            ],
            "runtime": fastapi["authenticated_probe"]["operation_count"],
            "setup": 0,
            "selected": True,
        },
        {
            "framework": "Flask",
            "surface": f"{scope['path_count']}개 경로 / {flask['registered_operation_count']}개 작업",
            "business": f"전체 제품 업무 핸들러 {flask['business_handler_operation_count']}개",
            "openapi": flask["automatic_openapi_operation_count"],
            "validation": flask["automatic_request_validation_operation_count"],
            "response": flask["automatic_response_schema_operation_count"],
            "response_validation": 0,
            "runtime": flask["registered_operation_count"],
            "setup": flask["manual_business_setup_operation_count"],
            "selected": False,
        },
    ]
    return "".join(
        "<tr>"
        f"<td><strong>{item['framework']}</strong>"
        + ('<span class="badge selected">최종 선택</span>' if item["selected"] else '<span class="badge">라우트 미러</span>')
        + "</td>"
        f"<td>{item['surface']}</td>"
        f"<td>{item['business']}</td>"
        f"<td>{item['openapi']}</td>"
        f"<td>{item['validation']}</td>"
        f"<td>{item['response']}</td>"
        f"<td>{item['response_validation']}</td>"
        f"<td>{item['runtime']}</td>"
        f"<td>{item['setup']}</td>"
        "</tr>"
        for item in rows
    )


def _selection_basis_cards() -> str:
    cards: list[str] = []
    for item in FULL_SURFACE_SNAPSHOT["conclusion"].get("selection_basis", []):
        cards.append(
            '<article class="basis-card">'
            f'<div class="eyebrow">{escape(item["title"])}</div>'
            f'<h3>FastAPI</h3><p>{escape(item["fastapi"])}</p>'
            f'<h3>Flask</h3><p>{escape(item["flask"])}</p>'
            "</article>"
        )
    return "".join(cards)


def _list_items(items: list[str]) -> str:
    return "".join(f"<li>{escape(item)}</li>" for item in items)


def _framework_summary_cards() -> str:
    conclusion = FULL_SURFACE_SNAPSHOT["conclusion"]
    summaries = conclusion["framework_summaries"]
    totals = conclusion["evaluation"]["totals"]
    cards: list[str] = []
    for key, label, badge in (
        ("fastapi", "FastAPI", "최종 선택"),
        ("flask", "Flask", "비교 대상"),
    ):
        item = summaries[key]
        cards.append(
            f'<article class="framework-card {key}">'
            '<div class="framework-head">'
            f'<div><span class="badge {"selected" if key == "fastapi" else ""}">{badge}</span>'
            f'<h3>{label}</h3></div>'
            f'<strong class="total-score">{totals[key]}<small>/100</small></strong>'
            "</div>"
            '<div class="result-block"><h4>실제 테스트 결과</h4>'
            f'<ul>{_list_items(item["tested_results"])}</ul></div>'
            '<div class="pros-cons">'
            f'<div class="pros"><h4>장점</h4><ul>{_list_items(item["advantages"])}</ul></div>'
            f'<div class="cons"><h4>단점</h4><ul>{_list_items(item["disadvantages"])}</ul></div>'
            "</div>"
            "</article>"
        )
    return "".join(cards)


def _weighted_score_rows() -> str:
    criteria = FULL_SURFACE_SNAPSHOT["conclusion"]["evaluation"]["criteria"]
    rows: list[str] = []
    for item in criteria:
        fastapi_weighted = item["weight"] * item["fastapi_score"] / 5
        flask_weighted = item["weight"] * item["flask_score"] / 5
        rows.append(
            "<tr>"
            f'<td><strong>{escape(item["title"])}</strong></td>'
            f'<td><strong>{item["weight"]}%</strong></td>'
            f'<td class="evidence-cell">{escape(item["observed_result"])}</td>'
            '<td class="framework-evaluation fastapi-evaluation">'
            f'<strong class="criterion-score">{item["fastapi_score"]}/5</strong>'
            f'<span class="weighted">{fastapi_weighted:g}점 반영</span>'
            f'<p>{escape(item["fastapi_reason"])}</p></td>'
            '<td class="framework-evaluation flask-evaluation">'
            f'<strong class="criterion-score">{item["flask_score"]}/5</strong>'
            f'<span class="weighted">{flask_weighted:g}점 반영</span>'
            f'<p>{escape(item["flask_reason"])}</p></td>'
            "</tr>"
        )
    return "".join(rows)


def _representative_performance_rows() -> str:
    rows: list[str] = []
    for feature in REPRESENTATIVE_BENCHMARK.get("features", {}).values():
        for framework in ("FastAPI", "Flask"):
            item = feature.get("results", {}).get(framework, {})
            sequential = item.get("sequential", {})
            concurrent = item.get("concurrent", {})
            score = feature.get("performance_scores", {}).get(framework, "—")
            rows.append(
                "<tr>"
                f"<td><strong>{escape(str(feature.get('title', '—')))}</strong></td>"
                f"<td><strong>{framework}</strong></td>"
                f"<td>{sequential.get('p50_ms', '—')}ms</td>"
                f"<td>{sequential.get('p95_ms', '—')}ms</td>"
                f"<td>{sequential.get('throughput_rps', '—')}</td>"
                f"<td>{concurrent.get('p50_ms', '—')}ms</td>"
                f"<td>{concurrent.get('p95_ms', '—')}ms</td>"
                f"<td>{concurrent.get('p99_ms', '—')}ms</td>"
                f"<td>{concurrent.get('throughput_rps', '—')}</td>"
                f"<td>{concurrent.get('error_rate_percent', '—')}%</td>"
                f"<td><strong>{score}/5</strong></td>"
                "</tr>"
            )
    return "".join(rows)


def _representative_implementation_rows() -> str:
    rows: list[str] = []
    for feature in REPRESENTATIVE_BENCHMARK.get("features", {}).values():
        implementation = feature.get("implementation", {})
        rows.extend(
            [
                "<tr>"
                f"<td><strong>{escape(str(feature.get('title', '—')))}</strong></td>"
                "<td><strong>FastAPI</strong></td>"
                f"<td>{implementation.get('fastapi_adapter_loc', '—')} LOC</td>"
                "<td>선언형 query/body 검증·response_model·OpenAPI</td>"
                "</tr>",
                "<tr>"
                f"<td><strong>{escape(str(feature.get('title', '—')))}</strong></td>"
                "<td><strong>Flask</strong></td>"
                f"<td>{implementation.get('flask_adapter_loc', '—')} LOC</td>"
                "<td>수동 query parser·Pydantic 호출·오류 응답</td>"
                "</tr>",
            ]
        )
    return "".join(rows)


def _representative_feature_cards() -> str:
    cards: list[str] = []
    for feature in REPRESENTATIVE_BENCHMARK.get("features", {}).values():
        scores = feature.get("performance_scores", {})
        parity = feature.get("parity", {})
        cards.append(
            '<article class="feature-card">'
            f'<div class="eyebrow">{escape(str(feature.get("method", "—")))}</div>'
            f'<h3>{escape(str(feature.get("title", "—")))}</h3>'
            f'<code>{escape(str(feature.get("endpoint", "—")))}</code>'
            f'<p>{escape(str(feature.get("comparison_scope", "—")))}</p>'
            f'<div class="feature-score"><span>응답</span><strong>{"일치" if parity.get("responses_equal") else "확인 필요"}</strong></div>'
            f'<div class="feature-score"><span>FastAPI</span><strong>{scores.get("FastAPI", "—")}/5</strong></div>'
            f'<div class="feature-score"><span>Flask</span><strong>{scores.get("Flask", "—")}/5</strong></div>'
            "</article>"
        )
    return "".join(cards)


def _representative_validation_rows() -> str:
    rows: list[str] = []
    for item in REPRESENTATIVE_BENCHMARK.get("validation", {}).get("cases", []):
        statuses = item.get("statuses", {})
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('feature', '—')))}</td>"
            f"<td>{escape(str(item.get('name', '—')))}</td>"
            f"<td>{item.get('expected_status', '—')}</td>"
            f"<td>{statuses.get('FastAPI', '—')}</td>"
            f"<td>{statuses.get('Flask', '—')}</td>"
            f"<td>{'일치' if item.get('status_match') else '불일치'}</td>"
            "</tr>"
        )
    return "".join(rows)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def comparison_page() -> HTMLResponse:
    source = COMPARISON_SNAPSHOT["source"]
    scope = FULL_SURFACE_SNAPSHOT["scope"]
    fastapi_surface = FULL_SURFACE_SNAPSHOT["fastapi"]
    authenticated = fastapi_surface["authenticated_probe"]
    evaluation = FULL_SURFACE_SNAPSHOT["conclusion"]["evaluation"]
    totals = evaluation["totals"]
    representative = REPRESENTATIVE_BENCHMARK
    representative_parity = representative.get("parity", {})
    representative_validation = representative.get("validation", {})
    representative_features = representative.get("features", {})
    representative_environment = representative.get("environment", {})
    first_feature = next(iter(representative_features.values()), {})
    status_summary = " · ".join(
        f"{status} {count}건"
        for status, count in authenticated["status_counts"].items()
    )
    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>FastAPI vs Flask · Week 1 비교 실험</title>
  <style>
    :root {{ color-scheme: dark; --bg:#071018; --panel:#0d1822; --line:#243342; --muted:#94a7b8; --text:#eef5fa; --accent:#67e8c7; --blue:#79a8ff; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:radial-gradient(circle at 15% 0%,#173044 0,transparent 35%),var(--bg); color:var(--text); font:15px/1.6 Inter,ui-sans-serif,system-ui,-apple-system,sans-serif; }}
    main {{ width:min(1180px,calc(100% - 32px)); margin:0 auto; padding:48px 0 72px; }}
    .eyebrow {{ color:var(--accent); font-weight:800; letter-spacing:.13em; font-size:12px; }}
    h1 {{ font-size:clamp(34px,6vw,68px); line-height:1.03; margin:12px 0 20px; letter-spacing:-.045em; }}
    .lead {{ max-width:850px; color:#c7d5df; font-size:18px; }}
    .actions {{ display:flex; flex-wrap:wrap; gap:10px; margin:24px 0 36px; }}
    a.button {{ color:var(--text); text-decoration:none; border:1px solid var(--line); background:#13222e; border-radius:10px; padding:10px 14px; font-weight:700; }}
    a.button.primary {{ color:#04120f; background:var(--accent); border-color:var(--accent); }}
    .grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:24px 0; }}
    .framework-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:18px; margin:18px 0 34px; }}
    .card,.table-wrap,.conclusion {{ border:1px solid var(--line); background:rgba(13,24,34,.9); border-radius:16px; padding:22px; box-shadow:0 18px 60px rgba(0,0,0,.22); }}
    .framework-card {{ border:1px solid var(--line); background:rgba(13,24,34,.82); border-radius:18px; padding:24px; }}
    .framework-card.fastapi {{ border-color:#2d725f; box-shadow:inset 0 1px 0 rgba(103,232,199,.16); }}
    .framework-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap:20px; border-bottom:1px solid var(--line); padding-bottom:18px; }}
    .framework-head h3 {{ margin:6px 0 0; font-size:30px; }}
    .total-score {{ font-size:42px; line-height:1; color:var(--accent); }}
    .framework-card.flask .total-score {{ color:var(--blue); }}
    .total-score small {{ color:var(--muted); font-size:14px; margin-left:3px; }}
    .framework-card h4 {{ margin:20px 0 8px; font-size:14px; letter-spacing:.04em; }}
    .framework-card ul {{ margin:0; padding-left:20px; color:#c7d5df; }}
    .framework-card li + li {{ margin-top:6px; }}
    .pros-cons {{ display:grid; grid-template-columns:1fr 1fr; gap:18px; }}
    .pros h4 {{ color:var(--accent); }}
    .cons h4 {{ color:#f1b4a8; }}
    .decision-model {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin:14px 0 18px; }}
    .score-card {{ border:1px solid var(--line); border-radius:14px; background:#0a141d; padding:18px; }}
    .score-card strong {{ display:block; font-size:34px; margin-top:4px; }}
    .score-card.fastapi strong {{ color:var(--accent); }}
    .score-card.flask strong {{ color:var(--blue); }}
    .weight-note {{ border-left:3px solid var(--accent); background:rgba(103,232,199,.06); padding:14px 16px; margin:12px 0 18px; color:#c7d5df; }}
    .scope-note {{ border:1px solid #3f5264; background:linear-gradient(135deg,rgba(121,168,255,.10),rgba(13,24,34,.9)); border-radius:16px; padding:20px; margin:24px 0 34px; }}
    .scope-note strong {{ color:var(--blue); }}
    .benchmark-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin:16px 0 18px; }}
    .benchmark-card {{ border:1px solid var(--line); border-radius:14px; padding:18px; background:#0a141d; }}
    .benchmark-card span {{ display:block; color:var(--muted); font-size:13px; }}
    .benchmark-card strong {{ display:block; margin-top:5px; font-size:25px; }}
    .benchmark-card.fast strong {{ color:var(--accent); }}
    .benchmark-card.flask strong {{ color:var(--blue); }}
    .feature-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; margin:16px 0 22px; }}
    .feature-card {{ border:1px solid var(--line); border-radius:16px; background:rgba(13,24,34,.86); padding:20px; min-width:0; }}
    .feature-card h3 {{ margin:6px 0 10px; font-size:20px; }}
    .feature-card code {{ display:block; overflow-wrap:anywhere; color:#c6f7ea; font-size:12px; }}
    .feature-card p {{ color:var(--muted); min-height:48px; }}
    .feature-score {{ display:flex; align-items:center; justify-content:space-between; gap:12px; border-top:1px solid var(--line); padding-top:8px; margin-top:8px; }}
    .feature-score span {{ color:var(--muted); font-size:12px; }}
    .feature-score strong {{ font-size:14px; }}
    .card strong {{ display:block; font-size:26px; margin-top:7px; }}
    .card span {{ color:var(--muted); }}
    .live {{ display:inline-flex; align-items:center; gap:7px; font-weight:800; }}
    .dot {{ width:9px; height:9px; border-radius:50%; background:#f4b942; box-shadow:0 0 0 4px rgba(244,185,66,.12); }}
    .dot.ok {{ background:#4ade80; box-shadow:0 0 0 4px rgba(74,222,128,.12); }}
    .table-wrap {{ overflow:auto; padding:0; }}
    table {{ width:100%; border-collapse:collapse; min-width:930px; }}
    .score-table {{ min-width:980px; }}
    th,td {{ padding:14px 16px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
    th {{ color:var(--muted); font-size:12px; letter-spacing:.05em; text-transform:uppercase; }}
    td:first-child {{ min-width:170px; }}
    .badge {{ display:block; width:max-content; margin-top:5px; color:var(--muted); font-size:11px; }}
    .badge.selected {{ color:var(--accent); }}
    .evidence-cell {{ white-space:normal; min-width:280px; color:#c7d5df; }}
    .framework-evaluation {{ white-space:normal; min-width:240px; vertical-align:top; }}
    .framework-evaluation p {{ margin:10px 0 0; color:#c7d5df; }}
    .criterion-score {{ display:block; font-size:20px; }}
    .fastapi-evaluation .criterion-score {{ color:var(--accent); }}
    .flask-evaluation .criterion-score {{ color:var(--blue); }}
    .weighted {{ display:block; color:var(--muted); font-size:12px; margin-top:3px; }}
    .section-note {{ color:var(--muted); margin:8px 0 14px; }}
    .conclusion {{ margin-top:18px; border-color:#2d725f; background:linear-gradient(135deg,rgba(24,83,68,.45),rgba(13,24,34,.92)); }}
    .conclusion h2 {{ margin:0 0 8px; font-size:26px; }}
    pre {{ overflow:auto; padding:16px; border-radius:12px; background:#050b10; color:#c6f7ea; border:1px solid var(--line); }}
    .note {{ color:var(--muted); font-size:13px; margin-top:16px; }}
    footer {{ color:var(--muted); margin-top:34px; font-size:13px; }}
    @media (max-width:800px) {{ .grid,.framework-grid,.decision-model,.pros-cons,.benchmark-grid,.feature-grid {{ grid-template-columns:1fr; }} main {{ padding-top:30px; }} }}
  </style>
</head>
<body>
<main>
  <div class="eyebrow">WEEK 1 · 프레임워크 비교</div>
  <h1>FastAPI vs Flask<br/>전체 MVP 구현 기준 비교</h1>
  <p class="lead">현재 페이지는 두 층을 분리해 보여줍니다. Dashboard 집계·위험 이벤트 검색·정비 조치 추천 등 대표 기능 <strong>{representative.get('feature_count', 0)}개를 FastAPI와 Flask에 실제로 동일 구현</strong>해 기능·검증·성능을 대칭 비교했고, 전체 <strong>{scope['path_count']}개 OpenAPI 경로·{scope['operation_count']}개 HTTP 작업</strong>은 FastAPI 제품 구현 현황과 Flask route mirror 범위를 구분해 표시합니다.</p>
  <div class="actions">
    <a class="button primary" href="https://dashboard.oosu.dev/docs">실제 서비스 162경로 Swagger</a>
    <a class="button" href="/docs">비교 화면 Swagger</a>
    <a class="button" href="/health">FastAPI /health</a>
    <a class="button" href="/flask-health">Flask /health 프록시</a>
    <a class="button" href="/benchmark/manufacturing-dashboard">FastAPI 대표 Dashboard API</a>
    <a class="button" href="/flask-dashboard">Flask 대표 Dashboard API</a>
    <a class="button" href="/benchmark/risk-events?risk_threshold=0.6&status=warning">FastAPI 위험 검색 API</a>
    <a class="button" href="/flask-risk-events?risk_threshold=0.6&status=warning">Flask 위험 검색 API</a>
    <a class="button" href="/representative-benchmark.json">대표 기능 3종 실측 JSON</a>
    <a class="button" href="/full-comparison.json">162경로 전수 비교 JSON</a>
    <a class="button" href="/comparison.json">전체 비교 JSON</a>
  </div>

  <section class="grid">
    <article class="card"><span>전체 API 표면</span><strong>{scope['path_count']}개 경로</strong><span>{scope['operation_count']}개 HTTP 작업</span></article>
    <article class="card"><span>인증 전수 프로브</span><strong>{authenticated['operation_count']} / {scope['operation_count']}</strong><span>{status_summary}</span></article>
    <article class="card"><span>처리되지 않은 오류</span><strong>{authenticated['unhandled_server_error_count']}건</strong><span>SQLite에서 PostgreSQL 전용 503 {authenticated['expected_503_count']}건은 명시적인 기능 제한 응답</span></article>
    <article class="card"><span>기준선 실험</span><strong>GET /health</strong><div class="live"><i id="fast-dot" class="dot"></i><span id="fast-live">FastAPI 확인 중</span></div><div class="live"><i id="flask-dot" class="dot"></i><span id="flask-live">Flask 확인 중</span></div></article>
  </section>

  <section class="scope-note">
    <strong>비교 범위 구분</strong><br/>
    대표 기능 3개는 같은 GS fixture, 같은 risk snapshot, 같은 업무 함수를 양쪽에 연결한 실제 대칭 비교입니다. 반면 전체 172개 작업은 FastAPI에만 제품 업무 로직이 있고 Flask에는 route mirror만 있으므로, 전체 성능을 양쪽이 모두 구현한 것처럼 표현하지 않습니다.
  </section>

  <h2>1. 서로 다른 대표 기능 3개 실제 양방향 구현</h2>
  <p class="lead"><code>/app/projects/manufacturing-demo-project</code>의 주요 사용 패턴을 반영해 ① 집계·중첩 JSON, ② 필터·정렬·페이지네이션, ③ POST body 검증·업무 판단이라는 서로 다른 성격의 기능을 비교했습니다.</p>
  <section class="benchmark-grid">
    <article class="benchmark-card"><span>대표 기능</span><strong>{representative.get('feature_count', '—')}개</strong><span>GET 2개 · POST 1개</span></article>
    <article class="benchmark-card"><span>정상 응답 계약</span><strong>{'3/3 일치' if representative_parity.get('all_feature_responses_equal') else '확인 필요'}</strong><span>canonical SHA-256 비교</span></article>
    <article class="benchmark-card fast"><span>FastAPI 3개 성능 평균</span><strong>{representative.get('performance_scores', {}).get('FastAPI', '—')}/5</strong></article>
    <article class="benchmark-card flask"><span>Flask 3개 성능 평균</span><strong>{representative.get('performance_scores', {}).get('Flask', '—')}/5</strong></article>
  </section>
  <section class="feature-grid">{_representative_feature_cards()}</section>
  <section class="table-wrap">
    <table>
      <thead><tr><th>대표 기능</th><th>프레임워크</th><th>순차 p50</th><th>순차 p95</th><th>순차 RPS</th><th>동시 p50</th><th>동시 p95</th><th>동시 p99</th><th>동시 RPS</th><th>오류율</th><th>기능 점수</th></tr></thead>
      <tbody>{_representative_performance_rows()}</tbody>
    </table>
  </section>
  <p class="section-note">각 기능마다 서버를 별도 프로세스로 실행하고 순차 {first_feature.get('results', {}).get('FastAPI', {}).get('sequential', {}).get('requests_per_round', '—')}회 × {first_feature.get('results', {}).get('FastAPI', {}).get('sequential', {}).get('round_count', '—')}라운드, 동시성 10도 같은 횟수로 요청했습니다. 기능과 라운드마다 FastAPI 우선·Flask 우선 순서를 교차했고, 두 서버 모두 매 요청 새 연결을 사용했습니다. 환경: {escape(str(representative_environment.get('platform', '—')))} · Python {escape(str(representative_environment.get('python', '—')))}.</p>
  <section class="table-wrap">
    <table>
      <thead><tr><th>대표 기능</th><th>프레임워크</th><th>Adapter 코드량</th><th>검증·계약 구현</th></tr></thead>
      <tbody>{_representative_implementation_rows()}</tbody>
    </table>
  </section>
  <h3>오류·경계값 계약 검증</h3>
  <section class="table-wrap">
    <table>
      <thead><tr><th>기능</th><th>검증 사례</th><th>기대 HTTP</th><th>FastAPI</th><th>Flask</th><th>결과</th></tr></thead>
      <tbody>{_representative_validation_rows()}</tbody>
    </table>
  </section>
  <p class="section-note">입력 범위 초과, 지원하지 않는 정렬값, 정상적인 빈 검색 결과, 잘못된 POST enum, 존재하지 않는 이벤트 등 {representative_validation.get('case_count', '—')}개 사례를 확인했습니다. 상태 계약은 {'모두 일치했습니다' if representative_validation.get('all_statuses_match') else '추가 확인이 필요합니다'}. 기능별 네 성능 지표를 같은 비중으로 계산한 후 세 기능을 다시 평균한 결과는 FastAPI {representative.get('performance_scores', {}).get('FastAPI', '—')}/5, Flask {representative.get('performance_scores', {}).get('Flask', '—')}/5입니다. 운영 환경 벤치마크가 아니라 로컬 framework·server stack 비교이며 원격 DB와 외부 모델 호출은 제외했습니다.</p>

  <h2>2. 프레임워크별 실제 테스트 결과와 장단점</h2>
  <p class="lead">대표 기능 3개는 양쪽 모두 실제 구현했습니다. 전체 제품 수준에서는 FastAPI 172개 업무 작업과 Flask 3개 대표 업무 API + 172개 route mirror를 구분해 평가합니다.</p>
  <section class="framework-grid">{_framework_summary_cards()}</section>

  <h2>3. 어떤 요소에 더 큰 비중을 뒀는가</h2>
  <div class="weight-note"><strong>네 항목을 동일하게 평가했습니다.</strong> 개발 생산성·API 계약 자동화·검증 안정성·대표 업무 API 성능에 각각 {evaluation['equal_weight_per_criterion']}%를 배정했습니다. 성능은 각 기능의 순차 p95·처리량과 동시성 10 p95·처리량을 같은 비중으로 계산한 뒤 세 기능 평균을 사용했습니다.</div>
  <section class="decision-model">
    <article class="score-card fastapi"><span>FastAPI 가중 합계</span><strong>{totals['fastapi']} / 100</strong><span>개발 구조·계약·검증에서 우세</span></article>
    <article class="score-card flask"><span>Flask 가중 합계</span><strong>{totals['flask']} / 100</strong><span>대표 업무 API 성능에서 근소 우세</span></article>
  </section>
  <section class="table-wrap">
    <table class="score-table">
      <thead><tr><th>평가 요소</th><th>가중치</th><th>실제 테스트 결과</th><th>FastAPI 평가</th><th>Flask 평가</th></tr></thead>
      <tbody>{_weighted_score_rows()}</tbody>
    </table>
  </section>

  <h2>4. FastAPI 전체 제품 구현 현황과 Flask 구성 범위</h2>
  <p class="section-note">아래 표는 전체 제품 성능의 대칭 비교가 아닙니다. FastAPI의 실제 제품 구현 범위와 Flask에서 같은 URL 구조가 등록되는지, 추가로 어떤 기능을 구성해야 하는지 보여주는 범위 분석입니다.</p>
  <section class="table-wrap">
    <table>
      <thead><tr><th>프레임워크</th><th>API 표면</th><th>업무 핸들러</th><th>자동 OpenAPI</th><th>요청 자동 검증</th><th>성공 응답 계약</th><th>응답 런타임 검증</th><th>전수 프로브</th><th>추가 업무 구성</th></tr></thead>
      <tbody>{_full_surface_rows()}</tbody>
    </table>
  </section>

  <h2>5. 참고: 동일 `/health` 최소 응답 비교</h2>
  <p class="section-note"><code>/health</code>는 최소 framework overhead를 살펴보는 이전 기준선입니다. 최종 성능 평가는 위의 대표 기능 3개 실제 HTTP 측정을 사용합니다. 마지막 열은 3번 평가표의 네 점수를 평균한 종합점수입니다.</p>
  <section class="table-wrap">
    <table>
      <thead><tr><th>프레임워크</th><th>HTTP</th><th>응답 일치</th><th>OpenAPI</th><th>응답 Schema</th><th>코드 줄 수</th><th>p50*</th><th>p95*</th><th>종합 평균*</th></tr></thead>
      <tbody>{_comparison_rows()}</tbody>
    </table>
  </section>

  <section class="conclusion">
    <div class="eyebrow">최종 선정</div>
    <h2>최종 선택: FastAPI</h2>
    <p>{escape(FULL_SURFACE_SNAPSHOT['conclusion']['reason'])}</p>
    <p><strong>Flask가 우세한 부분:</strong> 대표 기능 3개의 평균 성능 점수와 작은 framework의 단순성입니다.</p>
    <p><strong>FastAPI가 우세한 부분:</strong> 대표 기능 3개의 총 adapter 코드량, 자동 계약·검증과 전체 제품 구조화입니다.</p>
    <p class="note">{escape(FULL_SURFACE_SNAPSHOT['conclusion']['limitation'])}</p>
  </section>

  <footer>소스 · {source['repository']} · {source['branch']} · 최초 실험 커밋 {source['commit']}</footer>
</main>
<script>
async function probe(url, dotId, textId, label) {{
  const dot = document.getElementById(dotId); const text = document.getElementById(textId);
  try {{ const response = await fetch(url, {{cache:'no-store'}}); const body = await response.json();
    if (!response.ok || body.status !== 'ok') throw new Error('not ready');
    dot.classList.add('ok'); text.textContent = `${{label}} HTTP ${{response.status}} · 정상`;
  }} catch (_) {{ text.textContent = `${{label}} 응답 확인 필요`; }}
}}
probe('/health','fast-dot','fast-live','FastAPI');
probe('/flask-health','flask-dot','flask-live','Flask');
</script>
</body>
</html>"""
    return HTMLResponse(html)

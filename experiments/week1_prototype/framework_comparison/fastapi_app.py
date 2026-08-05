"""FastAPI implementation and public comparison report for Week 1."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from html import escape
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from .contracts import HEALTH_PAYLOAD, HealthResponse


FULL_SURFACE_SNAPSHOT_PATH = Path(__file__).with_name("full_surface_snapshot.json")


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
            "rubric_score": 5,
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
            "rubric_score": 3,
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


@app.get("/comparison.json", tags=["comparison"])
def comparison_json() -> dict:
    return {
        "baseline": COMPARISON_SNAPSHOT,
        "full_surface": FULL_SURFACE_SNAPSHOT,
    }


@app.get("/full-comparison.json", tags=["comparison"])
def full_comparison_json() -> dict:
    return FULL_SURFACE_SNAPSHOT


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


def _comparison_rows() -> str:
    cells: list[str] = []
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
            f"<td><strong>{item['rubric_score']}/5</strong></td>"
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
            "business": f"실제 업무 핸들러 {scope['operation_count']}개",
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
            "business": f"실제 업무 핸들러 {flask['business_handler_operation_count']}개",
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
            f'<td><strong>{item["fastapi_score"]}/5</strong><span class="weighted">{fastapi_weighted:g}점 반영</span></td>'
            f'<td class="reason-cell">{escape(item["fastapi_reason"])}</td>'
            f'<td><strong>{item["flask_score"]}/5</strong><span class="weighted">{flask_weighted:g}점 반영</span></td>'
            f'<td class="reason-cell">{escape(item["flask_reason"])}</td>'
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
    .card strong {{ display:block; font-size:26px; margin-top:7px; }}
    .card span {{ color:var(--muted); }}
    .live {{ display:inline-flex; align-items:center; gap:7px; font-weight:800; }}
    .dot {{ width:9px; height:9px; border-radius:50%; background:#f4b942; box-shadow:0 0 0 4px rgba(244,185,66,.12); }}
    .dot.ok {{ background:#4ade80; box-shadow:0 0 0 4px rgba(74,222,128,.12); }}
    .table-wrap {{ overflow:auto; padding:0; }}
    table {{ width:100%; border-collapse:collapse; min-width:930px; }}
    .score-table {{ min-width:1280px; }}
    th,td {{ padding:14px 16px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
    th {{ color:var(--muted); font-size:12px; letter-spacing:.05em; text-transform:uppercase; }}
    td:first-child {{ min-width:170px; }}
    .badge {{ display:block; width:max-content; margin-top:5px; color:var(--muted); font-size:11px; }}
    .badge.selected {{ color:var(--accent); }}
    .evidence-cell,.reason-cell {{ white-space:normal; min-width:260px; color:#c7d5df; }}
    .weighted {{ display:block; color:var(--muted); font-size:12px; margin-top:3px; }}
    .conclusion {{ margin-top:18px; border-color:#2d725f; background:linear-gradient(135deg,rgba(24,83,68,.45),rgba(13,24,34,.92)); }}
    .conclusion h2 {{ margin:0 0 8px; font-size:26px; }}
    pre {{ overflow:auto; padding:16px; border-radius:12px; background:#050b10; color:#c6f7ea; border:1px solid var(--line); }}
    .note {{ color:var(--muted); font-size:13px; margin-top:16px; }}
    footer {{ color:var(--muted); margin-top:34px; font-size:13px; }}
    @media (max-width:800px) {{ .grid,.framework-grid,.decision-model,.pros-cons {{ grid-template-columns:1fr; }} main {{ padding-top:30px; }} }}
  </style>
</head>
<body>
<main>
  <div class="eyebrow">WEEK 1 · 프레임워크 비교</div>
  <h1>FastAPI vs Flask<br/>전체 MVP 구현 기준 비교</h1>
  <p class="lead">초기 <code>GET /health</code> 최소 비교를 기준선으로만 남기고, 현재 Ontology Dashboard MVP의 <strong>{scope['path_count']}개 OpenAPI 경로·{scope['operation_count']}개 HTTP 작업 전체</strong>를 비교 대상으로 확장했습니다. FastAPI와 bare Flask의 개발 구조, 계약 자동화, 검증 안정성, 경량성을 같은 비중으로 평가했습니다.</p>
  <div class="actions">
    <a class="button primary" href="https://dashboard.oosu.dev/docs">실제 서비스 162경로 Swagger</a>
    <a class="button" href="/docs">비교 화면 Swagger</a>
    <a class="button" href="/health">FastAPI /health</a>
    <a class="button" href="/flask-health">Flask /health 프록시</a>
    <a class="button" href="/full-comparison.json">162경로 전수 비교 JSON</a>
    <a class="button" href="/comparison.json">전체 비교 JSON</a>
  </div>

  <section class="grid">
    <article class="card"><span>전체 API 표면</span><strong>{scope['path_count']}개 경로</strong><span>{scope['operation_count']}개 HTTP 작업</span></article>
    <article class="card"><span>인증 전수 프로브</span><strong>{authenticated['operation_count']} / {scope['operation_count']}</strong><span>{status_summary}</span></article>
    <article class="card"><span>처리되지 않은 오류</span><strong>{authenticated['unhandled_server_error_count']}건</strong><span>SQLite에서 PostgreSQL 전용 503 {authenticated['expected_503_count']}건은 명시적인 기능 제한 응답</span></article>
    <article class="card"><span>기준선 실험</span><strong>GET /health</strong><div class="live"><i id="fast-dot" class="dot"></i><span id="fast-live">FastAPI 확인 중</span></div><div class="live"><i id="flask-dot" class="dot"></i><span id="flask-live">Flask 확인 중</span></div></article>
  </section>

  <h2>1. 프레임워크별 실제 테스트 결과와 장단점</h2>
  <p class="lead">먼저 각 프레임워크에서 실제로 확인한 결과를 분리했습니다. Flask의 전체 제품 로직을 구현한 것이 아니므로, Flask 점수는 <strong>bare Flask의 기본 제공 범위와 새 제품을 구성할 때 필요한 추가 설정</strong>을 기준으로 평가했습니다.</p>
  <section class="framework-grid">{_framework_summary_cards()}</section>

  <h2>2. 어떤 요소에 더 큰 비중을 뒀는가</h2>
  <div class="weight-note"><strong>네 항목을 동일하게 평가했습니다.</strong> 개발 완성도·API 계약 자동화·검증 안정성·경량성에 각각 {evaluation['equal_weight_per_criterion']}%를 배정했습니다. 모든 프로젝트에 FastAPI가 더 낫다는 뜻은 아니며, 이번 실험에서 확인한 기본 제공 범위와 개발 방식에 대한 비교입니다.</div>
  <section class="decision-model">
    <article class="score-card fastapi"><span>FastAPI 가중 합계</span><strong>{totals['fastapi']} / 100</strong><span>개발 구조·계약·검증에서 우세</span></article>
    <article class="score-card flask"><span>Flask 가중 합계</span><strong>{totals['flask']} / 100</strong><span>최소 API 경량성에서 우세</span></article>
  </section>
  <section class="table-wrap">
    <table class="score-table">
      <thead><tr><th>평가 요소</th><th>가중치</th><th>실제 테스트 결과</th><th>FastAPI 점수</th><th>FastAPI 판단</th><th>Flask 점수</th><th>Flask 판단</th></tr></thead>
      <tbody>{_weighted_score_rows()}</tbody>
    </table>
  </section>

  <h2>3. 전체 162개 경로·172개 작업의 원본 수치</h2>
  <section class="table-wrap">
    <table>
      <thead><tr><th>프레임워크</th><th>API 표면</th><th>업무 핸들러</th><th>자동 OpenAPI</th><th>요청 자동 검증</th><th>성공 응답 계약</th><th>응답 런타임 검증</th><th>전수 프로브</th><th>추가 업무 구성</th></tr></thead>
      <tbody>{_full_surface_rows()}</tbody>
    </table>
  </section>

  <h2>4. 참고: 동일 `/health` 최소 응답 비교</h2>
  <section class="table-wrap">
    <table>
      <thead><tr><th>프레임워크</th><th>HTTP</th><th>응답 일치</th><th>OpenAPI</th><th>응답 Schema</th><th>코드 줄 수</th><th>p50*</th><th>p95*</th><th>점수</th></tr></thead>
      <tbody>{_comparison_rows()}</tbody>
    </table>
  </section>

  <section class="conclusion">
    <div class="eyebrow">최종 선정</div>
    <h2>최종 선택: FastAPI</h2>
    <p>{escape(FULL_SURFACE_SNAPSHOT['conclusion']['reason'])}</p>
    <p><strong>Flask가 우세한 부분:</strong> 단순 endpoint의 가벼움과 로컬 인프로세스 응답 속도입니다.</p>
    <p><strong>FastAPI가 우세한 부분:</strong> 큰 API의 구조화, 코드와 Swagger가 공유하는 계약 자동화, 요청·응답 오류를 조기에 발견하는 검증 안정성입니다. 네 항목의 가중치는 모두 동일합니다.</p>
    <p class="note">{escape(FULL_SURFACE_SNAPSHOT['conclusion']['limitation'])} <code>/health</code> 지연시간은 로컬 인프로세스 참고값이며 최종 선정 점수에 사용하지 않았습니다.</p>
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

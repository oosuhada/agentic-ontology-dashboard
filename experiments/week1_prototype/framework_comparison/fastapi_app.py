"""FastAPI implementation and public comparison report for Week 1."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from html import escape

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from .contracts import HEALTH_PAYLOAD, HealthResponse


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
    version="1.1.0",
    description="동일 /health 계약으로 FastAPI와 Flask를 비교한 실험 결과입니다.",
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(**HEALTH_PAYLOAD)


@app.get("/comparison.json", tags=["comparison"])
def comparison_json() -> dict:
    return COMPARISON_SNAPSHOT


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


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def comparison_page() -> HTMLResponse:
    payload = json.dumps(HEALTH_PAYLOAD, ensure_ascii=False, indent=2)
    source = COMPARISON_SNAPSHOT["source"]
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
    .grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; margin:24px 0; }}
    .card,.table-wrap,.conclusion {{ border:1px solid var(--line); background:rgba(13,24,34,.9); border-radius:16px; padding:22px; box-shadow:0 18px 60px rgba(0,0,0,.22); }}
    .card strong {{ display:block; font-size:26px; margin-top:7px; }}
    .card span {{ color:var(--muted); }}
    .live {{ display:inline-flex; align-items:center; gap:7px; font-weight:800; }}
    .dot {{ width:9px; height:9px; border-radius:50%; background:#f4b942; box-shadow:0 0 0 4px rgba(244,185,66,.12); }}
    .dot.ok {{ background:#4ade80; box-shadow:0 0 0 4px rgba(74,222,128,.12); }}
    .table-wrap {{ overflow:auto; padding:0; }}
    table {{ width:100%; border-collapse:collapse; min-width:930px; }}
    th,td {{ padding:14px 16px; border-bottom:1px solid var(--line); text-align:left; white-space:nowrap; }}
    th {{ color:var(--muted); font-size:12px; letter-spacing:.05em; text-transform:uppercase; }}
    td:first-child {{ min-width:170px; }}
    .badge {{ display:block; width:max-content; margin-top:5px; color:var(--muted); font-size:11px; }}
    .badge.selected {{ color:var(--accent); }}
    .conclusion {{ margin-top:18px; border-color:#2d725f; background:linear-gradient(135deg,rgba(24,83,68,.45),rgba(13,24,34,.92)); }}
    .conclusion h2 {{ margin:0 0 8px; font-size:26px; }}
    pre {{ overflow:auto; padding:16px; border-radius:12px; background:#050b10; color:#c6f7ea; border:1px solid var(--line); }}
    .note {{ color:var(--muted); font-size:13px; margin-top:16px; }}
    footer {{ color:var(--muted); margin-top:34px; font-size:13px; }}
    @media (max-width:800px) {{ .grid {{ grid-template-columns:1fr; }} main {{ padding-top:30px; }} }}
  </style>
</head>
<body>
<main>
  <div class="eyebrow">WEEK 1 · FRAMEWORK COMPARISON</div>
  <h1>FastAPI vs Flask<br/>동일 조건 비교 실험</h1>
  <p class="lead">같은 <code>GET /health</code> 경로와 JSON 계약을 두 프레임워크에 각각 구현했습니다. 단순 속도만으로 결론을 내리지 않고, 응답 계약·자동 문서·테스트·향후 예측 API 확장까지 포함해 결과물 완성도를 비교했습니다.</p>
  <div class="actions">
    <a class="button primary" href="/docs">FastAPI Swagger 열기</a>
    <a class="button" href="/health">FastAPI /health</a>
    <a class="button" href="/flask-health">Flask /health 프록시</a>
    <a class="button" href="/comparison.json">비교 JSON</a>
    <a class="button" href="https://github.com/{source['repository']}/tree/{source['branch']}">GitHub 브랜치</a>
  </div>

  <section class="grid">
    <article class="card"><span>동일 계약</span><strong>GET /health</strong><div class="live"><i id="fast-dot" class="dot"></i><span id="fast-live">FastAPI 확인 중</span></div></article>
    <article class="card"><span>비교 실행</span><strong>500 iterations</strong><div class="live"><i id="flask-dot" class="dot"></i><span id="flask-live">Flask 확인 중</span></div></article>
    <article class="card"><span>계약·문서 평가</span><strong>FastAPI 5 / Flask 3</strong><span>OpenAPI와 응답 스키마 포함</span></article>
  </section>

  <section class="table-wrap">
    <table>
      <thead><tr><th>Framework</th><th>HTTP</th><th>Payload</th><th>OpenAPI</th><th>Response schema</th><th>Endpoint LOC</th><th>p50*</th><th>p95*</th><th>Score</th></tr></thead>
      <tbody>{_comparison_rows()}</tbody>
    </table>
  </section>

  <section class="conclusion">
    <div class="eyebrow">SELECTION</div>
    <h2>최종 선택: FastAPI</h2>
    <p>{escape(COMPARISON_SNAPSHOT['selection_reason'])}</p>
    <pre>{escape(payload)}</pre>
    <p class="note">* 지연시간은 로컬 인프로세스 참고값이며 운영 성능 결론이 아닙니다. 이 실험에서는 Flask가 최소 응답에서 더 가벼웠고, FastAPI는 계약·문서화·확장성에서 더 높은 평가를 받았습니다.</p>
  </section>

  <footer>Source · {source['repository']} · {source['branch']} · initial commit {source['commit']}</footer>
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

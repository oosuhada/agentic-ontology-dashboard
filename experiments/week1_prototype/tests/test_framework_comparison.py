from fastapi.testclient import TestClient

from framework_comparison.compare import run_comparison
from framework_comparison.contracts import HEALTH_PAYLOAD
from framework_comparison.fastapi_app import app as fastapi_app
from framework_comparison.flask_app import app as flask_app


def test_health_contract_is_identical() -> None:
    fastapi_response = TestClient(fastapi_app).get("/health")
    flask_response = flask_app.test_client().get("/health")

    assert fastapi_response.status_code == 200
    assert flask_response.status_code == 200
    assert fastapi_response.json() == HEALTH_PAYLOAD
    assert flask_response.get_json() == HEALTH_PAYLOAD


def test_fastapi_generates_openapi_and_response_schema() -> None:
    payload = TestClient(fastapi_app).get("/openapi.json").json()
    schema = payload["paths"]["/health"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]

    assert schema
    assert schema.get("$ref", "").endswith("/HealthResponse")


def test_flask_minimal_app_does_not_generate_openapi_by_default() -> None:
    response = flask_app.test_client().get("/openapi.json")
    assert response.status_code == 404


def test_representative_dashboard_contract_is_identical() -> None:
    fastapi_client = TestClient(fastapi_app)
    flask_client = flask_app.test_client()

    fastapi_response = fastapi_client.get(
        "/benchmark/manufacturing-dashboard?risk_threshold=0.0&limit=8"
    )
    flask_response = flask_client.get(
        "/benchmark/manufacturing-dashboard?risk_threshold=0.0&limit=8"
    )

    assert fastapi_response.status_code == 200
    assert flask_response.status_code == 200
    assert fastapi_response.json() == flask_response.get_json()
    assert fastapi_response.json()["summary"]["visible_events"] == 8
    assert len(fastapi_response.json()["sensor_series"]) == 31


def test_representative_dashboard_rejects_invalid_limit_in_both_frameworks() -> None:
    fastapi_response = TestClient(fastapi_app).get(
        "/benchmark/manufacturing-dashboard?limit=0"
    )
    flask_response = flask_app.test_client().get(
        "/benchmark/manufacturing-dashboard?limit=0"
    )

    assert fastapi_response.status_code == 422
    assert flask_response.status_code == 422


def test_comparison_selects_fastapi_on_contract_rubric() -> None:
    report = run_comparison(iterations=25)
    assert report["selected_framework"] == "FastAPI"
    by_name = {item["framework"]: item for item in report["results"]}
    assert by_name["FastAPI"]["rubric_score"] > by_name["Flask"]["rubric_score"]



def test_public_comparison_page_and_json_are_available() -> None:
    client = TestClient(fastapi_app)
    page = client.get("/")
    report = client.get("/comparison.json")
    full_report = client.get("/full-comparison.json")

    assert page.status_code == 200
    assert "FastAPI vs Flask" in page.text
    assert "162개 OpenAPI 경로" in page.text
    assert "동일 제조 Dashboard API 실제 양방향 구현" in page.text
    assert "프레임워크별 실제 테스트 결과와 장단점" in page.text
    assert "어떤 요소에 더 큰 비중을 뒀는가" in page.text
    assert "개발 완성도와 구현 생산성" in page.text
    assert "대표 업무 API 성능과 경량성" in page.text
    assert "FastAPI 가중 합계" in page.text
    assert "98.9 / 100" in page.text
    assert "Flask 가중 합계" in page.text
    assert "69.7 / 100" in page.text
    assert "FastAPI 평가" in page.text
    assert "Flask 평가" in page.text
    assert "<th>FastAPI 점수</th>" not in page.text
    assert "<th>FastAPI 판단</th>" not in page.text
    assert "<th>Flask 점수</th>" not in page.text
    assert "<th>Flask 판단</th>" not in page.text
    assert "종합 평균*" in page.text
    assert "4.95/5" in page.text
    assert "3.49/5" in page.text
    assert "4개 평가 요소 평균" in page.text
    assert "응답 계약 일치" in page.text
    assert "완전 일치" in page.text
    assert "대표 API 실측 JSON" in page.text
    assert "GitHub 브랜치" not in page.text
    assert "실제 업무 핸들러 172개 실행" in page.text
    assert "JSON 168" in page.text
    assert "최종 선택: FastAPI" in page.text
    assert "The selection now covers" not in page.text
    assert report.status_code == 200
    assert report.json()["baseline"]["selected_framework"] == "FastAPI"
    assert report.json()["baseline"]["overall_average_scores"] == {
        "FastAPI": 4.95,
        "Flask": 3.49,
    }
    representative = report.json()["representative_dashboard"]
    assert representative["parity"]["responses_equal"] is True
    assert representative["results"]["FastAPI"]["sequential"]["round_count"] == 3
    assert representative["results"]["Flask"]["concurrent"]["error_count"] == 0
    assert report.json()["full_surface"]["scope"]["operation_count"] == 172
    assert full_report.status_code == 200
    assert full_report.json()["scope"]["path_count"] == 162
    assert full_report.json()["fastapi"]["automatic_response_schema_operation_count"] == 168
    assert full_report.json()["fastapi"]["success_contract_operation_count"] == 172
    assert full_report.json()["conclusion"]["selection_basis"]
    evaluation = full_report.json()["conclusion"]["evaluation"]
    assert evaluation["totals"] == {"fastapi": 98.9, "flask": 69.7}
    assert evaluation["equal_weight_per_criterion"] == 25
    assert len(evaluation["criteria"]) == 4

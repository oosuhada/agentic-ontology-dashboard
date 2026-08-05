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
    assert "프레임워크별 실제 테스트 결과와 장단점" in page.text
    assert "어떤 요소에 더 큰 비중을 뒀는가" in page.text
    assert "개발 완성도와 구현 생산성" in page.text
    assert "최소 API 경량성과 단순 응답 속도" in page.text
    assert "FastAPI 가중 합계" in page.text
    assert "85 / 100" in page.text
    assert "Flask 가중 합계" in page.text
    assert "60 / 100" in page.text
    assert "GitHub 브랜치" not in page.text
    assert "실제 업무 핸들러 172개 실행" in page.text
    assert "JSON 168" in page.text
    assert "최종 선택: FastAPI" in page.text
    assert "The selection now covers" not in page.text
    assert report.status_code == 200
    assert report.json()["baseline"]["selected_framework"] == "FastAPI"
    assert report.json()["full_surface"]["scope"]["operation_count"] == 172
    assert full_report.status_code == 200
    assert full_report.json()["scope"]["path_count"] == 162
    assert full_report.json()["fastapi"]["automatic_response_schema_operation_count"] == 168
    assert full_report.json()["fastapi"]["success_contract_operation_count"] == 172
    assert full_report.json()["conclusion"]["selection_basis"]
    evaluation = full_report.json()["conclusion"]["evaluation"]
    assert evaluation["totals"] == {"fastapi": 85, "flask": 60}
    assert evaluation["equal_weight_per_criterion"] == 25
    assert len(evaluation["criteria"]) == 4

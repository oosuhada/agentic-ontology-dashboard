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


def test_risk_event_search_contract_and_validation_are_identical() -> None:
    fastapi_client = TestClient(fastapi_app)
    flask_client = flask_app.test_client()
    endpoint = (
        "/benchmark/risk-events?risk_threshold=0.6&status=warning&"
        "sort=probability_desc&limit=5&offset=0"
    )

    fastapi_response = fastapi_client.get(endpoint)
    flask_response = flask_client.get(endpoint)

    assert fastapi_response.status_code == 200
    assert flask_response.status_code == 200
    assert fastapi_response.json() == flask_response.get_json()
    assert fastapi_response.json()["total_matching"] == 4
    assert [item["event_id"] for item in fastapi_response.json()["items"]] == [
        "EVT-GS-002",
        "EVT-GS-008",
        "EVT-GS-005",
        "EVT-GS-003",
    ]
    assert fastapi_client.get("/benchmark/risk-events?sort=bad").status_code == 422
    assert flask_client.get("/benchmark/risk-events?sort=bad").status_code == 422


def test_maintenance_recommendation_contract_and_errors_are_identical() -> None:
    fastapi_client = TestClient(fastapi_app)
    flask_client = flask_app.test_client()
    body = {
        "event_id": "EVT-GS-004",
        "operator_role": "process_manager",
        "include_evidence": True,
    }

    fastapi_response = fastapi_client.post(
        "/benchmark/maintenance-recommendation", json=body
    )
    flask_response = flask_client.post(
        "/benchmark/maintenance-recommendation", json=body
    )

    assert fastapi_response.status_code == 200
    assert flask_response.status_code == 200
    assert fastapi_response.json() == flask_response.get_json()
    assert fastapi_response.json()["recommended_decision"] == "review_shutdown"
    assert fastapi_response.json()["requires_shutdown_review"] is True

    invalid = {"event_id": "EVT-GS-004", "operator_role": "bad"}
    assert fastapi_client.post(
        "/benchmark/maintenance-recommendation", json=invalid
    ).status_code == 422
    assert flask_client.post(
        "/benchmark/maintenance-recommendation", json=invalid
    ).status_code == 422

    missing = {"event_id": "EVT-NOT-FOUND", "operator_role": "process_manager"}
    assert fastapi_client.post(
        "/benchmark/maintenance-recommendation", json=missing
    ).status_code == 404
    assert flask_client.post(
        "/benchmark/maintenance-recommendation", json=missing
    ).status_code == 404


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
    assert "서로 다른 대표 기능 3개 실제 양방향 구현" in page.text
    assert "위험 이벤트 검색·필터" in page.text
    assert "정비 조치 추천" in page.text
    assert "오류·경계값 계약 검증" in page.text
    assert "프레임워크별 실제 테스트 결과와 장단점" in page.text
    assert "어떤 요소에 더 큰 비중을 뒀는가" in page.text
    assert "개발 완성도와 구현 생산성" in page.text
    assert "대표 업무 API 성능과 경량성" in page.text
    assert "FastAPI 가중 합계" in page.text
    assert "99.55 / 100" in page.text
    assert "Flask 가중 합계" in page.text
    assert "69.6 / 100" in page.text
    assert "FastAPI 평가" in page.text
    assert "Flask 평가" in page.text
    assert "<th>FastAPI 점수</th>" not in page.text
    assert "<th>FastAPI 판단</th>" not in page.text
    assert "<th>Flask 점수</th>" not in page.text
    assert "<th>Flask 판단</th>" not in page.text
    assert "종합 평균*" in page.text
    assert "4.98/5" in page.text
    assert "3.48/5" in page.text
    assert "4개 평가 요소 평균" in page.text
    assert "정상 응답 계약" in page.text
    assert "3/3 일치" in page.text
    assert "대표 기능 3종 실측 JSON" in page.text
    assert "GitHub 브랜치" not in page.text
    assert "실제 업무 핸들러 172개 실행" in page.text
    assert "JSON 168" in page.text
    assert "최종 선택: FastAPI" in page.text
    assert "The selection now covers" not in page.text
    assert report.status_code == 200
    assert report.json()["baseline"]["selected_framework"] == "FastAPI"
    assert report.json()["baseline"]["overall_average_scores"] == {
        "FastAPI": 4.98,
        "Flask": 3.48,
    }
    representative = report.json()["representative_features"]
    assert representative["feature_count"] == 3
    assert representative["parity"]["all_feature_responses_equal"] is True
    assert representative["validation"]["case_count"] == 5
    assert representative["validation"]["all_statuses_match"] is True
    assert set(representative["features"]) == {
        "manufacturing_dashboard",
        "risk_event_search",
        "maintenance_recommendation",
    }
    assert representative["features"]["manufacturing_dashboard"]["results"][
        "FastAPI"
    ]["sequential"]["round_count"] == 3
    assert representative["features"]["maintenance_recommendation"]["results"][
        "Flask"
    ]["concurrent"]["error_count"] == 0
    assert report.json()["full_surface"]["scope"]["operation_count"] == 172
    assert full_report.status_code == 200
    assert full_report.json()["scope"]["path_count"] == 162
    assert full_report.json()["fastapi"]["automatic_response_schema_operation_count"] == 168
    assert full_report.json()["fastapi"]["success_contract_operation_count"] == 172
    assert full_report.json()["conclusion"]["selection_basis"]
    evaluation = full_report.json()["conclusion"]["evaluation"]
    assert evaluation["totals"] == {"fastapi": 99.55, "flask": 69.6}
    assert evaluation["equal_weight_per_criterion"] == 25
    assert len(evaluation["criteria"]) == 4

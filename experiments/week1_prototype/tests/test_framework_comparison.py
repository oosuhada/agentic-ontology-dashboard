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

    assert page.status_code == 200
    assert "FastAPI vs Flask" in page.text
    assert "최종 선택: FastAPI" in page.text
    assert report.status_code == 200
    assert report.json()["selected_framework"] == "FastAPI"

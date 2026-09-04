from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit


@dataclass
class MinimalResult:
    asset_id: str


class MinimalBatchPayload:
    batch_id = "batch-auth-01"
    results = [MinimalResult(asset_id="CNC-001")]

    def model_dump_json(self) -> str:
        return (
            '{"schema_version":"prediction-result-batch-v1",'
            '"batch_id":"batch-auth-01","results":[{"asset_id":"CNC-001"}]}'
        )

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        return {
            "schema_version": "prediction-result-batch-v1",
            "batch_id": "batch-auth-01",
            "results": [{"asset_id": "CNC-001"}],
        }


def test_prediction_delivery_service_adds_configured_bearer_token(monkeypatch) -> None:
    import urllib.request

    from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
        PredictionDeliveryService,
    )

    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_TOKEN", "receiver-secret")
    captured_req = None

    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def getcode(self) -> int:
            return 202

        def read(self) -> bytes:
            return b'{"validation_status":"accepted"}'

    def mock_urlopen(req, timeout=10.0):
        nonlocal captured_req
        captured_req = req
        return MockResponse()

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    service = PredictionDeliveryService(
        endpoint_url="http://backend.internal/internal/prediction-results"
    )

    response = service.send_once(MinimalBatchPayload())

    assert response["delivered"] is True
    assert captured_req is not None
    assert captured_req.headers["Authorization"] == "Bearer receiver-secret"
    query = parse_qs(urlsplit(captured_req.full_url).query)
    assert query["project_id"] == ["manufacturing-demo-project"]
    assert query["workspace_id"] == ["manufacturing-demo"]


def test_prediction_delivery_service_uses_configured_scope(monkeypatch) -> None:
    from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
        PredictionDeliveryService,
    )

    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_PROJECT_ID", "project-prod")
    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_WORKSPACE_ID", "workspace-prod")

    service = PredictionDeliveryService(
        endpoint_url="https://backend.internal/internal/prediction-results?existing=1"
    )
    query = parse_qs(urlsplit(service.endpoint_url).query)

    assert query["existing"] == ["1"]
    assert query["project_id"] == ["project-prod"]
    assert query["workspace_id"] == ["workspace-prod"]


def test_prediction_delivery_service_preserves_explicit_endpoint_scope(monkeypatch) -> None:
    from systems.generator.app.runtime_pipeline.prediction_delivery_service import (
        PredictionDeliveryService,
    )

    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_PROJECT_ID", "project-env")
    monkeypatch.setenv("GENERATOR_PREDICTION_RESULT_WORKSPACE_ID", "workspace-env")

    service = PredictionDeliveryService(
        endpoint_url=(
            "https://backend.internal/internal/prediction-results"
            "?project_id=project-url&workspace_id=workspace-url"
        )
    )
    query = parse_qs(urlsplit(service.endpoint_url).query)

    assert query["project_id"] == ["project-url"]
    assert query["workspace_id"] == ["workspace-url"]

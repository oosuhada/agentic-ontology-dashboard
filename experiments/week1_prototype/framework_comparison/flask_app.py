"""Flask implementation of the shared comparison contracts."""

from __future__ import annotations

from flask import Flask, jsonify, request
from pydantic import ValidationError

from .contracts import HEALTH_PAYLOAD
from .representative_dashboard import (
    MaintenanceRecommendationRequest,
    RepresentativeEventNotFound,
    build_maintenance_recommendation,
    build_manufacturing_dashboard,
    build_risk_event_search,
)


app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify(HEALTH_PAYLOAD)


def _float_query(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be a number") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _int_query(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


@app.get("/benchmark/manufacturing-dashboard")
def manufacturing_dashboard():
    try:
        payload = build_manufacturing_dashboard(
            risk_threshold=_float_query("risk_threshold", 0.0, 0.0, 1.0),
            limit=_int_query("limit", 8, 1, 100),
            line=request.args.get("line") or None,
        )
    except ValueError as error:
        return jsonify({"detail": str(error)}), 422
    return jsonify(payload.model_dump(mode="json"))


def _optional_choice_query(name: str, allowed: set[str]) -> str | None:
    value = request.args.get(name)
    if value is None or value == "":
        return None
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(sorted(allowed))}")
    return value


@app.get("/benchmark/risk-events")
def risk_event_search():
    try:
        payload = build_risk_event_search(
            risk_threshold=_float_query("risk_threshold", 0.6, 0.0, 1.0),
            status=_optional_choice_query(
                "status",
                {"critical", "warning", "attention", "data_quality_hold", "normal"},
            ),
            failure_type=request.args.get("failure_type") or None,
            line=request.args.get("line") or None,
            sort=_optional_choice_query(
                "sort",
                {
                    "probability_desc",
                    "probability_asc",
                    "event_id_asc",
                    "line_asc",
                },
            )
            or "probability_desc",
            limit=_int_query("limit", 5, 1, 100),
            offset=_int_query("offset", 0, 0, 1_000_000),
        )
    except ValueError as error:
        return jsonify({"detail": str(error)}), 422
    return jsonify(payload.model_dump(mode="json"))


@app.post("/benchmark/maintenance-recommendation")
def maintenance_recommendation():
    try:
        body = request.get_json(silent=False)
        parsed = MaintenanceRecommendationRequest.model_validate(body)
        payload = build_maintenance_recommendation(parsed)
    except ValidationError as error:
        return jsonify({"detail": error.errors(include_url=False)}), 422
    except RepresentativeEventNotFound:
        return jsonify({"detail": "event not found"}), 404
    except (TypeError, ValueError):
        return jsonify({"detail": "request body must be valid JSON"}), 422
    return jsonify(payload.model_dump(mode="json"))


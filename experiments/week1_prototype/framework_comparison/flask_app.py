"""Flask implementation of the shared comparison contracts."""

from __future__ import annotations

from flask import Flask, jsonify, request

from .contracts import HEALTH_PAYLOAD
from .representative_dashboard import build_manufacturing_dashboard


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


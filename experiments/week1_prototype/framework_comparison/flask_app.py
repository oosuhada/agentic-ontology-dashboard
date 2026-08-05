"""Flask implementation of the shared health contract."""

from __future__ import annotations

from flask import Flask, jsonify

from .contracts import HEALTH_PAYLOAD


app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify(HEALTH_PAYLOAD)


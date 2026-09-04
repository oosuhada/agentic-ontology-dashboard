"""Stable deterministic conversation contracts used by Operations orchestration."""

from .conversation import IntentResult, IntentRouter, deterministic_answer

__all__ = ["IntentResult", "IntentRouter", "deterministic_answer"]

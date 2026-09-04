"""Materialize read-only Agent Review Summaries from stable evidence snapshots."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.operations.agent_review_summary import (
    validate_agent_review_summary_contract,
    validated_agent_review_summary,
)
from app.operations.agent_review_summary_provider import (
    AGENT_REVIEW_SUMMARY_PROMPT_VERSION,
    AgentReviewSummaryProvider,
)
from app.operations.ports import AuditRepositoryPort
from app.diagnosis.presentation_dictionary import PRESENTATION_DICTIONARY_VERSION

SUMMARY_MATERIALIZATION_VERSION = "agent-review-summary-materialization-v1.1"


class AgentReviewSummaryMaterializer:
    """Persist validated summaries so UI reads do not become LLM triggers."""

    def __init__(
        self,
        repository: AuditRepositoryPort,
        provider: AgentReviewSummaryProvider | None,
    ) -> None:
        self.repository = repository
        self.provider = provider

    def materialize(
        self,
        *,
        packet: dict[str, Any],
        organization_id: str,
        project_id: str,
        workspace_id: str,
        history_window: str,
        workflow_run_id: str | None = None,
        force: bool = False,
        refresh_fallback: bool = False,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        key_payload = summary_key_payload(
            packet=packet,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            history_window=history_window,
            provider=self.provider,
        )
        materialization_key = summary_key(key_payload)
        cached = self.repository.get_agent_review_summary(materialization_key)
        should_refresh_fallback = refresh_fallback and cached is not None and cached.get("status") == "fallback"
        if cached is not None and not force and not should_refresh_fallback:
            return cached["summary"], {
                **cached["trace"],
                "materialization": _materialization_trace(cached, reused=True),
            }

        summary, trace = self._generate_summary(packet)
        trace = {**trace, "context_sha256": key_payload["context_sha256"]}
        status = "fallback" if trace["fallback"] else "ready"
        record = self.repository.save_agent_review_summary(
            summary_key=materialization_key,
            workflow_run_id=workflow_run_id,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            asset_id=packet.get("asset_id"),
            event_id=(packet.get("snapshot_basis") or {}).get("event_id"),
            dataset_version_id=(packet.get("snapshot_basis") or {}).get(
                "dataset_version"
            ),
            history_window=history_window,
            packet_schema_version=packet.get("schema_version"),
            summary_schema_version=summary.get("schema_version"),
            prompt_version=AGENT_REVIEW_SUMMARY_PROMPT_VERSION,
            model_version=key_payload["model_version"],
            source_sha256=key_payload["source_sha256"],
            status=status,
            fallback_reason=trace.get("reason") if trace["fallback"] else None,
            snapshot_basis=packet.get("snapshot_basis") or {},
            summary=summary,
            trace=trace,
            generated_at=summary.get("generated_at"),
        )
        return record["summary"], {
            **record["trace"],
            "materialization": _materialization_trace(record, reused=False),
        }

    def lookup(
        self,
        *,
        packet: dict[str, Any],
        organization_id: str,
        project_id: str,
        workspace_id: str,
        history_window: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        """Return a stored summary only; never generate an LLM/fallback candidate."""

        key_payload = summary_key_payload(
            packet=packet,
            organization_id=organization_id,
            project_id=project_id,
            workspace_id=workspace_id,
            history_window=history_window,
            provider=self.provider,
        )
        materialization_key = summary_key(key_payload)
        cached = self.repository.get_agent_review_summary(materialization_key)
        if cached is not None:
            return cached["summary"], {
                **cached["trace"],
                "context_sha256": key_payload["context_sha256"],
                "materialization": _materialization_trace(cached, reused=True),
            }
        return None, {
            "provider": getattr(self.provider, "name", "none") if self.provider else "none",
            "fallback": False,
            "reason": "summary_not_materialized",
            "validation_errors": [],
            "context_sha256": key_payload["context_sha256"],
            "materialization": _pending_materialization_trace(
                summary_key=materialization_key,
                key_payload=key_payload,
            ),
        }

    def _generate_summary(self, packet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        provider = self.provider
        if provider is None:
            summary, errors = validated_agent_review_summary(packet=packet)
            return summary, {
                "provider": "none",
                "fallback": True,
                "reason": "agent_review_summary_provider_disabled",
                "validation_errors": errors,
            }

        try:
            candidate = provider.generate(packet)
            candidate_errors = validate_agent_review_summary_contract(
                candidate, packet=packet
            )
            if candidate.get("mode") != "llm":
                candidate_errors.append("mode_invalid_for_candidate")
            if not candidate_errors:
                return candidate, {
                    "provider": provider.name,
                    "fallback": False,
                    "reason": None,
                    "validation_errors": [],
                }
            summary, errors = validated_agent_review_summary(packet=packet)
            return summary, {
                "provider": provider.name,
                "fallback": True,
                "reason": "summary_validation_failed",
                "validation_errors": candidate_errors,
                "fallback_validation_errors": errors,
            }
        except Exception as exc:
            summary, errors = validated_agent_review_summary(packet=packet)
            return summary, {
                "provider": getattr(provider, "name", "unknown"),
                "fallback": True,
                "reason": type(exc).__name__,
                "message": str(exc),
                "validation_errors": errors,
            }


def summary_key_payload(
    *,
    packet: dict[str, Any],
    organization_id: str = "org-ontology-demo",
    project_id: str,
    workspace_id: str = "manufacturing-demo",
    history_window: str,
    provider: AgentReviewSummaryProvider | None,
) -> dict[str, Any]:
    basis = packet.get("snapshot_basis") or {}
    source_sha256 = str(basis.get("source_sha256") or _sha256_json(basis))
    return {
        "materialization_version": SUMMARY_MATERIALIZATION_VERSION,
        "organization_id": organization_id,
        "project_id": project_id,
        "workspace_id": workspace_id,
        "asset_id": str(packet.get("asset_id") or ""),
        "event_id": str(basis.get("event_id") or ""),
        "dataset_version": str(basis.get("dataset_version") or ""),
        "history_window": history_window,
        "packet_schema_version": str(packet.get("schema_version") or ""),
        "summary_schema_version": "agent-review-summary-v1.0",
        "prompt_version": AGENT_REVIEW_SUMMARY_PROMPT_VERSION,
        "presentation_dictionary_version": PRESENTATION_DICTIONARY_VERSION,
        "model_version": _provider_model_version(provider),
        "source_sha256": source_sha256,
        "context_sha256": _summary_context_sha256(packet),
    }


def summary_key(payload: dict[str, Any]) -> str:
    return f"agent-review-summary:{_sha256_json(payload)}"


def _provider_model_version(provider: AgentReviewSummaryProvider | None) -> str:
    if provider is None:
        return "deterministic:none"
    model = getattr(getattr(provider, "provider", None), "model", "")
    if model:
        return f"{provider.name}:{model}"
    return provider.name


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _summary_context_sha256(packet: dict[str, Any]) -> str:
    return _sha256_json(
        {
            "risk_summary": packet.get("risk_summary") or {},
            "review_draft": packet.get("review_draft") or {},
            "review_priority": packet.get("review_priority"),
            "model_expression_context": packet.get("model_expression_context") or {},
            "operation_context_summary": packet.get("operation_context_summary") or {},
            "maintenance_history_summary": packet.get("maintenance_history_summary") or {},
            "sop_guidance": packet.get("sop_guidance") or [],
            "inspection_targets": packet.get("inspection_targets") or [],
            "ontology_context": packet.get("ontology_context") or {},
            "evidence_gaps": packet.get("evidence_gaps") or [],
            "limitations": packet.get("limitations") or [],
        }
    )


def _materialization_trace(record: dict[str, Any], *, reused: bool) -> dict[str, Any]:
    return {
        "summary_id": record["summary_id"],
        "summary_key": record["summary_key"],
        "workflow_run_id": record.get("workflow_run_id"),
        "status": record["status"],
        "reused": reused,
        "source_sha256": record["source_sha256"],
        "context_sha256": (record.get("trace") or {}).get("context_sha256"),
        "prompt_version": record["prompt_version"],
        "model_version": record["model_version"],
        "generated_at": record["generated_at"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "fallback_reason": record.get("fallback_reason"),
    }


def _pending_materialization_trace(
    *,
    summary_key: str,
    key_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "summary_id": None,
        "summary_key": summary_key,
        "workflow_run_id": None,
        "status": "pending",
        "reused": False,
        "source_sha256": key_payload["source_sha256"],
        "context_sha256": key_payload["context_sha256"],
        "prompt_version": key_payload["prompt_version"],
        "model_version": key_payload["model_version"],
        "generated_at": None,
        "created_at": None,
        "updated_at": None,
        "fallback_reason": None,
    }

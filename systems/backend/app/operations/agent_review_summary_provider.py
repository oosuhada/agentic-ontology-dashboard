"""LLM adapter for read-only Agent Review Summary generation."""

from __future__ import annotations

from typing import Any

from app.operations.agent_review_summary import (
    compose_deterministic_agent_review_summary,
    summary_schema,
)
from app.operations.ports import AgentReviewLLMPort


AGENT_REVIEW_SUMMARY_SYSTEM_PROMPT = """
You write a Korean read-only maintenance review summary from one Agent Review Packet.

Hard contract:
- Use only facts, IDs, timestamps, source_refs, limitations, inspection targets, SOP guidance,
  evidence gaps, risk summary, and history summary present in the packet.
- Do not return the input agent_review_packet or any of its packet-only fields.
- Do not create work orders, approvals, maintenance events, replay requests, action IDs,
  state patches, or any closed-loop mutation.
- Do not claim repair completion, auto approval, real downtime reduction, root-cause certainty,
  or actual failure prevention.
- Preserve packet asset_id, generated_at, packet schema version, boundary note, limitations,
  evidence gaps, and source_refs grounding.
- Return JSON only, matching agent-review-summary-v1.0.
- Keep baseline_summary.history_summary, inspection_focus, evidence_gaps, data_footnotes,
  source_refs, boundary_note, confidence_label, limitations, schema_version,
  packet_schema_version, asset_id, generated_at, and mode unchanged.
- Keep baseline_summary.role_summaries role, label, and source_refs unchanged.
- You may improve only title, summary, and role_summaries[*].quote. These fields must stay
  read-only Korean prose grounded in baseline_summary and agent_review_packet.
- Use the packet's display_name values as user language. Never infer meaning from raw field,
  artifact, model, dataset, or source identifiers.
- Prefer value-realization language over task-only reporting. When operation context supports
  it, connect early detection and human response to production continuity, protected exposure,
  decision-speed KPI, and other company outcomes.
- Never turn modeled downtime or production exposure into realized savings. Until the packet
  contains case-linked post-action and financial actual evidence, use wording such as "보호 대상
  가치", "예상 손실 노출", "회피 가능 비용", or "KPI 기여 가능성" and explicitly state that
  realized savings remain unconfirmed.
""".strip()

AGENT_REVIEW_SUMMARY_PROMPT_VERSION = "agent-review-summary-prompt-v1.2-value"


class AgentReviewSummaryProvider:
    """Generate a candidate summary through the shared LLM provider port."""

    def __init__(self, provider: AgentReviewLLMPort | None) -> None:
        self.provider = provider
        self.name = getattr(provider, "name", "none")

    def generate(self, packet: dict[str, Any]) -> dict[str, Any]:
        if self.provider is None:
            raise RuntimeError("agent_review_summary_provider_disabled")
        baseline_summary = compose_deterministic_agent_review_summary(packet)
        payload = self.provider.generate_json(
            AGENT_REVIEW_SUMMARY_SYSTEM_PROMPT,
            {
                "agent_review_packet": packet,
                "baseline_summary": baseline_summary,
                "allowed_output_fields": list(baseline_summary.keys()),
            },
            response_schema=summary_schema(),
            response_schema_name="agent_review_summary",
        )
        return _merge_llm_editable_fields(
            baseline_summary=baseline_summary,
            candidate=payload,
        )


def _merge_llm_editable_fields(
    *,
    baseline_summary: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Apply LLM prose edits while preserving grounded summary structure."""

    summary = dict(baseline_summary)
    summary["mode"] = "llm"
    for field in ("title", "summary"):
        value = candidate.get(field)
        if isinstance(value, str) and value.strip():
            summary[field] = value

    candidate_quotes = {
        str(item.get("role")): item.get("quote")
        for item in candidate.get("role_summaries") or []
        if isinstance(item, dict) and isinstance(item.get("quote"), str)
    }
    summary["role_summaries"] = [
        {
            **item,
            "quote": candidate_quotes.get(item["role"]) or item["quote"],
        }
        for item in baseline_summary.get("role_summaries") or []
    ]
    return summary

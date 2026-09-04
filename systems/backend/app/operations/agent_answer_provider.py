"""Grounded LLM answer generation for the read-only Operations assistant."""

from __future__ import annotations

from typing import Any

from app.operations.ports import AgentReviewLLMPort


AGENT_ANSWER_PROMPT_VERSION = "operations-grounded-answer-v1.0"

AGENT_ANSWER_SYSTEM_PROMPT = """
You are the read-only operations assistant for Hanbit Tech.

Answer in Korean unless the user's question is clearly English. Adapt the depth
and vocabulary to the requested audience: engineering, operations, executive,
or maintenance.

Grounding contract:
- Use only the supplied packet summary and evidence items.
- Treat evidence IDs and source references as immutable citations.
- Separate observed facts, estimates, historical context, and recommendations.
- Never claim a failure, root cause, repair result, approval, work completion,
  downtime reduction, revenue impact, or inventory fact that is not in evidence.
- Historical maintenance, meeting, decision, business, material, and financial
  context may explain a recommendation but must not overwrite current workflow state.
- Do not approve, create, start, complete, cancel, or mutate any work order.
- If evidence is insufficient, say what is missing.
- Keep the answer concise enough for an operational workspace, but include the
  most decision-relevant business or maintenance context when it is available.

Return JSON only with: answer, evidence_ids, caveats.
""".strip()


AGENT_ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "caveats": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "evidence_ids", "caveats"],
}


class GroundedAgentAnswerProvider:
    def __init__(self, provider: AgentReviewLLMPort | None) -> None:
        self.provider = provider
        self.name = getattr(provider, "name", "none")

    def generate(
        self,
        *,
        question: str,
        audience: str | None,
        packet: dict[str, Any],
        evidence: list[dict[str, Any]],
        baseline_answer: str,
        summary: dict[str, Any] | None,
    ) -> tuple[str, list[str], list[str], dict[str, Any]]:
        if self.provider is None:
            return baseline_answer, [], [], {
                "mode": "deterministic_fallback",
                "provider": "none",
                "reason": "provider_unavailable",
                "prompt_version": AGENT_ANSWER_PROMPT_VERSION,
            }

        allowed_ids = {str(item.get("evidence_id")) for item in evidence if item.get("evidence_id")}
        compact_packet = {
            "asset_id": packet.get("asset_id"),
            "risk_summary": packet.get("risk_summary") or {},
            "review_priority": packet.get("review_priority") or {},
            "maintenance_history_summary": packet.get("maintenance_history_summary") or {},
            "operation_context_summary": packet.get("operation_context_summary") or {},
            "inspection_targets": packet.get("inspection_targets") or [],
            "evidence_gaps": packet.get("evidence_gaps") or [],
            "limitations": packet.get("limitations") or [],
        }
        try:
            candidate = self.provider.generate_json(
                AGENT_ANSWER_SYSTEM_PROMPT,
                {
                    "question": question,
                    "audience": audience or "operations",
                    "packet": compact_packet,
                    "role_summary": summary,
                    "evidence": evidence,
                    "baseline_answer": baseline_answer,
                },
                response_schema=AGENT_ANSWER_SCHEMA,
                response_schema_name="operations_grounded_answer",
            )
            answer = str(candidate.get("answer") or "").strip()
            cited_ids = [str(item) for item in candidate.get("evidence_ids") or []]
            unknown = sorted(set(cited_ids) - allowed_ids)
            if not answer:
                raise ValueError("empty_answer")
            if unknown:
                raise ValueError(f"unknown_evidence_ids:{','.join(unknown)}")
            forbidden = (
                "자동 승인 완료",
                "자동으로 승인",
                "정비 완료가 확인",
                "근본 원인이 확정",
                "고장이 확정",
            )
            if any(text in answer for text in forbidden):
                raise ValueError("forbidden_operational_claim")
            caveats = [str(item) for item in candidate.get("caveats") or [] if str(item).strip()]
            return answer, cited_ids, caveats, {
                "mode": "llm",
                "provider": self.name,
                "reason": None,
                "prompt_version": AGENT_ANSWER_PROMPT_VERSION,
            }
        except Exception as exc:
            return baseline_answer, [], [], {
                "mode": "deterministic_fallback",
                "provider": self.name,
                "reason": type(exc).__name__,
                "prompt_version": AGENT_ANSWER_PROMPT_VERSION,
            }

"""Deterministic event layout planner retained as part of the canonical planner package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .ports import PlannerLLMPort
from .state import AppLocale, Intent, Role, UIBlock, UILayout

BLOCK_REGISTRY: dict[str, tuple[str, list[str]]] = {
    "StatusSummary": ("현재 상태", ["status", "confidence", "predicted_failure_type"]),
    "RiskKpi": ("위험 지표", ["failure_probability", "threshold", "status"]),
    "PriorityList": ("설비 우선순위", ["equipment", "status", "failure_probability"]),
    "ImpactSummary": ("예상 운영 영향", ["equipment.criticality", "equipment.estimated_downtime_minutes"]),
    "ManagerDecisionCard": ("권장 결정", ["recommended_decision", "maintenance_context.recommended_actions"]),
    "SensorLineChart": ("센서 변화", ["history", "detected_interval"]),
    "AnomalyTimeline": ("이상 구간", ["history", "detected_interval", "status"]),
    "FactorContribution": ("주요 위험 근거", ["top_factors"]),
    "EvidenceTable": ("근거 상세", ["top_factors", "observation"]),
    "RecommendedActions": ("권장 조치", ["maintenance_context.recommended_actions", "recommended_decision"]),
    "EngineerChecklist": ("점검 체크리스트", ["maintenance_context.checklist", "maintenance_context.source_refs"]),
    "DataQualityWarning": ("데이터 품질 경고", ["data_quality_warnings"]),
    "ModelDetails": ("모델·정책 상세", ["model", "threshold", "lineage"]),
    "ConversationThread": ("후속 질문", ["event_id", "evidence_id"]),
}


BLOCK_TITLES_EN: dict[str, str] = {
    "StatusSummary": "Current status",
    "RiskKpi": "Risk indicators",
    "PriorityList": "Equipment priority",
    "ImpactSummary": "Estimated operational impact",
    "ManagerDecisionCard": "Recommended decision",
    "SensorLineChart": "Sensor trends",
    "AnomalyTimeline": "Anomaly interval",
    "FactorContribution": "Primary risk evidence",
    "EvidenceTable": "Evidence details",
    "RecommendedActions": "Recommended actions",
    "EngineerChecklist": "Inspection checklist",
    "DataQualityWarning": "Data quality warning",
    "ModelDetails": "Model and policy details",
    "ConversationThread": "Follow-up questions",
}

MANAGER_DEFAULT = [
    "StatusSummary", "RiskKpi", "PriorityList", "ImpactSummary", "ManagerDecisionCard",
    "RecommendedActions", "FactorContribution", "ModelDetails", "ConversationThread",
]
ENGINEER_DEFAULT = [
    "StatusSummary", "SensorLineChart", "AnomalyTimeline", "FactorContribution", "EvidenceTable",
    "EngineerChecklist", "RecommendedActions", "ModelDetails", "ConversationThread",
]


class LayoutPlanner:
    def __init__(self, project_root: str | Path, provider: PlannerLLMPort | None = None) -> None:
        self.root = Path(project_root)
        self.provider = provider
        self.schema = json.loads(
            (self.root / "contracts" / "schemas" / "ui-block.schema.json").read_text(encoding="utf-8")
        )

    def _ordered_types(self, evidence: dict[str, Any], role: Role, intent: Intent) -> list[str]:
        if evidence["status"] == "data_quality_hold":
            if role == "manager":
                return ["DataQualityWarning", "StatusSummary", "ManagerDecisionCard", "ModelDetails", "ConversationThread"]
            return ["DataQualityWarning", "EvidenceTable", "EngineerChecklist", "ModelDetails", "ConversationThread"]
        if evidence["confidence"] == "low":
            if role == "manager":
                return [
                    "DataQualityWarning", "StatusSummary", "RiskKpi", "ManagerDecisionCard",
                    "PriorityList", "RecommendedActions", "ModelDetails", "ConversationThread",
                ]
            return [
                "DataQualityWarning", "SensorLineChart", "EvidenceTable", "EngineerChecklist",
                "FactorContribution", "RecommendedActions", "ModelDetails", "ConversationThread",
            ]

        base = list(MANAGER_DEFAULT if role == "manager" else ENGINEER_DEFAULT)
        if role == "engineer" and intent == "overview":
            scenario_id = evidence.get("scenario_id")
            promoted = (
                ["StatusSummary"] if scenario_id == "GS-001"
                else ["FactorContribution"] if scenario_id == "GS-005"
                else ["SensorLineChart"]
            )
            return [*promoted, *(item for item in base if item not in promoted)]
        priorities: dict[Intent, list[str]] = {
            "overview": [],
            "explain-risk": ["FactorContribution", "EvidenceTable"],
            "compare": ["SensorLineChart", "EvidenceTable"],
            "summarize-manager": ["StatusSummary", "ImpactSummary", "ManagerDecisionCard"],
            "detail-engineer": ["SensorLineChart", "AnomalyTimeline", "FactorContribution", "EvidenceTable"],
            "recommend-check": ["RecommendedActions", "EngineerChecklist"],
            "show-model-details": ["ModelDetails", "StatusSummary"],
        }
        promoted = [item for item in priorities[intent] if item in base]
        return [*promoted, *(item for item in base if item not in promoted)]

    def deterministic(
        self,
        evidence: dict[str, Any],
        role: Role,
        intent: Intent,
        *,
        locale: AppLocale = "ko-KR",
        mode: str,
    ) -> UILayout:
        blocks: list[UIBlock] = []
        for index, block_type in enumerate(self._ordered_types(evidence, role, intent), start=1):
            title, fields = BLOCK_REGISTRY[block_type]
            if locale == "en-US":
                title = BLOCK_TITLES_EN[block_type]
            if (
                block_type == "DataQualityWarning"
                and evidence["confidence"] == "low"
                and not evidence["data_quality_warnings"]
            ):
                title = "Low-confidence result warning" if locale == "en-US" else "저신뢰 결과 경고"
            blocks.append(
                UIBlock(
                    block_id=f"block.{index}.{block_type}",
                    type=block_type,  # type: ignore[arg-type]
                    title=title,
                    order=index,
                    emphasis="primary" if index <= 3 else "secondary" if index <= 6 else "detail",
                    data_fields=fields,
                    collapsed=block_type == "ModelDetails" and intent != "show-model-details",
                )
            )
        layout = UILayout(
            layout_id=f"LAY-{evidence['event_id']}-{role}-{intent}-{locale}",
            event_id=evidence["event_id"],
            role=role,
            locale=locale,
            intent=intent,
            mode=mode,  # type: ignore[arg-type]
            blocks=blocks,
            generated_at=evidence["generated_at"],
        )
        self.validate(layout, evidence)
        return layout

    def validate(self, layout: UILayout, evidence: dict[str, Any]) -> None:
        errors = sorted(
            Draft202012Validator(self.schema).iter_errors(layout.model_dump(mode="json")),
            key=lambda item: list(item.absolute_path),
        )
        if errors:
            raise ValueError("layout schema invalid: " + "; ".join(error.message for error in errors))
        if layout.event_id != evidence["event_id"]:
            raise ValueError("layout event does not match evidence")
        orders = [block.order for block in layout.blocks]
        if orders != list(range(1, len(orders) + 1)):
            raise ValueError("layout order must be contiguous")
        for block in layout.blocks:
            if block.type not in BLOCK_REGISTRY:
                raise ValueError(f"unregistered block: {block.type}")
            allowed = set(BLOCK_REGISTRY[block.type][1])
            if not set(block.data_fields).issubset(allowed):
                raise ValueError(f"block {block.type} requested unregistered data fields")
        if evidence["status"] == "data_quality_hold" and layout.blocks[0].type != "DataQualityWarning":
            raise ValueError("data-quality layout must lead with DataQualityWarning")

    def plan(
        self,
        evidence: dict[str, Any],
        report: Any,
        role: Role,
        intent: Intent,
        *,
        locale: AppLocale = "ko-KR",
        use_llm: bool,
        provider_available: bool,
    ) -> tuple[UILayout, dict[str, Any]]:
        if not use_llm:
            return self.deterministic(evidence, role, intent, locale=locale, mode="deterministic"), {
                "fallback": False,
                "provider": "none",
            }
        if not provider_available or self.provider is None:
            return self.deterministic(evidence, role, intent, locale=locale, mode="deterministic_fallback"), {
                "fallback": True,
                "provider": getattr(self.provider, "name", "none"),
                "reason": "planner_unavailable",
            }
        try:
            prompt = (self.root / "prompts" / "ui-planner.md").read_text(encoding="utf-8")
            payload = self.provider.generate_json(
                prompt,
                {
                    "role": role,
                    "intent": intent,
                    "locale": locale,
                    "output_language": "Korean" if locale == "ko-KR" else "English",
                    "evidence": evidence,
                    "report": report.model_dump(mode="json"),
                },
            )
            payload["mode"] = "llm"
            payload["locale"] = locale
            layout = UILayout.model_validate(payload)
            self.validate(layout, evidence)
            return layout, {"fallback": False, "provider": self.provider.name}
        except Exception as exc:
            return self.deterministic(evidence, role, intent, locale=locale, mode="deterministic_fallback"), {
                "fallback": True,
                "provider": getattr(self.provider, "name", "unknown"),
                "reason": type(exc).__name__,
            }


__all__ = ["BLOCK_REGISTRY", "LayoutPlanner"]

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .generation import render_report
from .ports import ReportGenerationProviderPort
from .report_schema import AppLocale, GroundedReport, ReportType, Role


class ReportAgent:
    def __init__(
        self,
        project_root: str | Path,
        provider: ReportGenerationProviderPort | None = None,
    ) -> None:
        self.root = Path(project_root)
        self.provider = provider
        self.report_schema = json.loads((self.root / "contracts" / "schemas" / "report.schema.json").read_text(encoding="utf-8"))

    def _prompt(self, role: Role, locale: AppLocale) -> str:
        name = "manager-report.md" if role == "manager" else "executive-report.md" if role == "executive" else "engineer-report.md"
        base = (self.root / "prompts" / name).read_text(encoding="utf-8")
        language = "Korean" if locale == "ko-KR" else "English"
        return (
            f"{base}\n\n"
            f"OUTPUT LANGUAGE CONTRACT: Write every human-readable field in {language}. "
            f"Set locale to '{locale}'. Keep IDs, evidence references, model versions, schema versions, "
            "units, and source tokens unchanged."
        )

    def _validate_schema(self, payload: dict[str, Any]) -> None:
        errors = sorted(Draft202012Validator(self.report_schema).iter_errors(payload), key=lambda item: list(item.absolute_path))
        if errors:
            rendered = "; ".join(error.message for error in errors)
            raise ValueError(f"LLM report schema invalid: {rendered}")

    @staticmethod
    def _allowed_references(evidence: dict[str, Any]) -> set[str]:
        refs = {
            "status",
            "recommended_decision",
            "confidence",
            "failure_probability",
            "predicted_failure_type",
            "detected_interval.start",
            "detected_interval.end",
            "equipment.criticality",
            "equipment.estimated_downtime_minutes",
        }
        refs.update(factor["evidence_field_id"] for factor in evidence["top_factors"])
        refs.update(evidence["maintenance_context"]["source_refs"])
        refs.update(f"data_quality_warnings.{index}" for index, _ in enumerate(evidence["data_quality_warnings"]))
        refs.update(
            str(item.get("evidence_field_id"))
            for item in evidence.get("company_context_documents") or []
            if item.get("evidence_field_id")
        )
        return refs

    def _validate_grounding(
        self,
        report: GroundedReport,
        evidence: dict[str, Any],
        role: Role,
        locale: AppLocale,
    ) -> None:
        if report.event_id != evidence["event_id"] or report.role != role:
            raise ValueError("LLM report event or role does not match request")
        if report.locale != locale:
            raise ValueError("LLM report locale does not match request")
        if report.status != evidence["status"]:
            raise ValueError("LLM report changed the accepted status")
        if report.recommended_decision != evidence["recommended_decision"]:
            raise ValueError("LLM report changed the accepted decision")
        allowed = self._allowed_references(evidence)
        referenced = set(report.citations)
        for section in report.sections:
            referenced.update(section.evidence_field_ids)
        unknown = sorted(referenced - allowed)
        if unknown:
            raise ValueError(f"LLM report contains unknown evidence references: {unknown}")
        forbidden_phrases = ["자동 정지 완료", "작업 지시가 실행", "근본 원인이 확정", "고장이 확정"]
        combined = " ".join([report.headline, report.summary, *(section.body for section in report.sections)])
        if any(phrase in combined for phrase in forbidden_phrases):
            raise ValueError("LLM report contains a forbidden operational claim")

    def generate(
        self,
        evidence: dict[str, Any],
        role: Role,
        *,
        locale: AppLocale,
        use_llm: bool,
        provider_available: bool,
        report_type: ReportType | None = None,
    ) -> tuple[GroundedReport, dict[str, Any]]:
        if not use_llm:
            return render_report(evidence, role, locale=locale, mode="deterministic", report_type=report_type), {"provider": "none", "fallback": False}
        if not provider_available or self.provider is None:
            return render_report(evidence, role, locale=locale, mode="deterministic_fallback", report_type=report_type), {
                "provider": getattr(self.provider, "name", "unknown"),
                "fallback": True,
                "reason": "fixture_provider_disabled",
            }
        try:
            payload = self.provider.generate_json(
                self._prompt(role, locale),
                {"evidence": evidence, "role": role, "report_type": report_type, "locale": locale},
            )
            payload["mode"] = "llm"
            payload["locale"] = locale
            payload["report_type"] = report_type or ("executive-brief" if role == "executive" else "inspection-summary" if role == "engineer" else "operations-decision")
            self._validate_schema(payload)
            report = GroundedReport.model_validate(payload)
            self._validate_grounding(report, evidence, role, locale)
            return report, {"provider": self.provider.name, "fallback": False}
        except Exception as exc:  # provider, timeout, parser, schema, and grounding failures all fail closed
            return render_report(evidence, role, locale=locale, mode="deterministic_fallback", report_type=report_type), {
                "provider": getattr(self.provider, "name", "unknown"),
                "fallback": True,
                "reason": type(exc).__name__,
            }

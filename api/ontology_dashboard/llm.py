from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

import httpx
from jsonschema import Draft202012Validator

from .contracts import AppLocale, GroundedReport, Role
from .reports import render_report


class LLMProvider(Protocol):
    name: str

    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class ProviderUnavailable(RuntimeError):
    pass


class VertexAIProvider:
    """Gemini on Vertex AI using Application Default Credentials (ADC)."""

    name = "vertex-ai"

    def __init__(self) -> None:
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        self.model = os.getenv("LLM_MODEL", "gemini-2.5-flash")

    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.project:
            raise ProviderUnavailable("GOOGLE_CLOUD_PROJECT is not configured for Vertex AI")
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ProviderUnavailable("google-genai is not installed") from exc

        client = genai.Client(vertexai=True, project=self.project, location=self.location)
        response = client.models.generate_content(
            model=self.model,
            contents=json.dumps(payload, ensure_ascii=False),
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        if not response.text:
            raise ProviderUnavailable("Vertex AI returned an empty response")
        return json.loads(response.text)


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self) -> None:
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("LLM_MODEL", "")
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))

    def generate_json(self, system_prompt: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key or not self.model:
            raise ProviderUnavailable("LLM credentials or model are not configured")
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={
                "model": self.model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)


def configured_provider() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "deterministic").strip().lower()
    if provider in {"vertex", "vertex-ai", "vertex_ai"}:
        return VertexAIProvider()
    return OpenAICompatibleProvider()


class ReportAgent:
    def __init__(self, project_root: str | Path, provider: LLMProvider | None = None) -> None:
        self.root = Path(project_root)
        self.provider = provider or OpenAICompatibleProvider()
        self.report_schema = json.loads((self.root / "schemas" / "report.schema.json").read_text(encoding="utf-8"))

    def _prompt(self, role: Role, locale: AppLocale) -> str:
        name = "manager-report.md" if role == "manager" else "engineer-report.md"
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
    ) -> tuple[GroundedReport, dict[str, Any]]:
        if not use_llm:
            return render_report(evidence, role, locale=locale, mode="deterministic"), {"provider": "none", "fallback": False}
        if not provider_available:
            return render_report(evidence, role, locale=locale, mode="deterministic_fallback"), {
                "provider": getattr(self.provider, "name", "unknown"),
                "fallback": True,
                "reason": "fixture_provider_disabled",
            }
        try:
            payload = self.provider.generate_json(
                self._prompt(role, locale),
                {"evidence": evidence, "role": role, "locale": locale},
            )
            payload["mode"] = "llm"
            payload["locale"] = locale
            self._validate_schema(payload)
            report = GroundedReport.model_validate(payload)
            self._validate_grounding(report, evidence, role, locale)
            return report, {"provider": self.provider.name, "fallback": False}
        except Exception as exc:  # provider, timeout, parser, schema, and grounding failures all fail closed
            return render_report(evidence, role, locale=locale, mode="deterministic_fallback"), {
                "provider": getattr(self.provider, "name", "unknown"),
                "fallback": True,
                "reason": type(exc).__name__,
            }

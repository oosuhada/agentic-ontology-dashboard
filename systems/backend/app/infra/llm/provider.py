"""LLM provider ports and external provider adapters."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

import httpx


class LLMProvider(Protocol):
    name: str

    def generate_json(
        self,
        system_prompt: str,
        payload: dict[str, Any],
        *,
        response_schema: dict[str, Any] | None = None,
        response_schema_name: str = "structured_response",
    ) -> dict[str, Any]: ...


class ProviderUnavailable(RuntimeError):
    pass


class VertexAIProvider:
    """Gemini on Vertex AI using Application Default Credentials (ADC)."""

    name = "vertex-ai"

    def __init__(self) -> None:
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        self.model = os.getenv("LLM_MODEL", "gemini-2.5-flash")

    def generate_json(
        self,
        system_prompt: str,
        payload: dict[str, Any],
        *,
        response_schema: dict[str, Any] | None = None,
        response_schema_name: str = "structured_response",
    ) -> dict[str, Any]:
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

    def generate_json(
        self,
        system_prompt: str,
        payload: dict[str, Any],
        *,
        response_schema: dict[str, Any] | None = None,
        response_schema_name: str = "structured_response",
    ) -> dict[str, Any]:
        if not self.api_key or not self.model:
            raise ProviderUnavailable("LLM credentials or model are not configured")
        response_format: dict[str, Any]
        if response_schema:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema_name,
                    "strict": True,
                    "schema": _openai_compatible_schema(response_schema),
                },
            }
        else:
            response_format = {"type": "json_object"}
        request_body = {
            "model": self.model,
            "temperature": 0,
            "response_format": response_format,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        }
        response = self._post_chat_completion(request_body)
        if response_schema and response.status_code == 400:
            request_body["response_format"] = {"type": "json_object"}
            response = self._post_chat_completion(request_body)
        if response.status_code >= 400:
            raise ProviderUnavailable(
                f"OpenAI request rejected: {response.status_code} {response.text}"
            )
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)

    def _post_chat_completion(self, request_body: dict[str, Any]) -> httpx.Response:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=request_body,
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            if response.status_code == 400:
                return response
            response.raise_for_status()
        return response


def configured_provider() -> LLMProvider:
    provider = os.getenv("LLM_PROVIDER", "deterministic").strip().lower()
    if provider in {"vertex", "vertex-ai", "vertex_ai"}:
        return VertexAIProvider()
    return OpenAICompatibleProvider()


def _openai_compatible_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Project Draft 2020-12 schema into the subset accepted by OpenAI strict JSON."""

    def convert(value: Any) -> Any:
        if isinstance(value, list):
            return [convert(item) for item in value]
        if not isinstance(value, dict):
            return value

        converted: dict[str, Any] = {}
        for key, child in value.items():
            if key in {"$schema", "$id", "title", "description", "minLength"}:
                continue
            if key == "const":
                converted["enum"] = [child]
                continue
            converted[key] = convert(child)
        return converted

    return convert(schema)

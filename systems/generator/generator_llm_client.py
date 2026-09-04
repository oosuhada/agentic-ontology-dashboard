"""
generator_llm_client.py

담당 기능:
- Generator 도메인 전역 LLM 호출 서비스(call_llm) 및 Pydantic 스키마 검증/다중 변환기(validate_or_transform_pydantic) 모듈.
- OpenAI 또는 Google Vertex AI Gemini provider를 통해 RAW 텍스트 응답을 수신하며, Pydantic 검증 ➔ 실패 시 Multi-Format Transformer(JSON/YAML/KV/CSV) ➔ Pydantic 스키마 재검증 ➔ 실패 시 None(Fail-Fast) 4단계 파이프라인으로 동작한다.

입력:
- prompt(str): LLM에 전달할 사용자 프롬프트
- system(str, optional): system 역할 프롬프트. 기본값 "You are a helpful assistant."
- raw_text(str): LLM 수신 RAW 응답 텍스트
- pydantic_cls(type[T]): 검증 및 정제할 Pydantic 스키마 모델 클래스

출력:
- call_llm(): LLM RAW 응답 텍스트 (str)
- validate_or_transform_pydantic(): 스키마 검증이 완료된 Pydantic 모델 인스턴스 또는 실패 시 None

의존 모듈:
- generator_config.load_config: API 키 로딩 전 환경변수 세팅.
- openai.OpenAI: OpenAI 공식 API 클라이언트.
- google.genai: Google Vertex AI Gemini 공식 Gen AI SDK.
- pydantic.BaseModel, json, re, yaml, logging

예외/경계 상황:
- 선택한 provider의 인증정보가 없으면 ValueError 발생하고 상위 단계의 기존 rule/heuristic fallback이 동작한다.
- Pydantic 스키마 검증 및 파싱 실패 시 경고 로그 후 None을 안전하게 반환한다(Fail-Fast).

설계 원칙과의 연결:
- docs/architecture.md의 '타입 안전 스키마 검증' 및 '단일 책임 원칙'에 따라 스키마 검증과 포맷 변환을 캡슐화하여 제공한다.
"""

import os
import sys
import json
import re
import logging
from typing import Any, TypeVar, Optional
from pydantic import BaseModel, Field

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from systems.generator.generator_config import load_config

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# --- Pydantic Response Schemas ---

class ColumnMappingResponse(BaseModel):
    ontology_node: str = "Unknown"
    confidence: float = 0.5
    reason: Optional[str] = None


class FileProfileResponse(BaseModel):
    role: str = "unknown"
    description: str = ""
    id_columns: list[str] = Field(default_factory=list)
    time_columns: list[dict] = Field(default_factory=list)
    column_notes: dict[str, str] = Field(default_factory=dict)
    confidence: float = 0.9


def call_llm(prompt: str, system: str = "You are a helpful assistant.") -> str:
    """OpenAI 또는 Vertex AI Gemini 모델을 호출하여 RAW 응답 텍스트를 반환한다."""
    load_config()
    provider = os.getenv("GENERATOR_LLM_PROVIDER", "openai").strip().lower()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY environment variable is missing.")
            raise ValueError("OPENAI_API_KEY가 설정되어 있지 않습니다.")

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("GENERATOR_LLM_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        return response.choices[0].message.content.strip()

    if provider in {"vertex", "vertex_ai", "google_vertex"}:
        from google import genai
        from google.genai import types

        api_key = os.getenv("VERTEX_AI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()
        location = os.getenv("GOOGLE_CLOUD_LOCATION", "global").strip() or "global"
        if not api_key and not project:
            logger.warning(
                "Vertex AI authentication is missing: configure VERTEX_AI_API_KEY/GOOGLE_API_KEY "
                "or GOOGLE_CLOUD_PROJECT with Application Default Credentials."
            )
            raise ValueError("Vertex AI 인증정보가 설정되어 있지 않습니다.")

        client_kwargs: dict[str, Any] = {
            "vertexai": True,
            "http_options": types.HttpOptions(api_version="v1"),
        }
        if api_key:
            client_kwargs["api_key"] = api_key
        if project:
            client_kwargs["project"] = project
            client_kwargs["location"] = location
        client = genai.Client(**client_kwargs)
        response = client.models.generate_content(
            model=os.getenv("GENERATOR_LLM_MODEL", "gemini-3.5-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.0,
            ),
        )
        text = response.text or ""
        if not text.strip():
            raise ValueError("Vertex AI Gemini returned an empty response")
        return text.strip()

    raise ValueError(f"unsupported GENERATOR_LLM_PROVIDER: {provider!r}")


def clean_markdown_block(raw_text: str) -> str:
    """응답 텍스트에서 ```json ... ``` 형태의 마크다운 코드 블록을 제거한다."""
    text = raw_text.strip()
    match = re.search(r"```(?:json|yaml)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def parse_multiformat(cleaned_text: str) -> Optional[dict]:
    """JSON, YAML, Key-Value, CSV 순으로 다중 포맷 파싱을 시도한다."""
    try:
        data = json.loads(cleaned_text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    try:
        import yaml
        data = yaml.safe_load(cleaned_text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    try:
        kv_data = {}
        lines = cleaned_text.strip().splitlines()
        for line in lines:
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip().strip("- ")
                v = v.strip()
                if k:
                    try:
                        v = json.loads(v)
                    except Exception:
                        pass
                    kv_data[k] = v
        if kv_data:
            return kv_data
    except Exception:
        pass

    try:
        import io
        import csv
        reader = csv.DictReader(io.StringIO(cleaned_text))
        rows = list(reader)
        if rows and isinstance(rows[0], dict):
            return rows[0]
    except Exception:
        pass

    return None


def validate_or_transform_pydantic(raw_text: str, pydantic_cls: type[T]) -> Optional[T]:
    """LLM RAW 텍스트를 Pydantic 모델로 파싱/검증/변환하는 4단계 파이프라인."""
    cleaned = clean_markdown_block(raw_text)

    try:
        data = json.loads(cleaned)
        return pydantic_cls.model_validate(data)
    except Exception:
        pass

    logger.warning(f"[GeneratorLLM] Stage 1 JSON validation failed for {pydantic_cls.__name__}. Trying Stage 2 multi-format transformation.")
    transformed_dict = parse_multiformat(cleaned)
    if transformed_dict:
        try:
            return pydantic_cls.model_validate(transformed_dict)
        except Exception as e:
            logger.warning(f"[GeneratorLLM] Stage 3 schema validation failed for {pydantic_cls.__name__}: {e}")
    else:
        logger.warning(f"[GeneratorLLM] Stage 2 multi-format transformation could not parse text.")

    logger.error(f"[GeneratorLLM] Fail-Fast: All validation/transformation stages failed for {pydantic_cls.__name__}.")
    return None

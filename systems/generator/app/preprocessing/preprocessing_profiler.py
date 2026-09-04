"""
preprocessing_profiler.py

담당 기능:
- 소스 데이터셋 파일 역할(role) 및 계열 메타데이터 프로파일링 모듈.
- LLM 및 Pydantic 스키마 검증기(FileProfileResponse)를 사용하여 소스 파일의 역할, 계열 시그니처, 타임스탬프 세맨틱을 프로파일링하고 source_family_registry.json에 저장한다.

입력:
- data_dir(str): 소스 데이터셋 디렉토리 경로
- force_reprofile(bool): True 설정 시 기존 메타데이터 캐시를 무시하고 재분석

출력:
- registry(dict): 파일명 키별 프로파일링 메타데이터 딕셔너리
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime, timezone
from typing import Any
import pandas as pd

from systems.generator.generator_config import PATHS
from systems.generator.generator_llm_client import (
    call_llm,
    validate_or_transform_pydantic,
    FileProfileResponse,
)

logger = logging.getLogger(__name__)

FAMILY_REGISTRY_PATH = PATHS.source_family_registry

ID_CANDIDATES = ["asset_id", "machineID", "equipment_id", "device_id", "asset", "machine"]
TIME_CANDIDATES = [
    "observed_at", "datetime", "timestamp", "time", "date",
    "degradation_started_at", "failure_occurred_at", "maintenance_started_at", "maintenance_completed_at"
]


def infer_key_signature(columns: list[str]) -> tuple[str | None, str | None]:
    """컬럼 목록에서 id/time 후보를 찾아 시그니처로 반환한다."""
    id_col = next((c for c in ID_CANDIDATES if c in columns), None)
    time_col = next((c for c in TIME_CANDIDATES if c in columns), None)
    return id_col, time_col


def compute_family_id(id_col: str | None, time_col: str | None) -> str:
    """id_col과 time_col 조합으로 계열 식별키를 생성한다."""
    return f"{id_col or 'unknown'}::{time_col or 'unknown'}"


def profile_source_file_with_llm(filepath: str, filename: str, df_preview: pd.DataFrame) -> dict[str, Any]:
    """LLM을 통해 파일의 역할(role)과 컬럼 메타데이터를 프로파일링한다."""
    all_columns = [str(c) for c in df_preview.columns]
    sample_json = df_preview.head(10).to_json(orient="records", date_format="iso")

    system_prompt = (
        "You are an expert industrial manufacturing data profiler.\n"
        "Analyze the source dataset file and output a detailed metadata JSON schema.\n"
        "Output ONLY a valid JSON object matching the exact format:\n"
        "{\n"
        '  "role": "failure_event" | "telemetry_sensor" | "maintenance_history" | "machine_master" | "error_event" | "evaluation_truth" | "unknown",\n'
        '  "description": "Clear explanation of what this dataset records and its business context.",\n'
        '  "id_columns": ["asset_id", ...],\n'
        '  "time_columns": [\n'
        '    {"name": "column_name", "semantic": "period_start" | "period_end" | "failure_point" | "maintenance_start" | "timestamp"}\n'
        '  ],\n'
        '  "column_notes": {\n'
        '    "column_name": "note explaining structural role, source dtype, unit, timestamp format, or parsing requirement"\n'
        '  },\n'
        '  "confidence": 0.0 ~ 1.0\n'
        "}"
    )

    user_prompt = f"Filename: {filename}\nColumns ({len(all_columns)}): {all_columns}\nSample Data (up to 10 rows):\n{sample_json}"

    try:
        raw_res = call_llm(user_prompt, system=system_prompt)
        profile_res = validate_or_transform_pydantic(raw_res, FileProfileResponse)
        if not profile_res:
            raise ValueError(f"Pydantic profile validation failed for raw: '{raw_res[:100]}'")

        confidence = profile_res.confidence
        status = "auto_confirmed" if confidence >= 0.7 else "pending"

        id_col, time_col = infer_key_signature(all_columns)
        family_id = compute_family_id(id_col, time_col)

        col_notes = profile_res.column_notes
        for col in all_columns:
            if col not in col_notes:
                col_notes[col] = "일반 속성 컬럼"

        time_cols_parsed = profile_res.time_columns
        if not time_cols_parsed and time_col:
            time_cols_parsed = [{"name": time_col, "semantic": "timestamp"}]

        id_cols_parsed = profile_res.id_columns
        if not id_cols_parsed and id_col:
            id_cols_parsed = [id_col]

        meta = {
            "family_id": family_id,
            "id_col": id_col,
            "time_col": time_col,
            "role": profile_res.role,
            "description": profile_res.description or f"Data source for {filename}",
            "all_columns": all_columns,
            "id_columns": id_cols_parsed,
            "time_columns": time_cols_parsed,
            "column_notes": col_notes,
            "confidence": confidence,
            "status": status,
            "profiled_at": datetime.now(timezone.utc).isoformat(),
            "provenance": {"model": "gpt-4o-mini", "sample_rows_used": min(10, len(df_preview))}
        }
        return meta
    except Exception as e:
        logger.warning(f"[SourceFamily] LLM profiling failed for '{filename}': {e}. Falling back to rule-based profiling.")
        id_col, time_col = infer_key_signature(all_columns)
        family_id = compute_family_id(id_col, time_col)

        role = "failure_event" if "failure" in filename.lower() else ("telemetry_sensor" if any(
            k in filename.lower() for k in ("telemetry", "sensor", "observation")) else "unknown")

        time_cols_rule = []
        for c in all_columns:
            if c in TIME_CANDIDATES:
                semantic = "period_start" if "start" in c else ("period_end" if "end" in c or "complete" in c else (
                    "failure_point" if "occurred" in c or "fail" in c else "timestamp"))
                time_cols_rule.append({"name": c, "semantic": semantic})

        col_notes_rule = {c: "컬럼 속성 (자동 할당)" for c in all_columns}

        return {
            "family_id": family_id,
            "id_col": id_col,
            "time_col": time_col,
            "role": role,
            "description": f"Rule-based profiled dataset for {filename}",
            "all_columns": all_columns,
            "id_columns": [c for c in all_columns if c in ID_CANDIDATES],
            "time_columns": time_cols_rule if time_cols_rule else ([{"name": time_col, "semantic": "timestamp"}] if time_col else []),
            "column_notes": col_notes_rule,
            "confidence": 0.85,
            "status": "auto_confirmed",
            "profiled_at": datetime.now(timezone.utc).isoformat(),
            "provenance": {"model": "rule_based_fallback", "sample_rows_used": len(df_preview)}
        }


def build_family_registry(data_dir: str, force_reprofile: bool = False) -> dict[str, Any]:
    """data_dir 내 모든 지원 파일의 전체 컬럼과 구조를 스캔하여 메타데이터를 구축한다."""
    logger.info(f"[SourceFamily] Building family registry for data_dir: '{data_dir}' (force_reprofile={force_reprofile})...")
    if not os.path.exists(data_dir):
        logger.warning(f"[SourceFamily] Directory '{data_dir}' missing. Returning empty registry.")
        return {}

    existing_registry = load_family_registry()
    registry = dict(existing_registry)
    valid_exts = (".csv", ".xlsx", ".xls")

    updated_count = 0
    for filename in sorted(os.listdir(data_dir)):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in valid_exts:
            continue

        existing_meta = registry.get(filename)
        if not force_reprofile and existing_meta and "role" in existing_meta and "all_columns" in existing_meta:
            logger.info(f"[SourceFamily] Cache Hit for '{filename}' -> keeping metadata.")
            continue

        filepath = os.path.join(data_dir, filename)
        try:
            preview = pd.read_csv(filepath, nrows=10) if ext == ".csv" else pd.read_excel(filepath, nrows=10)
            meta = profile_source_file_with_llm(filepath, filename, preview)
            registry[filename] = meta
            updated_count += 1
            logger.info(f"[SourceFamily] Profiled '{filename}': role='{meta.get('role')}', cols={len(meta.get('all_columns', []))}, confidence={meta.get('confidence')}")
        except Exception as e:
            logger.warning(f"[SourceFamily] Failed to profile '{filename}': {e}")

    registry_file_path = os.path.abspath(FAMILY_REGISTRY_PATH)
    os.makedirs(os.path.dirname(registry_file_path), exist_ok=True)
    with open(registry_file_path, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)

    logger.info(f"[SourceFamily] Family registry saved to '{FAMILY_REGISTRY_PATH}' with {len(registry)} entries ({updated_count} profiled).")
    return registry


def load_family_registry() -> dict[str, Any]:
    """레지스트리 파일에서 프로파일링 결과를 조회한다."""
    if not FAMILY_REGISTRY_PATH.exists():
        return {}
    with open(FAMILY_REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

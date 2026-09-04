"""
mapping_agent.py

담당 기능:
- 소스 컬럼과 온톨로지 개념(Target Node) 간의 LLM 기반 매퍼 에이전트.
- catalog.yaml의 동적 온톨로지 노드 및 Stage 0 프로파일링 메타데이터(파일 역할, 설명, 컬럼 비고) 맥락을 주입받아 LLM으로 매핑 대상 및 확신도(confidence)를 추론한다.

입력:
- column_name(str): 소스 데이터셋 컬럼명
- sample_values(list): 컬럼 샘플 값 목록 (최대 5건)
- store(MappingStore): 매핑 결과를 누적할 MappingStore 객체
- file_metadata(dict, optional): Stage 0 프로파일링 메타데이터

출력:
- MappingRecord: 매핑 결과 레코드 객체

의존 모듈:
- systems.generator.generator_llm_client.call_llm: LLM 추론 실행.
- mapping_cache.py: MappingStore 및 MappingRecord.
- extraction.extraction_profiler.load_family_registry: Stage 0 메타데이터 조회.

예외/경계 상황:
- LLM 추론 실패 또는 JSON 파싱 에러 시 target_ontology를 "Unknown"으로, confidence를 0.0으로 폴백한다.
- Stage 0 메타데이터의 confidence가 0.7 미만이거나 status가 pending인 파일은 매핑을 생략한다.

설계 원칙과의 연결:
- docs/architecture.md의 '맥락 주입 매핑' 원칙에 따라 단순 컬럼명 추론을 넘어 파일 역할과 세맨틱 비고를 LLM에 전달한다.
"""

import json
import logging
import os
import yaml
from systems.generator.ontology_mapping.mapping_cache import (
    MappingStore,
    MappingRecord,
    MAPPING_CACHE_PATH,
    get_mapping_store,
)
from systems.generator.generator_llm_client import (
    call_llm,
    validate_or_transform_pydantic,
    ColumnMappingResponse,
)
from systems.generator.extraction.extraction_profiler import load_family_registry

logger = logging.getLogger(__name__)

DEFAULT_ONTOLOGY_NODES = [
    "Voltage", "Rotation", "Pressure", "Vibration",
    "AirTemperature", "ProcessTemperature", "RotationalSpeed", "Torque", "ToolWear",
    "Equipment", "Timestamp", "ErrorEvent", "FailureEvent", "MaintenanceEvent", "Unknown"
]


def load_catalog_nodes() -> list:
    """catalog.yaml 파일에서 정의된 온톨로지 노드들을 로드하여 기본 노드와 병합한다."""
    catalog_path = os.path.join(os.path.dirname(__file__), "..", "feature", "feature_catalog.yaml")
    if not os.path.exists(catalog_path):
        catalog_path = os.path.join(os.path.dirname(__file__), "..", "feature", "catalog.yaml")

    nodes = list(DEFAULT_ONTOLOGY_NODES)
    if os.path.exists(catalog_path):
        try:
            with open(catalog_path, "r", encoding="utf-8") as f:
                cat_features = yaml.safe_load(f).get("features", {})
                for node in cat_features.keys():
                    if node not in nodes:
                        nodes.append(node)
        except Exception as e:
            logger.warning(f"[MappingAgent] Failed to load catalog yaml for dynamic prompt: {e}")
    return nodes


def build_system_prompt(nodes: list) -> str:
    """온톨로지 노드 목록을 포함하는 시스템 프롬프트를 생성한다."""
    nodes_str = ", ".join(nodes)
    return (
        "당신은 제조 데이터 온톨로지 매핑 전문가입니다.\n"
        "주어진 컬럼명, 파일 역할 맥락, 샘플 값을 보고 아래 온톨로지 노드 목록 중 가장 적합한 하나를 선택하여 매핑하세요:\n"
        f"{nodes_str}\n\n"
        "반드시 JSON 형식으로만 응답하세요: {\"ontology_node\": \"...\", \"confidence\": 0.0~1.0, \"reason\": \"...\"}"
    )


def map_column(column_name: str, sample_values: list, store: MappingStore, file_metadata: dict | None = None) -> MappingRecord:
    """단일 컬럼에 대해 LLM으로 온톨로지 매핑을 추론하고 레코드를 반환한다."""
    logger.info(f"[MappingAgent] Agent processing column: '{column_name}' with samples: {sample_values[:3]}")

    nodes = load_catalog_nodes()
    base_prompt = build_system_prompt(nodes)

    context = ""
    if file_metadata:
        role = file_metadata.get("role", "unknown")
        desc = file_metadata.get("description", "")
        notes = file_metadata.get("column_notes", {}).get(column_name, "")
        context = (
            f"[파일 맥락 정보]\n"
            f"- 파일 설명: {desc}\n"
            f"- 파일 역할 (Role): {role}\n"
        )
        if notes:
            context += f"- 컬럼 비고: {notes}\n"
        context += "\n"

    system_prompt = context + base_prompt
    prompt = f"컬럼명: {column_name}\n샘플 값: {sample_values[:5]}"

    try:
        raw = call_llm(prompt, system=system_prompt)
        logger.debug(f"[MappingAgent] LLM raw response for '{column_name}': {raw}")
        parsed = validate_or_transform_pydantic(raw, ColumnMappingResponse)
        if not parsed:
            raise ValueError(f"Failed to validate or transform LLM response: '{raw[:100]}'")
        target = parsed.ontology_node
        confidence = float(parsed.confidence)
        reason = parsed.reason or ""
    except Exception as e:
        logger.warning(f"[MappingAgent] LLM mapping inference failed for '{column_name}': {e}. Applying heuristic fallback.")
        # Heuristic fallback for standard sensor column names
        c_lower = column_name.lower()
        if "voltage" in c_lower:
            target, confidence = "Voltage", 0.8
        elif "rotation" in c_lower and "speed" not in c_lower:
            target, confidence = "Rotation", 0.8
        elif "pressure" in c_lower:
            target, confidence = "Pressure", 0.8
        elif "vibration" in c_lower:
            target, confidence = "Vibration", 0.8
        elif "air" in c_lower and "temp" in c_lower:
            target, confidence = "AirTemperature", 0.8
        elif "process" in c_lower and "temp" in c_lower:
            target, confidence = "ProcessTemperature", 0.8
        elif "speed" in c_lower or "rpm" in c_lower:
            target, confidence = "RotationalSpeed", 0.8
        elif "torque" in c_lower:
            target, confidence = "Torque", 0.8
        elif "tool" in c_lower and "wear" in c_lower:
            target, confidence = "ToolWear", 0.8
        else:
            target, confidence = "Unknown", 0.0
        reason = f"Heuristic fallback due to inference exception: {e}"

    logger.info(f"[MappingAgent] Agent mapped '{column_name}' -> '{target}' (confidence: {confidence:.2f}) Reason: {reason}")

    record = MappingRecord(
        source_field=column_name,
        target_ontology=target,
        source="mapping_agent",
        confidence=confidence,
        status="pending" if confidence < 0.7 else "auto_mapped",
    )
    store.add_mapping(record)
    return record


def map_all_sources(sources: dict, store: MappingStore = None) -> MappingStore:
    """모든 소스 데이터셋의 컬럼들을 순회하며 미매핑된 컬럼을 LLM으로 매핑한다."""
    logger.info("[MappingAgent] Starting agent-based mapping for all sources (with Stage 0 file metadata context)...")
    if store is None:
        store = get_mapping_store()

    family_registry = load_family_registry()

    updated = False
    for source_key, df in sources.items():
        matched_filename = next(
            (fname for fname in family_registry if os.path.splitext(fname)[0] == source_key), None
        )
        file_meta = family_registry.get(matched_filename) if matched_filename else None

        if file_meta and (file_meta.get("status") == "pending" or float(file_meta.get("confidence", 1.0)) < 0.7):
            logger.warning(f"[MappingAgent] Skipping mapping for source dataset '{source_key}' because file metadata status is '{file_meta.get('status')}' (confidence={file_meta.get('confidence')}).")
            continue

        logger.info(f"[MappingAgent] Mapping source dataset: '{source_key}' ({len(df.columns)} columns) with metadata role='{file_meta.get('role') if file_meta else 'none'}'")
        for col in df.columns:
            if store.get_mapping(col) is not None:
                continue

            sample = df[col].dropna().astype(str).head(5).tolist()
            map_column(col, sample, store, file_metadata=file_meta)
            updated = True

    if updated:
        store.save_to_file(MAPPING_CACHE_PATH)
        logger.info(f"[MappingAgent] Updated mapping file saved to '{MAPPING_CACHE_PATH}'.")

    logger.info(f"[MappingAgent] Completed agent mapping. Total mappings in store: {len(store.get_all())}")
    return store

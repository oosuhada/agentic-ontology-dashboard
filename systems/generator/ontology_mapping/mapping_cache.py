"""
mapping_cache.py

담당 기능:
- 온톨로지 매핑 레코드(`MappingRecord`) 및 경로 레지스트리(PATHS.mapping_cache) 영속 저장소(`MappingStore`) 모듈.
- 프로세스 전역에서 단일 저장소(싱글톤)로 동작하며 mapping_cache.json 파일과의 동기화를 관리한다.

입력:
- source_field(str): 소스 데이터셋 컬럼명
- target_ontology(str): 표준 온톨로지 노드명
- confidence(float): 0.0 ~ 1.0 확신도

출력:
- MappingStore: 매핑 레코드 딕셔너리를 관리하는 객체
- get_mapping_store(): 싱글톤 인스턴스 반환

의존 모듈:
- pydantic.BaseModel: 매핑 레코드 스키마 정의
- systems.generator.generator_config.PATHS: 전역 경로 레지스트리

예외/경계 상황:
- 매핑 캐시 파일 미존재 시 빈 매핑으로 초기화한다.

설계 원칙과의 연결:
- docs/architecture.md의 '단일 경로 제어 온톨로지 캐시' 원칙에 따라 PATHS 레지스트리를 참조한다.
"""

import json
import os
from pathlib import Path
from pydantic import BaseModel
from typing import Dict, Optional
from systems.generator.generator_config import PATHS

MAPPING_CACHE_PATH = PATHS.mapping_cache


class MappingRecord(BaseModel):
    source_field: str
    target_ontology: str
    source: str
    confidence: float
    status: str


class MappingStore:
    def __init__(self):
        self._mappings: Dict[str, MappingRecord] = {}

    def add_mapping(self, record: MappingRecord):
        self._mappings[record.source_field] = record

    def get_mapping(self, source_field: str) -> Optional[MappingRecord]:
        return self._mappings.get(source_field)

    def confirm_mapping(self, source_field: str):
        if source_field in self._mappings:
            self._mappings[source_field].status = "confirmed"
            self._mappings[source_field].source = "user_confirmed"
            self._mappings[source_field].confidence = 1.0

    def get_all(self):
        return self._mappings

    def load_from_file(self, path: Path = MAPPING_CACHE_PATH):
        path_obj = Path(path)
        if not path_obj.exists():
            return
        with open(path_obj, "r", encoding="utf-8") as f:
            data = json.load(f)
        for source_field, v in data.items():
            self._mappings[source_field] = MappingRecord(source_field=source_field, **v)

    def save_to_file(self, path: Path = MAPPING_CACHE_PATH):
        path_obj = Path(path)
        data = {
            k: {
                "target_ontology": v.target_ontology,
                "source": v.source,
                "confidence": v.confidence,
                "status": v.status,
            }
            for k, v in self._mappings.items()
        }
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        with open(path_obj, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


_singleton_instance: Optional["MappingStore"] = None


def get_mapping_store() -> "MappingStore":
    """프로세스 전역에서 공유되는 MappingStore 싱글톤을 반환한다."""
    global _singleton_instance
    if _singleton_instance is None:
        _singleton_instance = MappingStore()
        _singleton_instance.load_from_file(MAPPING_CACHE_PATH)
    return _singleton_instance


def reload_mapping_store() -> "MappingStore":
    """캐시 파일이 외부에서 갱신된 뒤 강제로 다시 로드해야 할 때 사용한다."""
    global _singleton_instance
    _singleton_instance = MappingStore()
    _singleton_instance.load_from_file(MAPPING_CACHE_PATH)
    return _singleton_instance

"""
__init__.py (ontology_mapping package)

담당 기능:
- ontology_mapping 도메인 공개 모듈 초기화 및 서비스 함수 파사드.

입력:
- None

출력:
- export symbols: map_all_sources, map_column, get_mapping_store, detect_capabilities

의존 모듈:
- mapping_agent: map_all_sources, map_column
- mapping_cache: get_mapping_store
- ontology_mapping_capability_service: detect_capabilities

예외/경계 상황:
- None

설계 원칙과의 연결:
- docs/architecture.md의 '도메인 서비스 파사드' 원칙에 따라 외부에 일관된 진입점을 제공한다.
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[3])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from systems.generator.ontology_mapping.mapping_agent import map_all_sources, map_column
from systems.generator.ontology_mapping.mapping_cache import get_mapping_store
from systems.generator.ontology_mapping.ontology_mapping_capability_service import detect_capabilities

__all__ = ["map_all_sources", "map_column", "get_mapping_store", "detect_capabilities"]

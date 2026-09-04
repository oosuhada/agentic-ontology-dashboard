"""
feature_catalog.py

담당 기능:
- 온톨로지 기반 피처 추출 카탈로그(catalog.yaml) 로더 및 파일 변경 감지(mtime) 메모리 캐시 모듈.

입력:
- path(str, optional): 카탈로그 YAML 파일 경로. 미지정 시 feature_catalog.yaml 또는 catalog.yaml 자동 탐색.

출력:
- catalog(dict): {ontology_node: list[rule_dict]} 형태의 피처 추출 규칙 딕셔너리

의존 모듈:
- yaml: YAML 파일 파싱
- os, logging: 파일 존재 여부 및 수정 시각 검사, 로그 기록

예외/경계 상황:
- 지정된 경로에 카탈로그 파일이 존재하지 않는 경우 경고 로그를 남기고 빈 딕셔너리를 반환한다.

설계 원칙과의 연결:
- docs/architecture.md의 '피처 카탈로그 동적 구성' 원칙에 따라 카탈로그 파일 변경 시 프로세스 재시작 없이 자동 갱신한다.
"""

import os
import yaml
import logging

logger = logging.getLogger(__name__)

_catalog_cache: dict[str, tuple[float, dict]] = {}


def load_catalog(path: str = None) -> dict:
    """catalog.yaml 파일에서 피처 추출 규칙을 읽고 메모리에 캐싱하여 반환한다."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "feature_catalog.yaml")
        if not os.path.exists(path):
            path = os.path.join(os.path.dirname(__file__), "catalog.yaml")

    if not os.path.exists(path):
        logger.warning(f"[FeatureCatalog] Catalog path '{path}' does not exist.")
        return {}

    mtime = os.path.getmtime(path)
    cached = _catalog_cache.get(path)
    if cached and cached[0] == mtime:
        logger.debug(f"[FeatureCatalog] Reusing cached catalog from: {path}")
        return cached[1]

    logger.info(f"[FeatureCatalog] Loading feature catalog from: {path} (mtime: {mtime})")
    with open(path, "r", encoding="utf-8") as f:
        raw_yaml = yaml.safe_load(f) or {}
        catalog = raw_yaml.get("features", {})
        logger.info(f"[FeatureCatalog] Loaded catalog rules for nodes: {list(catalog.keys())}")
        _catalog_cache[path] = (mtime, catalog)
        return catalog

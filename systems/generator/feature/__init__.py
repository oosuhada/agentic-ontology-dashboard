"""
__init__.py (feature package)

담당 기능:
- feature 도메인 공개 모듈 초기화 및 서비스 함수 파사드.

입력:
- None

출력:
- export symbols: load_catalog, build_features, save_features_npy, load_features_npy, build_labels

의존 모듈:
- feature_catalog: load_catalog
- feature_builder: build_features, save_features_npy, load_features_npy
- feature_label_service: build_labels

예외/경계 상황:
- dataset 모듈에 대한 __getattr__ 레이지 로딩 지원.

설계 원칙과의 연결:
- docs/architecture.md의 '도메인 서비스 파사드' 원칙에 따라 외부에 일관된 진입점을 제공한다.
"""

import sys
from pathlib import Path

_project_root = str(Path(__file__).resolve().parents[3])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from systems.generator.feature.feature_catalog import load_catalog
from systems.generator.feature.feature_builder import build_features, save_features_npy, load_features_npy
from systems.generator.feature.feature_label_service import build_labels


def __getattr__(name: str):
    if name in {"DatasetAudit", "audit_ai4i", "canonicalize", "load_ai4i"}:
        from . import dataset

        return getattr(dataset, name)
    raise AttributeError(name)


__all__ = [
    "load_catalog",
    "build_features",
    "save_features_npy",
    "load_features_npy",
    "build_labels",
    "DatasetAudit",
    "audit_ai4i",
    "canonicalize",
    "load_ai4i",
]

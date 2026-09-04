"""
topology_service.py

담당 기능:
- topology_agent의 추론 결과를 바탕으로 인접 행렬(Adjacency Matrix) 및 위상 데이터를 구성한다.
  설비 네트워크 그래프 구조를 계산 가능한 형태의 노드/엣지 데이터셋으로 변환하여
  다음 단계인 feature 생성 파이프라인으로 전달한다.

입력:
- topology_agent.py의 `TopologyGraph` 객체.

출력:
- Feature 생성을 위한 설비 위상 인접 행렬 및 노드 관계 데이터셋 (`TopologyMatrixData`).

의존 모듈:
- topology_agent.py (추론 그래프 수용)
- topology_cache.py (위상 데이터 캐시 조회)

예외/경계 상황:
- 연결선 엣지 가중치 계산 오류 시 `TopologyBuildError`를 발생시킨다.

설계 원칙과의 연결:
- docs/architecture.md 1장 컨벤션에 따라 {도메인}_{계층}.py 규칙을 지킨다.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


REQUIRED_RELATION_FIELDS = ("source_asset_id", "relationship_type", "target_asset_id")


class TopologyService:
    """위상 데이터 구성 서비스 클래스 스켈레톤"""

    pass


def normalize_relation(relation: Mapping[str, Any]) -> dict[str, str]:
    """Validate source-provided relations without promoting topology to causal truth."""

    missing = [field for field in REQUIRED_RELATION_FIELDS if not relation.get(field)]
    if missing:
        raise ValueError(f"asset relation is missing required fields: {missing}")
    return {field: str(relation[field]) for field in REQUIRED_RELATION_FIELDS}


def _self_test() -> None:
    """
    이 모듈을 단독 실행했을 때 수행되는 기능 테스트.
    실제 검증 로직은 이 모듈의 실제 구현 작업에서 채운다.
    """
    print("[SELF-TEST] topology_service.py - 아직 테스트 로직이 구현되지 않았습니다.")


if __name__ == "__main__":
    _self_test()

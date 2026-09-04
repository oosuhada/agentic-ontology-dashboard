"""
mapping_service.py

담당 기능:
- 온톨로지 매핑 서비스 재노출(Re-export) 인터페이스 모듈.
- mapping_agent.py가 매핑 오케스트레이션을 담당하므로, 외부 모듈 호출 호환성을 위해 map_all_sources 함수 및 관련 서비스를 재노출한다.

입력:
- sources(dict): 파싱 완료된 소스 데이터프레임 딕셔너리
- store(MappingStore, optional): 매핑 저장소 인스턴스

출력:
- MappingStore: 갱신된 매핑 저장소 인스턴스

의존 모듈:
- ontology_mapping.mapping_agent: map_all_sources 함수 재노출

예외/경계 상황:
- 매핑 실패 시 MappingAgent 내부의 안전한 폴백(Unknown 매핑) 처리를 그대로 활용한다.

설계 원칙과의 연결:
- docs/architecture.md의 '도메인 서비스 파사드' 원칙에 따라 외부에 일관된 서비스 진입점을 제공한다.
"""

from systems.generator.ontology_mapping.mapping_agent import map_all_sources

__all__ = ["map_all_sources"]

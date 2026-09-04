"""
ontology_mapping_capability_service.py

담당 기능:
- 온톨로지 매핑 상태 기반 도메인 역량(Capability) 판별 서비스 모듈.
- MappingStore에 등록된 target_ontology 노드들의 존재 여부를 분석하여 시스템이 현재 수행 가능한 분석 기능들(EquipmentMonitoring, SensorAnalytics, MaintenanceHistory, FailurePrediction, ErrorTracking)을 딕셔너리로 판별한다.

입력:
- store(MappingStore): 온톨로지 매핑 저장소 객체

출력:
- capabilities(dict): {capability_name(str): is_supported(bool)} 형태의 도메인 역량 맵

의존 모듈:
- ontology_mapping.mapping_cache.MappingStore: 매핑 노드 조회

예외/경계 상황:
- 매핑 저장소가 비어있거나 특정 노드가 매핑되지 않은 경우 해당 역량 항목을 False로 처리한다.

설계 원칙과의 연결:
- docs/architecture.md의 '역량 자동 감지' 원칙에 따라 데이터 매핑 상태에 기반해 제공 가능한 기능을 동적으로 판단한다.
"""

from systems.generator.ontology_mapping.mapping_cache import MappingStore


def detect_capabilities(store: MappingStore) -> dict:
    """MappingStore에 저장된 target_ontology 필드들을 기반으로 시스템이 실행 가능한 도메인 역량을 감지한다."""
    mapped_targets = {v.target_ontology for v in store.get_all().values()}

    capabilities = {
        "EquipmentMonitoring": "Equipment" in mapped_targets,
        "SensorAnalytics": any(t in mapped_targets for t in [
            "Voltage", "Rotation", "Pressure", "Vibration",
            "AirTemperature", "ProcessTemperature", "RotationalSpeed", "Torque", "ToolWear"
        ]),
        "MaintenanceHistory": "MaintenanceEvent" in mapped_targets,
        "FailurePrediction": "FailureEvent" in mapped_targets,
        "ErrorTracking": "ErrorEvent" in mapped_targets,
    }
    return capabilities

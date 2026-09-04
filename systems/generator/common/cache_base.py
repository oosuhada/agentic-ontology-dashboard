"""
cache_base.py

담당 기능:
- generator 내 3종 캐시(extraction_cache, mapping_cache, topology_cache)가 공유하는 공통 지문(Fingerprint)
  생성 및 JSON/파일 기반 캐시 저장/조회 핵심 로직을 담당하는 추상 베이스 클래스이다.

입력:
- 대상 데이터 파일/메타데이터의 바이트/문자열 지문 키 (`str`).

출력:
- 직렬화된 캐시 파일 저장 결과 및 복원된 객체.

의존 모듈:
- 하위 extraction_cache, mapping_cache, topology_cache 모듈에서 상속하여 사용된다.

예외/경계 상황:
- 이 모듈은 추상 베이스 및 공통 캐시 알고리즘 정의 모듈이므로 단독 실행이 성립하지 않는다.
  아래 __main__ 블록은 실수로 직접 실행했을 때 비정상 종료를 명시하기 위한 것이다.

설계 원칙과의 연결:
- docs/architecture.md 3장의 'cache_base' 공통 fingerprint->결과 캐시 로직 스펙을 지킨다.
"""

import sys


class CacheBase:
    """캐시 추상 베이스 클래스 스켈레톤"""

    pass


if __name__ == "__main__":
    print(
        "[ERROR] cache_base.py는 단독 실행 대상이 아닙니다. "
        "다른 Cache 모듈에서 import하여 상속 사용하십시오.",
        file=sys.stderr,
    )
    sys.exit(1)

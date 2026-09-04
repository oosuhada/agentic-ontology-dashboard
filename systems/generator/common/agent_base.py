"""
agent_base.py

담당 기능:
- generator 내 모든 Agent(extraction_agent, mapping_agent, topology_agent)가 상속받는 추상 베이스 클래스를 정의한다.
  "하나의 LLM 호출은 오직 하나의 단일 판단만 담당한다"는 판단 단위 분리 원칙을 시스템 차원에서 강제하도록
  단일 추상 인터페이스 메서드만을 제공하는 프레임워크 베이스 구조이다.

입력:
- 상속받는 개별 Agent 구현체가 정의하는 입력 콘텍스트.

출력:
- 개별 Agent 판단 결과 데이터 객체.

의존 모듈:
- 하위 extraction_agent, mapping_agent, topology_agent 모듈에서 상속하여 사용된다.

예외/경계 상황:
- 이 모듈은 추상 베이스 클래스 정의 모듈이므로 단독 실행이 성립하지 않는다. 아래 __main__ 블록은
  실수로 직접 실행했을 때 비정상 종료로 이를 명시적 차단하기 위한 것이다.

설계 원칙과의 연결:
- docs/architecture.md 3장의 '판단 단위 분리' 원칙을 강제하는 공통 베이스 규칙을 적용한다.
"""

import sys


class AgentBase:
    """Agent 추상 베이스 클래스 스켈레톤"""

    pass


if __name__ == "__main__":
    print(
        "[ERROR] agent_base.py는 단독 실행 대상이 아닙니다. "
        "다른 Agent 모듈에서 import하여 상속 사용하십시오.",
        file=sys.stderr,
    )
    sys.exit(1)

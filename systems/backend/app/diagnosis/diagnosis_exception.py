"""
diagnosis_exception.py

담당 기능:
- 진단 도메인 예외 처리 클래스들을 정의한다 (DiagnosisModelNotFoundError, DiagnosisInferenceError 등).

입력:
- 에러 상세 메시지.

출력:
- 예외 인스턴스.

의존 모듈:
- diagnosis_service.py

예외/경계 상황:
- 단독 실행 비대상 파일이다.

설계 원칙과의 연결:
- 프로젝트 전역 예외 처리 체계를 지킨다.
"""

import sys


class DiagnosisModelNotFoundError(Exception):
    """모델 미발견 예외 클래스 스켈레톤"""

    pass


if __name__ == "__main__":
    print(
        "[ERROR] diagnosis_exception.py는 단독 실행 대상이 아닙니다. "
        "다른 모듈에서 import하여 사용하십시오.",
        file=sys.stderr,
    )
    sys.exit(1)

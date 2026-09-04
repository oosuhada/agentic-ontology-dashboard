"""
diagnosis_service.py

담당 기능:
- `MODEL_ARTIFACT_URI`로 주입된 provider에서 versioned Model Artifact를 읽기 전용으로 로드한다.
- Model Artifact의 manifest/version/checksum/compatibility를 확인한 뒤 current observation에 runtime inference를 수행한다.
- 특정 asset + observation time의 제품 Result Artifact와 Evidence/provenance를 생성·조립한다.
- 백엔드는 직접 모델 학습을 수행하지 않으며, diagnosis가 제품 Result Artifact의 최종 producer다.

입력:
- diagnosis_router.py로부터 수신된 DiagnosisPredictRequest 객체.

출력:
- 진단 및 추론 연산 결과가 담긴 DiagnosisPredictResponse 객체와 제품 Result Artifact/Evidence 계약.

의존 모듈:
- 외부 주입된 Model Artifact provider (`MODEL_ARTIFACT_URI`)
- diagnosis_schema.py (요청/응답 규격 파싱)

예외/경계 상황:
- artifact가 없거나 manifest가 비호환/손상되었거나 모델 로드에 실패하면 DiagnosisModelNotFoundError 또는 계약 검증 오류를 발생시킨다.
- sibling `../generator/...` 경로를 fallback으로 탐색하지 않는다.

설계 원칙과의 연결:
- docs/architecture.md의 Model Artifact contract, Backend Product Runtime, Result Artifact/Evidence 최종 producer 원칙을 적용한다.
"""


class DiagnosisService:
    """설비 실시간 진단 서비스.

    ML/runtime dependencies are imported lazily so the PR #10 backend scaffold
    can still run its lightweight architecture/import smoke before optional
    model dependencies are installed.
    """

    def predict_fixture(self, fixture: dict) -> dict:
        from .predictor import configured_predictor

        return configured_predictor().predict(fixture).to_dict()

    def result_artifact(self, fixture: dict) -> dict:
        from .evidence import build_product_result_artifact

        return build_product_result_artifact(fixture)

    def evidence(self, fixture: dict, *, context_provider=None) -> dict:
        from .evidence import build_evidence_package

        return build_evidence_package(fixture, context_provider=context_provider)


def _self_test() -> None:
    """
    이 모듈을 단독 실행했을 때 수행되는 기능 테스트.
    실제 검증 로직은 이 모듈의 실제 구현 작업에서 채운다.
    """
    service = DiagnosisService()
    assert callable(service.predict_fixture)
    assert callable(service.result_artifact)
    assert callable(service.evidence)
    print("[SELF-TEST] diagnosis_service.py - runtime facade 준비 완료")


if __name__ == "__main__":
    _self_test()

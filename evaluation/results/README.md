# Evaluation Results

자동 생성되는 평가 결과는 기본적으로 Git에서 제외한다.

추적할 결과는 다음 조건을 만족해야 한다.

- 재현 가능한 실행 명령이 있다.
- 사용한 데이터·모델·임계값 버전이 기록돼 있다.
- Gold 시나리오 ID와 연결된다.
- 민감정보가 포함되지 않는다.
- 최종 발표 또는 릴리즈 근거로 승인됐다.

권장 결과 범주:

- 모델 지표와 임계값 비교
- Evidence 추적률
- 리포트 수치 일치율
- 역할 적합성 평가
- UI Gold flow 결과
- LLM fallback 성공률

## Tracked Recommendation Policy v1 Artifact

`recommendation-policy-v1.json`은 PR #96 계획에 따른 Gold v1 synthetic evaluation/demo
fixture store 결과다.

- 재현 명령: `PYTHONPATH=systems/backend:. python3 scripts/seed_gold_recommendations.py --output evaluation/results/recommendation-policy-v1.json`
- 검증 명령: `PYTHONPATH=systems/backend:. python3 scripts/evaluate_gold.py --root .`
- 최근 로컬 검증: targeted backend suite 70개 통과, Gold runner 8/8 통과,
  operational recommendation/Decision/WorkOrder/Maintenance side effect 0건
- 범위: Gold 8/8 engineering acceptance, policy/source lineage, replay/no-op,
  policy-v2 별도 evaluation artifact, 새 Product Result revision lineage,
  runtime/imported writer boundary
- 미검증: PostgreSQL production E2E, 실제 정비 승인 UI, 자동 정비 실행,
  현장 정비 효과, 비용/RPN 최적화, LLM 기반 추천 결정

이 artifact는 운영 추천 테이블 seed가 아니다. `fixture_recommendations[*].store`는
`evaluation_demo_fixture`이고, `do_not_operationalize=true`로 고정된다. Gold 8/8은
engineering acceptance evidence일 뿐 현장 효과나 비용 절감 증거가 아니다.

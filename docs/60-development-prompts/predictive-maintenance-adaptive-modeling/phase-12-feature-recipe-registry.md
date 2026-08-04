# Phase 12 — Ontology-Aware Feature Recipe Registry

````text
@devspace-codex

다음 프로젝트를 실제 checkout 모드로 열어줘.

/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/mvp-프로젝트2

다음 두 경로는 참고용으로만 열고 수정하지 마.

V3.1 package:
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/predictive_maintenance_canonical_v3.1

prototype:
/Users/gabrieljang/Documents/Macbook air personal/비스텔리전스 파이널 프로젝트/prototype_share

먼저 다음을 읽어줘.

- docs/30-implementation/predictive-maintenance-adaptive-modeling-integration-plan.md
- Phase 9~11 구현과 commit
- approved mapping set와 capability requirement contract
- ml/src/factory_signal_ml/contracts.py
- ml/src/factory_signal_ml/dataset.py
- ml/src/factory_signal_ml/training.py
- V3.1 AI4I derived measure 계약
- Phase 5 replay derived measure registry
- Phase 6 Semantic Field Catalog
- prototype_share/feature_catalog/catalog.yaml
- prototype_share/feature_catalog/builder.py
- prototype_share/prediction/label_builder.py

git status, 최근 commit, remote tracking을 확인하고 다른 세션의 미커밋 변경을 보존해.
현재 단계 관련 파일만 stage해.

이번 목표는 prototype_share의 ontology-based feature catalog 아이디어를 설비별 시간
정렬, leakage 방지, version/checksum, training/serving parity를 갖춘 Feature Recipe
Registry로 재구현하는 것이다.

구현 범위:

1. Feature Recipe Registry
   - recipe id/version/checksum
   - ontology property input
   - source field binding은 approved mapping set을 통해 해결
   - operation
   - parameters
   - group_by
   - order_by
   - minimum history
   - null/boundary policy
   - source grain
   - output datatype/unit
   - leakage policy
   - enabled/deprecated status
2. Allowlisted operation
   - rolling_mean
   - rolling_std
   - lag
   - diff/gradient
   - EMA
   - moving average
   - safe arithmetic derived expression registry
   - operation과 parameter JSON Schema validation
   - arbitrary Python/eval/SQL expression 금지
3. Time-series execution semantics
   - group by approved equipment/asset identifier
   - order by approved timestamp
   - stable tie-breaker
   - group boundary마다 rolling/lag state reset
   - source row order를 신뢰하지 않고 명시적으로 정렬
   - inference에서도 같은 recipe engine/version 사용
4. V3.1 recipe examples
   - air/process temperature trend
   - rotational speed rolling/diff
   - torque rolling/lag
   - tool wear lag/diff
   - allowlisted `power_w`, `temperature_gap_k`, `overstrain_load`
   - unit과 physical meaning 보존
5. Label Policy
   - failure-within-horizon label policy version
   - event time와 observation cutoff
   - horizon, lookback, embargo
   - same-event 중복과 overlapping window 정책
   - evaluation truth/hidden truth를 runtime label source로 사용 금지
6. Feature Recipe Set
   - 여러 recipe와 label policy의 immutable set
   - approved mapping set version
   - Dataset Version compatibility
   - validation report와 checksum
7. Feature Dataset Version materialization
   - source Dataset Version
   - mapping set
   - recipe set
   - label policy
   - row/feature count, time range, equipment coverage
   - materialization checksum
   - artifact URI와 media type
   - 원본 Dataset Version을 수정하거나 feature를 canonical CSV에 역기입하지 않음
8. Artifact format
   - current stack에 맞는 portable columnar format 우선
   - local artifact store port 사용
   - path separator를 identity에 포함하지 않음
   - feature names와 schema metadata 별도 저장
9. Leakage and continuity validator
   - cross-equipment window contamination
   - future timestamp access
   - label window overlap policy
   - duplicate timestamp ambiguity
   - unsorted input recovery
   - minimum history로 인한 dropped row summary
10. API/CLI
   - recipe CRUD/version publish
   - validate recipe set
   - feature materialization submit/status
   - long operation은 queued worker/CLI boundary 사용
   - synchronous request에서 전체 V3.1 feature matrix를 계산하지 않음

prototype_share의 다음 구현을 그대로 복사하지 마.

```python
df[col].rolling(...)
df[col].shift(...)
```

반드시 equipment group과 timestamp order가 적용된 결과만 허용해.

필수 검증:

- 두 equipment가 연속 배치된 fixture에서 rolling 값 혼합 0
- unsorted input과 sorted input 결과 parity
- lag/diff가 group boundary에서 reset
- future leakage 0
- duplicate timestamp tie-breaker deterministic
- minimum history와 null policy
- unit-incompatible operation 거부
- arbitrary expression/eval/SQL 거부
- unapproved mapping으로 recipe 실행 거부
- 다른 Dataset Version mapping/recipe 재사용 거부 또는 compatibility 상태
- recipe set/checksum immutability
- feature materialization idempotency
- same source+mapping+recipe+label identity 재실행 중복 없음
- V3.1 derived measure formula parity
- evaluation truth/hidden truth reference 거부
- training/inference transform parity
- artifact URI/checksum portability
- targeted ml/backend tests
- git diff --check

전체 model training과 ML Validator UI는 다음 Phase에서 수행하므로 이번 단계에서 구현하지
마. 필요한 최소 API contract와 CLI/worker test만 수행해.

검증 완료 후 이번 단계 파일만 stage해서 다음을 수행해줘.

- git commit -m "feat: add ontology feature recipe registry"
- git push origin HEAD

마지막 보고:

- recipe/recipe-set/feature-dataset 계약
- group/order/leakage 정책
- V3.1 recipe와 derived measure
- label policy
- artifact identity와 materialization 결과
- 변경 파일과 테스트
- commit hash와 push 결과
- Phase 13 Experiment Run이 사용할 Feature Dataset Version
````

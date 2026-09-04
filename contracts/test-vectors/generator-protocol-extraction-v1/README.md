# Golden Vector: generator-protocol-extraction-v1

이 테스트 벡터는 Generator Protocol Extraction 및 Canonical Observation Artifact 발행 계약을 검증하기 위한 정본 입력과 기대 산출물입니다.

- `input/protocol-records.jsonl`: gen_data SensorRecord v2 수신 프로토콜 로그 원본
- `input/static-mapping-table.json`: 승인된 정적 매핑 테이블 (Approved Static Mapping Table)
- `input/request.json`: `POST /extraction` API 요청 데이터
- `expected/observations.jsonl`: 생성 기대되는 Canonical Observation JSONL 레코드
- `expected/dataset_manifest.json`: `generator-dataset-input-v1` 정본 메타데이터 Manifest
- `expected/provenance.jsonl`: 추출 이력 및 매핑 추적 provenance 로그
- `expected/response.json`: `POST /extraction` API 기대 응답 payload

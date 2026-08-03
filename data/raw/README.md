# Raw Data

## AI4I 2020

- UCI dataset ID: 601
- DOI: `10.24432/C5HS5C`
- License: CC BY 4.0
- Expected file: `ai4i2020.csv`
- Expected SHA-256: `59db4f1d9c34c58136d89e5a006ec190dcea19e9dbea74f6b3b0c6f22a44d183`

다운로드와 checksum 검증:

```bash
python scripts/fetch_ai4i.py
```

이미 검증된 로컬 CSV가 있을 때:

```bash
python scripts/fetch_ai4i.py \
  --local-source "../레퍼런스-프로젝트2/P2-엔드투엔드/agentic-predictive-maintenance/data/ai4i2020.csv"
```

원본 CSV는 Git에 커밋하지 않는다. 모델 입력, target과 failure-mode 분리, 컬럼·단위·누수 정책은 `docs/10-product/data-dictionary.md`에 기록했다.

발표와 테스트에는 `data/fixtures/`의 작은 AI4I-compatible Gold 사건만 사용한다. Fixture의 설비명, 라인, 담당자, 정지 영향과 센서 history는 synthetic demo context이며 실제 공장 사실이 아니다.

# Troubleshooting

## Web 3100 또는 API 8100 포트가 사용 중

```bash
lsof -nP -iTCP:3100 -sTCP:LISTEN
lsof -nP -iTCP:8100 -sTCP:LISTEN
```

해당 프로세스를 종료하거나 `.env`에서 `WEB_PORT`, `API_PORT`, `VITE_API_BASE_URL`을 함께 변경한다. 릴리스 게이트의 E2E는 동적 빈 포트를 사용하므로 기존 서비스와 충돌하지 않는다.

## 웹은 열리지만 사건 목록이 보이지 않음

1. `http://127.0.0.1:8100/health`를 확인한다.
2. `/tmp/factory-signal-board-api.log`를 확인한다.
3. `.env`의 `VITE_API_BASE_URL`과 API port가 일치하는지 확인한다.
4. 브라우저 개발자 도구의 Network/CORS 오류를 확인한다.

API는 보안을 위해 `localhost`와 `127.0.0.1` origin만 허용한다.

## Python import 오류

```bash
source .venv/bin/activate
pip install -e ml -e api
export PYTHONPATH="$PWD/api:$PWD/ml/src"
```

## Node 버전 오류

`web/package.json` 기준 Node `>=22.13.0`이 필요하다.

```bash
node --version
npm --version
```

## Playwright Chromium 없음

```bash
cd web
npx playwright install chromium
```

## LLM 설정했지만 fallback으로 표시됨

필수 설정:

```dotenv
LLM_MODEL=your-model
LLM_API_KEY=your-key
LLM_BASE_URL=https://api.openai.com/v1
```

Provider 호출, timeout, JSON parsing, schema, grounding 중 하나라도 실패하면 안전하게 deterministic fallback을 사용한다. 자격 증명 오류는 사용자 화면에 상세 노출하지 않는다.

## Project 3 연결 실패

```dotenv
PROJECT3_API_URL=http://127.0.0.1:<project3-port>
```

프로젝트 3 응답이 필수 계약을 지키는지 확인한다. 실패 시 `maintenance_context.provider=fixture_fallback`이 정상 동작이다.

## GS-007에서 차트가 비어 있음

의도된 동작이다. 결측·음수 토크·비단조 시간으로 인해 추론이 억제된다. 유효한 데이터를 다시 수집하기 전 고장 차트나 영향 추정을 기본 제공하지 않는다.

## 모델 파일이 없음

Gold 제품 데모는 `fixture-heuristic-v1`로 동작하므로 정상이다. AI4I 모델 artifact가 필요할 때:

```bash
python scripts/fetch_ai4i.py
PYTHONPATH=ml/src python -m factory_signal_ml.cli train data/raw/ai4i2020.csv --output ml/artifacts
```

원본 CSV와 모델 binary는 기본 Git 추적 대상이 아니다.

## 전체 상태 확인

```bash
source .venv/bin/activate
python scripts/preflight.py
PYTHONPATH=api:ml/src python scripts/release_gate.py --with-e2e
```

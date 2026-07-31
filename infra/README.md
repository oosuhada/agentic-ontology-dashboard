# Infrastructure

## Docker Compose

```bash
cd infra
docker compose up --build
```

서비스:

- `api`: FastAPI, host port 8100 → container port 8000, SQLite named volume
- `web`: Vite production preview, port 3100

LLM과 Project 3 환경 변수는 루트 `.env`에서 전달할 수 있다. 외부 서비스가 없어도 deterministic mode로 동작한다.

로컬 개발에는 더 빠른 `bash scripts/run_local.sh`를 권장한다.

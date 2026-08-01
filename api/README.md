# API

FastAPI 서비스는 Evidence, 역할별 Report, governed Layout, 후속 질문과 사용자 활동 기록을 제공한다.

## 실행

```bash
export PYTHONPATH="$PWD/api:$PWD/ml/src"
uvicorn factory_signal_board.main:app --host 127.0.0.1 --port 8100
```

- Swagger: `http://127.0.0.1:8100/docs`
- Health: `http://127.0.0.1:8100/health`

## 모듈

- `service.py`: 전체 orchestration
- `reports.py`: deterministic manager/engineer reports
- `llm.py`: OpenAI-compatible provider와 grounding fallback
- `planner.py`: 등록된 UI Block 전용 Planner
- `context.py`: Project 3 HTTP Adapter와 fallback
- `repository.py`: SQLite decision/note/conversation/audit
- `conversation.py`: 제한된 intent와 안전한 후속 질문
- `main.py`: API routes, CORS, 오류 계약

설비 제어 endpoint는 제공하지 않는다.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/api:/app/ml/src

WORKDIR /app

COPY ml /app/ml
COPY api /app/api
COPY schemas /app/schemas
COPY prompts /app/prompts
COPY data/fixtures /app/data/fixtures

ARG API_EXTRAS=""
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e /app/ml \
    && if [ -n "$API_EXTRAS" ]; then \
         python -m pip install --no-cache-dir -e "/app/api[$API_EXTRAS]"; \
       else \
         python -m pip install --no-cache-dir -e /app/api; \
       fi

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "ontology_dashboard.app:app", "--host", "0.0.0.0", "--port", "8000"]

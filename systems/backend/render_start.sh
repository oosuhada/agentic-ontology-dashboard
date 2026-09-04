#!/bin/sh
set -eu

python -m app.migrate

exec python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-10000}" \
  --no-server-header

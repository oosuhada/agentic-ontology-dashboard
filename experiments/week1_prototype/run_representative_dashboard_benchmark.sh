#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv-week1/bin/python}"

cd "$ROOT"
PYTHONPATH="experiments/week1_prototype" \
  "$PYTHON" experiments/week1_prototype/benchmark_representative_dashboard.py \
  --sequential-requests 300 \
  --concurrent-requests 300 \
  --concurrency 10 \
  --rounds 3

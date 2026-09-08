#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.orbstack/bin:${PATH}"

ROOT="${ONTOLOGY_MACMINI_SOURCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
if [[ ! -f "$ROOT/infra/macmini/docker-compose.yml" ]]; then
  echo "Ontology source root is invalid: $ROOT" >&2
  exit 1
fi
PROD_ROOT="${ONTOLOGY_MACMINI_PROD_ROOT:-$HOME/Services/ontology-dashboard-prod}"
COMPOSE_FILE="$ROOT/infra/macmini/docker-compose.yml"
BACKEND_CONTAINER="ontology-dashboard-macmini-backend-1"
GENERATOR_CONTAINER="ontology-dashboard-macmini-generator-runtime-1"
GENERATOR_IMAGE_REPO="ontology-dashboard-macmini-generator-runtime"
LOCK_DIR="$PROD_ROOT/.background-refresh-lock"
GENERATOR_STARTED=0

mkdir -p "$PROD_ROOT"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Ontology background refresh is already running"
  exit 0
fi

cleanup() {
  if [[ "$GENERATOR_STARTED" == "1" ]]; then
    compose stop -t 20 generator-runtime >/dev/null 2>&1 || true
    compose rm -f generator-runtime >/dev/null 2>&1 || true
  fi
  rm -rf "$LOCK_DIR"
}
trap cleanup EXIT

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for Mac mini background refresh" >&2
  exit 1
fi

ENV_FILE="${ONTOLOGY_MACMINI_ENV_FILE:-}"
if [[ -z "$ENV_FILE" ]] && docker inspect "$BACKEND_CONTAINER" >/dev/null 2>&1; then
  ENV_FILE="$(
    docker inspect "$BACKEND_CONTAINER" \
      --format '{{ index .Config.Labels "com.docker.compose.project.environment_file" }}' \
      2>/dev/null || true
  )"
fi
if [[ -z "$ENV_FILE" ]] && [[ -f "$PROD_ROOT/repo/infra/macmini/.env" ]]; then
  ENV_FILE="$PROD_ROOT/repo/infra/macmini/.env"
fi
if [[ -z "$ENV_FILE" || ! -f "$ENV_FILE" ]]; then
  echo "production Mac mini .env could not be resolved" >&2
  exit 1
fi

RUNNING_BACKEND_IMAGE="$(docker inspect "$BACKEND_CONTAINER" --format '{{.Config.Image}}' 2>/dev/null || true)"
if [[ -z "$RUNNING_BACKEND_IMAGE" ]]; then
  echo "Mac mini backend container is not available" >&2
  exit 1
fi
BACKEND_STATUS="$(
  docker inspect "$BACKEND_CONTAINER" \
    --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
    2>/dev/null || true
)"
if [[ "$BACKEND_STATUS" != "healthy" ]]; then
  echo "Mac mini backend is not healthy: ${BACKEND_STATUS:-missing}" >&2
  exit 1
fi

RELEASE_TAG=""
if [[ -f "$PROD_ROOT/backend-deploy-base-sha" ]]; then
  candidate_release_tag="$(tr -d '[:space:]' < "$PROD_ROOT/backend-deploy-base-sha")"
  if [[ "$candidate_release_tag" =~ ^[0-9a-f]{40}$ ]] \
    && docker image inspect "ontology-dashboard-macmini-backend:$candidate_release_tag" >/dev/null 2>&1; then
    RELEASE_TAG="$candidate_release_tag"
  fi
fi
if [[ -z "$RELEASE_TAG" ]]; then
  RELEASE_TAG="${RUNNING_BACKEND_IMAGE##*:}"
fi
BACKEND_IMAGE="ontology-dashboard-macmini-backend:$RELEASE_TAG"
GENERATOR_RUNTIME_IMAGE="$GENERATOR_IMAGE_REPO:$RELEASE_TAG"
if ! docker image inspect "$GENERATOR_RUNTIME_IMAGE" >/dev/null 2>&1; then
  GENERATOR_RUNTIME_IMAGE="$GENERATOR_IMAGE_REPO:latest"
fi

compose() {
  BACKEND_IMAGE="$BACKEND_IMAGE" \
  GENERATOR_RUNTIME_IMAGE="$GENERATOR_RUNTIME_IMAGE" \
    docker compose \
      --env-file "$ENV_FILE" \
      -p ontology-dashboard-macmini \
      -f "$COMPOSE_FILE" \
      "$@"
}

generator_status() {
  docker exec "$GENERATOR_CONTAINER" python -c '
import json
import urllib.request
p = json.load(urllib.request.urlopen("http://127.0.0.1:8000/runtime-pipeline/status", timeout=5))
runs = p.get("recent_runs") or [{}]
r = runs[0] if runs else {}
current = p.get("current_job")
print("|".join([
    str(p.get("queued_count") or 0),
    str(p.get("running_count") or 0),
    "1" if current else "0",
    str(r.get("run_id") or ""),
    str(r.get("status") or ""),
    str(r.get("prediction_delivery_status") or ""),
]))
' 2>/dev/null
}

echo "Starting on-demand Generator runtime: $GENERATOR_RUNTIME_IMAGE"
compose up -d --no-deps --no-build generator-runtime >/dev/null
GENERATOR_STARTED=1

generator_health=""
for _ in {1..30}; do
  generator_health="$(
    docker inspect "$GENERATOR_CONTAINER" \
      --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      2>/dev/null || true
  )"
  [[ "$generator_health" == "healthy" ]] && break
  sleep 2
done
if [[ "$generator_health" != "healthy" ]]; then
  echo "Generator runtime did not become healthy" >&2
  docker logs --tail 80 "$GENERATOR_CONTAINER" >&2 || true
  exit 1
fi

before_status="$(generator_status || true)"
before_run_id="$(printf '%s' "$before_status" | awk -F'|' '{print $4}')"

echo "Running one live predictive-maintenance refresh"
compose run --rm --no-deps -e LIVE_PM_RUN_ONCE=1 live-ingestor

drained=0
for attempt in {1..90}; do
  status_line="$(generator_status || true)"
  if [[ -n "$status_line" ]]; then
    IFS='|' read -r queued running current latest_run latest_status delivery_status <<< "$status_line"
    if [[ "$queued" == "0" && "$running" == "0" && "$current" == "0" ]]; then
      if [[ -n "$latest_run" && "$latest_run" != "$before_run_id" ]]; then
        if [[ "$latest_status" == "failed" || "$delivery_status" == "failed" ]]; then
          echo "Generator refresh failed: run=$latest_run status=$latest_status delivery=$delivery_status" >&2
          exit 1
        fi
        if [[ "$latest_status" == "succeeded" \
          && ( "$delivery_status" == "sent" || "$delivery_status" == "not_required" ) ]]; then
          drained=1
          break
        fi
      elif (( attempt >= 5 )); then
        # No new cadence-aligned sensor snapshot was produced in this cycle.
        drained=1
        break
      fi
    fi
  fi
  sleep 2
done
if [[ "$drained" != "1" ]]; then
  echo "Generator runtime did not drain within the background refresh budget" >&2
  exit 1
fi

# Prediction delivery is asynchronous relative to the live-ingestor cycle.
# Re-materialize only after delivery drains so the graph sees the newest Result
# Artifacts rather than the previous cadence's risk snapshot.
echo "Refreshing current ontology graph after prediction delivery"
compose run --rm --no-deps graph-projector python -m app.project3_refresh_current_projection

echo "Checking knowledge dirty state once"
compose run --rm --no-deps knowledge-indexer

echo "Ontology background refresh completed; Generator runtime will be stopped"

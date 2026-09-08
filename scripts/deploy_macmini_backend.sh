#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.orbstack/bin:${PATH}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET_SHA="${GITHUB_SHA:-$(git rev-parse HEAD)}"
PROD_ROOT="${ONTOLOGY_MACMINI_PROD_ROOT:-$HOME/Services/ontology-dashboard-prod}"
STATE_FILE="$PROD_ROOT/backend-deploy-base-sha"
COMPOSE_FILE="$ROOT/infra/macmini/docker-compose.yml"
IMAGE_REPO="ontology-dashboard-macmini-backend"
TARGET_IMAGE="$IMAGE_REPO:$TARGET_SHA"
CONTAINER_NAME="ontology-dashboard-macmini-backend-1"
LIVE_INGESTOR_CONTAINER_NAME="ontology-dashboard-macmini-live-ingestor-1"
KNOWLEDGE_INDEXER_CONTAINER_NAME="ontology-dashboard-macmini-knowledge-indexer-1"

mkdir -p "$PROD_ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for Mac mini backend deployment" >&2
  exit 1
fi

ENV_FILE="${ONTOLOGY_MACMINI_ENV_FILE:-}"
if [[ -z "$ENV_FILE" ]] && docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  ENV_FILE="$(
    docker inspect "$CONTAINER_NAME" \
      --format '{{ index .Config.Labels "com.docker.compose.project.environment_file" }}' \
      2>/dev/null || true
  )"
fi
if [[ -z "$ENV_FILE" || ! -f "$ENV_FILE" ]]; then
  if [[ -f "$PROD_ROOT/repo/infra/macmini/.env" ]]; then
    ENV_FILE="$PROD_ROOT/repo/infra/macmini/.env"
  else
    echo "production Mac mini .env could not be resolved" >&2
    exit 1
  fi
fi

# Project 3 is now an internal, project-identity-preserving service in the Mac
# mini stack. Normalize stale pre-cutover values before recreating Backend so a
# historical source->cip-dmd mapping cannot route queries outside the current
# versioned graph projection.
python3 - "$ENV_FILE" <<'PY'
import os
import sys

path = sys.argv[1]
updates = {
    "ONTOLOGY_DASHBOARD_PROJECT3_URL": "http://project3:8000",
    "ONTOLOGY_DASHBOARD_PROJECT3_PROJECT_MAP": "{}",
}
with open(path, encoding="utf-8") as handle:
    lines = handle.read().splitlines()
seen = set()
result = []
for line in lines:
    key = line.split("=", 1)[0] if "=" in line else ""
    if key in updates:
        if key not in seen:
            result.append(f"{key}={updates[key]}")
            seen.add(key)
        continue
    result.append(line)
for key, value in updates.items():
    if key not in seen:
        result.append(f"{key}={value}")
mode = os.stat(path).st_mode & 0o777
with open(path, "w", encoding="utf-8") as handle:
    handle.write("\n".join(result) + "\n")
os.chmod(path, mode)
PY

if [[ -f "$STATE_FILE" ]]; then
  PREVIOUS_BASE_SHA="$(tr -d '[:space:]' < "$STATE_FILE")"
else
  PREVIOUS_BASE_SHA=""
fi

if [[ "$PREVIOUS_BASE_SHA" == "$TARGET_SHA" ]]; then
  echo "Mac mini backend already evaluated at $TARGET_SHA"
  exit 0
fi

if [[ -n "$PREVIOUS_BASE_SHA" ]] \
  && git cat-file -e "$PREVIOUS_BASE_SHA^{commit}" 2>/dev/null \
  && git diff --quiet "$PREVIOUS_BASE_SHA" "$TARGET_SHA" -- \
      systems/backend infra/macmini/docker-compose.yml requirements; then
  printf '%s\n' "$TARGET_SHA" > "$STATE_FILE"
  echo "No backend build inputs changed since $PREVIOUS_BASE_SHA; deployment skipped."
  exit 0
fi

CURRENT_IMAGE_ID=""
ROLLBACK_IMAGE=""
if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  CURRENT_IMAGE_ID="$(docker inspect "$CONTAINER_NAME" --format '{{.Image}}')"
  ROLLBACK_IMAGE="$IMAGE_REPO:rollback-${GITHUB_RUN_ID:-local}-$(date +%s)"
  docker tag "$CURRENT_IMAGE_ID" "$ROLLBACK_IMAGE"
fi

echo "Building $TARGET_IMAGE from $TARGET_SHA"
docker build \
  -f systems/backend/Dockerfile \
  --build-arg API_EXTRAS=macmini \
  -t "$TARGET_IMAGE" \
  .

deploy_image() {
  local image="$1"
  BACKEND_IMAGE="$image" \
    docker compose \
      --env-file "$ENV_FILE" \
      -p ontology-dashboard-macmini \
      -f "$COMPOSE_FILE" \
      up -d --no-deps --no-build backend live-ingestor knowledge-indexer
}

wait_for_health() {
  local attempts=30
  local status=""
  local host_port=""
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    status="$(docker inspect "$CONTAINER_NAME" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
    if [[ "$status" == "healthy" ]]; then
      live_running="$(docker inspect "$LIVE_INGESTOR_CONTAINER_NAME" --format '{{.State.Running}}' 2>/dev/null || true)"
      if [[ "$live_running" != "true" ]]; then
        sleep 2
        continue
      fi
      knowledge_status="$(docker inspect "$KNOWLEDGE_INDEXER_CONTAINER_NAME" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
      if [[ "$knowledge_status" != "healthy" ]]; then
        sleep 2
        continue
      fi
      host_port="$(
        docker inspect "$CONTAINER_NAME" \
          --format '{{with (index .NetworkSettings.Ports "8000/tcp")}}{{(index . 0).HostPort}}{{end}}' \
          2>/dev/null || true
      )"
      if [[ -z "$host_port" ]]; then
        echo "backend container is healthy but its localhost port mapping is missing" >&2
        return 1
      fi
      curl --fail --silent --show-error --max-time 10 \
        "http://127.0.0.1:${host_port}/health/ready" >/dev/null
      return 0
    fi
    sleep 4
  done
  echo "backend health check failed with status=${status:-missing}" >&2
  return 1
}

rollback() {
  if [[ -z "$ROLLBACK_IMAGE" ]]; then
    echo "No previous backend image is available for rollback." >&2
    return 1
  fi
  echo "Rolling back backend to $ROLLBACK_IMAGE" >&2
  deploy_image "$ROLLBACK_IMAGE"
  wait_for_health
}

if ! deploy_image "$TARGET_IMAGE" || ! wait_for_health; then
  rollback || true
  exit 1
fi

docker tag "$TARGET_IMAGE" "$IMAGE_REPO:latest"
printf '%s\n' "$TARGET_SHA" > "$STATE_FILE"
echo "Mac mini backend deployment succeeded: $TARGET_SHA"

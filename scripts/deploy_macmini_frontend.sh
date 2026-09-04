#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET_SHA="${GITHUB_SHA:-$(git rev-parse HEAD)}"
PROD_ROOT="${ONTOLOGY_MACMINI_PROD_ROOT:-$HOME/Services/ontology-dashboard-prod}"
STATE_FILE="$PROD_ROOT/frontend-deploy-base-sha"
COMPOSE_FILE="$ROOT/infra/macmini/frontend-compose.yml"
FRONTEND_PORT="${FRONTEND_PORT:-8120}"
IMAGE_REPO="ontology-dashboard-macmini-frontend"
TARGET_IMAGE="$IMAGE_REPO:$TARGET_SHA"
CONTAINER_NAME="ontology-dashboard-macmini-frontend-1"
PRIVATE_NETWORK="ontology-dashboard-macmini_private"

mkdir -p "$PROD_ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for Mac mini deployment" >&2
  exit 1
fi

if ! docker network inspect "$PRIVATE_NETWORK" >/dev/null 2>&1; then
  echo "required production network is missing: $PRIVATE_NETWORK" >&2
  exit 1
fi

if [[ -f "$STATE_FILE" ]]; then
  PREVIOUS_BASE_SHA="$(tr -d '[:space:]' < "$STATE_FILE")"
else
  PREVIOUS_BASE_SHA=""
fi

if [[ "$PREVIOUS_BASE_SHA" == "$TARGET_SHA" ]]; then
  echo "Mac mini frontend already evaluated at $TARGET_SHA"
  exit 0
fi

if [[ -n "$PREVIOUS_BASE_SHA" ]] \
  && git cat-file -e "$PREVIOUS_BASE_SHA^{commit}" 2>/dev/null \
  && git diff --quiet "$PREVIOUS_BASE_SHA" "$TARGET_SHA" -- systems/frontend docs; then
  printf '%s\n' "$TARGET_SHA" > "$STATE_FILE"
  echo "No frontend build inputs changed since $PREVIOUS_BASE_SHA; deployment skipped."
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
  -f systems/frontend/Dockerfile \
  --build-arg VITE_API_BASE_URL= \
  --build-arg VITE_FEATURE_ONTOLOGY_WORKBENCH=true \
  --build-arg VITE_FEATURE_DATASET_CATALOG=false \
  --build-arg VITE_FEATURE_GOVERNANCE_WORKBENCH=false \
  -t "$TARGET_IMAGE" \
  .

deploy_image() {
  local image="$1"
  FRONTEND_IMAGE="$image" FRONTEND_PORT="$FRONTEND_PORT" \
    docker compose \
      -p ontology-dashboard-macmini \
      -f "$COMPOSE_FILE" \
      up -d --no-deps --no-build frontend
}

wait_for_health() {
  local attempts=24
  local status=""
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    status="$(docker inspect "$CONTAINER_NAME" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
    if [[ "$status" == "healthy" ]]; then
      curl --fail --silent --show-error "http://127.0.0.1:${FRONTEND_PORT}/health/live" >/dev/null
      curl --fail --silent --show-error --max-time 15 "https://ontology.oosu.dev/" >/dev/null
      return 0
    fi
    sleep 5
  done
  echo "frontend health check failed with status=${status:-missing}" >&2
  return 1
}

rollback() {
  if [[ -z "$ROLLBACK_IMAGE" ]]; then
    echo "No previous frontend image is available for rollback." >&2
    return 1
  fi
  echo "Rolling back frontend to $ROLLBACK_IMAGE" >&2
  deploy_image "$ROLLBACK_IMAGE"
  wait_for_health
}

if ! deploy_image "$TARGET_IMAGE" || ! wait_for_health; then
  rollback || true
  exit 1
fi

printf '%s\n' "$TARGET_SHA" > "$STATE_FILE"
echo "Mac mini frontend deployment succeeded: $TARGET_SHA"

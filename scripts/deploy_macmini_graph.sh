#!/usr/bin/env bash
set -Eeuo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.orbstack/bin:${PATH}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TARGET_SHA="${GITHUB_SHA:-$(git rev-parse HEAD)}"
PROD_ROOT="${ONTOLOGY_MACMINI_PROD_ROOT:-$HOME/Services/ontology-dashboard-prod}"
STATE_FILE="$PROD_ROOT/graph-deploy-base-sha"
COMPOSE_FILE="$ROOT/infra/macmini/docker-compose.yml"
BACKEND_IMAGE="ontology-dashboard-macmini-backend:$TARGET_SHA"
PROJECT3_REPO="ontology-dashboard-macmini-project3"
PROJECT3_IMAGE="$PROJECT3_REPO:$TARGET_SHA"
PROJECT3_CONTAINER="ontology-dashboard-macmini-project3-1"
PROJECTOR_CONTAINER="ontology-dashboard-macmini-graph-projector-1"

mkdir -p "$PROD_ROOT"

ENV_FILE="${ONTOLOGY_MACMINI_ENV_FILE:-}"
if [[ -z "$ENV_FILE" ]] && docker inspect ontology-dashboard-macmini-backend-1 >/dev/null 2>&1; then
  ENV_FILE="$(
    docker inspect ontology-dashboard-macmini-backend-1 \
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

if ! grep -q '^NEO4J_PASSWORD=.' "$ENV_FILE"; then
  generated="$(openssl rand -hex 24)"
  printf '\nNEO4J_USERNAME=neo4j\nNEO4J_PASSWORD=%s\nONTOLOGY_DASHBOARD_NEO4J_DATABASE=neo4j\n' "$generated" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

if [[ -f "$STATE_FILE" ]] && [[ "$(tr -d '[:space:]' < "$STATE_FILE")" == "$TARGET_SHA" ]]; then
  echo "Mac mini graph runtime already evaluated at $TARGET_SHA"
  exit 0
fi

if ! docker image inspect "$BACKEND_IMAGE" >/dev/null 2>&1; then
  echo "verified backend image is required before graph deployment: $BACKEND_IMAGE" >&2
  exit 1
fi

echo "Building $PROJECT3_IMAGE from $TARGET_SHA"
docker build \
  -f systems/backend/Dockerfile \
  --build-arg API_EXTRAS=graph-runtime \
  -t "$PROJECT3_IMAGE" \
  .

BACKEND_IMAGE="$BACKEND_IMAGE" PROJECT3_IMAGE="$PROJECT3_IMAGE" \
  docker compose --env-file "$ENV_FILE" -p ontology-dashboard-macmini -f "$COMPOSE_FILE" \
  up -d --no-build neo4j project3

status=""
for _ in {1..30}; do
  status="$(docker inspect "$PROJECT3_CONTAINER" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
  if [[ "$status" == "healthy" ]]; then
    break
  fi
  sleep 4
done
if [[ "$status" != "healthy" ]]; then
  echo "Project 3 runtime did not become healthy" >&2
  exit 1
fi

BACKEND_IMAGE="$BACKEND_IMAGE" PROJECT3_IMAGE="$PROJECT3_IMAGE" \
  docker compose --env-file "$ENV_FILE" -p ontology-dashboard-macmini -f "$COMPOSE_FILE" \
  run --rm --no-deps graph-projector python -m app.project3_refresh_current_projection

BACKEND_IMAGE="$BACKEND_IMAGE" PROJECT3_IMAGE="$PROJECT3_IMAGE" \
  docker compose --env-file "$ENV_FILE" -p ontology-dashboard-macmini -f "$COMPOSE_FILE" \
  up -d --no-build graph-projector

for _ in {1..30}; do
  if [[ "$(docker inspect "$PROJECTOR_CONTAINER" --format '{{.State.Running}}' 2>/dev/null || true)" == "true" ]]; then
    readiness="$(
      docker exec "$PROJECT3_CONTAINER" python -c \
        "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/projects/manufacturing-demo-project/readiness', timeout=5).read().decode())" \
        2>/dev/null || true
    )"
    if echo "$readiness" | grep -q '"can_query":true'; then
      docker tag "$PROJECT3_IMAGE" "$PROJECT3_REPO:latest"
      printf '%s\n' "$TARGET_SHA" > "$STATE_FILE"
      echo "Mac mini graph deployment succeeded: $TARGET_SHA"
      exit 0
    fi
  fi
  sleep 4
done

echo "Graph projector did not produce a queryable projection" >&2
docker logs --tail 120 "$PROJECTOR_CONTAINER" >&2 || true
exit 1

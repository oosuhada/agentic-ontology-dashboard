#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_ROOT="${HOME_IDLE_INSTALL_ROOT:-$HOME/Services/home-idle-runtime}"
LOG_ROOT="$HOME/Library/Logs/dev.oosu.home-idle"
PLIST_ROOT="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
NGINX_SERVERS="/opt/homebrew/etc/nginx/servers"
NGINX_BIN="/opt/homebrew/opt/nginx/bin/nginx"
CLOUDFLARE_CONFIG="$HOME/.cloudflared/config.yml"
DOCKER_BIN="/Applications/OrbStack.app/Contents/MacOS/xbin/docker"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="$INSTALL_ROOT/backups/$TIMESTAMP"
FACTORY_LABEL="dev.oosu.factorygraph-idle-supervisor"
AIGRAM_LABEL="dev.oosu.aigram-idle-supervisor"
COMMITTED=0

mkdir -p "$INSTALL_ROOT" "$INSTALL_ROOT/state" "$LOG_ROOT" "$PLIST_ROOT" "$BACKUP_ROOT"
install -m 0755 "$ROOT/infra/macmini/home_server_idle_supervisor.py" "$INSTALL_ROOT/home_idle_supervisor.py"

FACTORY_COMPOSE="$HOME/Services/text2cypher-factory-rca/infra/docker-compose.product.yml"
FACTORY_ENV="$HOME/Services/text2cypher-factory-rca/.env.public"
AIGRAM_COMPOSE="$HOME/Services/instagram-orbstack/compose.prod.yml"

for required in "$FACTORY_COMPOSE" "$FACTORY_ENV" "$AIGRAM_COMPOSE" "$CLOUDFLARE_CONFIG"; do
  [[ -f "$required" ]] || { echo "required file missing: $required" >&2; exit 1; }
done
[[ -x "$DOCKER_BIN" ]] || { echo "OrbStack docker binary missing" >&2; exit 1; }
[[ -x "$NGINX_BIN" ]] || { echo "Homebrew nginx binary missing" >&2; exit 1; }

install_agent() {
  local label="$1" port="$2" name="$3" project="$4" compose="$5" working_dir="$6"
  local env_file="$7" start_services="$8" stop_services="$9" ready_urls="${10}" ready_tcp="${11}" idle="${12}"
  local plist="$PLIST_ROOT/$label.plist"
  local env_xml=""
  if [[ -n "$env_file" ]]; then
    env_xml="<key>HOME_IDLE_ENV_FILE</key><string>$env_file</string>"
  fi
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array><string>/opt/homebrew/bin/python3</string><string>$INSTALL_ROOT/home_idle_supervisor.py</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>ProcessType</key><string>Background</string>
  <key>EnvironmentVariables</key><dict>
    <key>HOME_IDLE_NAME</key><string>$name</string>
    <key>HOME_IDLE_PROJECT</key><string>$project</string>
    <key>HOME_IDLE_COMPOSE_FILE</key><string>$compose</string>
    <key>HOME_IDLE_WORKING_DIR</key><string>$working_dir</string>
    $env_xml
    <key>HOME_IDLE_START_SERVICES</key><string>$start_services</string>
    <key>HOME_IDLE_STOP_SERVICES</key><string>$stop_services</string>
    <key>HOME_IDLE_READY_URLS</key><string>$ready_urls</string>
    <key>HOME_IDLE_READY_TCP</key><string>$ready_tcp</string>
    <key>HOME_IDLE_SECONDS</key><string>$idle</string>
    <key>HOME_IDLE_MIN_UP_SECONDS</key><string>300</string>
    <key>HOME_IDLE_START_TIMEOUT_SECONDS</key><string>180</string>
    <key>HOME_IDLE_HOST</key><string>127.0.0.1</string>
    <key>HOME_IDLE_PORT</key><string>$port</string>
    <key>PYTHONUNBUFFERED</key><string>1</string>
  </dict>
  <key>StandardOutPath</key><string>$LOG_ROOT/$name.stdout.log</string>
  <key>StandardErrorPath</key><string>$LOG_ROOT/$name.stderr.log</string>
</dict></plist>
EOF
  plutil -lint "$plist"
  launchctl bootout "$DOMAIN" "$plist" >/dev/null 2>&1 || true
  launchctl bootstrap "$DOMAIN" "$plist"
}

PORTFOLIO_CONF="$NGINX_SERVERS/portfolio-demos.conf"
AIGRAM_CONF="$NGINX_SERVERS/instagram-orbstack.conf"
FACTORY_IDLE_CONF="$NGINX_SERVERS/text2cypher-idle.conf"
cp "$PORTFOLIO_CONF" "$BACKUP_ROOT/portfolio-demos.conf"
cp "$AIGRAM_CONF" "$BACKUP_ROOT/instagram-orbstack.conf"
cp "$CLOUDFLARE_CONFIG" "$BACKUP_ROOT/cloudflared-config.yml"
if [[ -f "$FACTORY_IDLE_CONF" ]]; then
  cp "$FACTORY_IDLE_CONF" "$BACKUP_ROOT/text2cypher-idle.conf"
  touch "$BACKUP_ROOT/had-text2cypher-idle"
fi
for label in "$FACTORY_LABEL" "$AIGRAM_LABEL"; do
  plist="$PLIST_ROOT/$label.plist"
  if [[ -f "$plist" ]]; then
    cp "$plist" "$BACKUP_ROOT/$label.plist"
    touch "$BACKUP_ROOT/had-$label-plist"
  fi
done

rollback() {
  local rc=$?
  if [[ "$COMMITTED" == "1" ]]; then
    return "$rc"
  fi
  echo "Idle demo install failed; restoring previous nginx/cloudflared configuration" >&2
  cp "$BACKUP_ROOT/portfolio-demos.conf" "$PORTFOLIO_CONF" || true
  cp "$BACKUP_ROOT/instagram-orbstack.conf" "$AIGRAM_CONF" || true
  cp "$BACKUP_ROOT/cloudflared-config.yml" "$CLOUDFLARE_CONFIG" || true
  if [[ -f "$BACKUP_ROOT/had-text2cypher-idle" ]]; then
    cp "$BACKUP_ROOT/text2cypher-idle.conf" "$FACTORY_IDLE_CONF" || true
  else
    rm -f "$FACTORY_IDLE_CONF"
  fi
  "$NGINX_BIN" -t >/dev/null 2>&1 && "$NGINX_BIN" -s reload >/dev/null 2>&1 || true
  launchctl kickstart -k "$DOMAIN/com.cloudflare.cloudflared" >/dev/null 2>&1 || true
  for label in "$FACTORY_LABEL" "$AIGRAM_LABEL"; do
    plist="$PLIST_ROOT/$label.plist"
    launchctl bootout "$DOMAIN" "$plist" >/dev/null 2>&1 || true
    if [[ -f "$BACKUP_ROOT/had-$label-plist" ]]; then
      cp "$BACKUP_ROOT/$label.plist" "$plist" || true
      launchctl bootstrap "$DOMAIN" "$plist" >/dev/null 2>&1 || true
    else
      rm -f "$plist"
    fi
  done
  return "$rc"
}
trap rollback ERR

install_agent \
  "$FACTORY_LABEL" 8232 factorygraph factorygraph-rca \
  "$FACTORY_COMPOSE" "$HOME/Services/text2cypher-factory-rca/infra" "$FACTORY_ENV" \
  "neo4j,api,streamlit,web" "web,streamlit,api,neo4j" \
  "http://127.0.0.1:8300/,http://127.0.0.1:8800/api/v1/health/live,http://127.0.0.1:8851/_stcore/health" "" 2700

install_agent \
  "$AIGRAM_LABEL" 8233 aigram instagram-orbstack \
  "$AIGRAM_COMPOSE" "$HOME/Services/instagram-orbstack" "" \
  "postgres,meilisearch,backend,frontend" "frontend,backend,meilisearch,postgres" \
  "" "127.0.0.1:7700,127.0.0.1:8081,127.0.0.1:3000" 3600

if grep -q "server_name text2cypher.oosu.dev;" "$PORTFOLIO_CONF"; then
python3 - "$PORTFOLIO_CONF" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
needle = "server_name text2cypher.oosu.dev;"
pos = text.find(needle)
if pos < 0:
    raise SystemExit("text2cypher server block not found")
start = text.rfind("server {", 0, pos)
if start < 0:
    raise SystemExit("text2cypher server start not found")
depth = 0
end = None
for index in range(start, len(text)):
    char = text[index]
    if char == "{":
        depth += 1
    elif char == "}":
        depth -= 1
        if depth == 0:
            end = index + 1
            break
if end is None:
    raise SystemExit("text2cypher server end not found")
path.write_text(text[:start].rstrip() + "\n\n" + text[end:].lstrip())
PY
elif [[ ! -f "$FACTORY_IDLE_CONF" ]]; then
  echo "text2cypher nginx route is neither legacy nor idle-managed" >&2
  false
fi

cp "$ROOT/infra/macmini/nginx/factorygraph-idle.conf" "$FACTORY_IDLE_CONF"
sed "s#__HOME__#$HOME#g" "$ROOT/infra/macmini/nginx/aigram-idle.conf" > "$AIGRAM_CONF"

python3 - "$CLOUDFLARE_CONFIG" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text()
old = "  - hostname: text2cypher-console.oosu.dev\n    service: http://127.0.0.1:8851"
new = "  - hostname: text2cypher-console.oosu.dev\n    service: http://localhost:8080"
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("text2cypher console Cloudflare route not found")
path.write_text(text)
PY

"$NGINX_BIN" -t
/opt/homebrew/bin/cloudflared tunnel ingress validate
"$NGINX_BIN" -s reload
launchctl kickstart -k "$DOMAIN/com.cloudflare.cloudflared"

COMMITTED=1
trap - ERR

echo "Installed FactoryGraph/Aigram idle supervisors. Backups: $BACKUP_ROOT"

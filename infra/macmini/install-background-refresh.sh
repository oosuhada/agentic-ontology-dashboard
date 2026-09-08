#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_ROOT="${ONTOLOGY_MACMINI_WATCH_ROOT:-$HOME/Services/ontology-dashboard-release}"
RUNNER="$INSTALL_ROOT/run-background-refresh.sh"
PLIST="$HOME/Library/LaunchAgents/dev.oosu.ontology-dashboard-background-refresh.plist"
LOG_ROOT="$HOME/Library/Logs/dev.oosu.ontology-dashboard-background-refresh"
DOMAIN="gui/$(id -u)"
INTERVAL="${ONTOLOGY_MACMINI_BACKGROUND_REFRESH_SECONDS:-600}"
PROD_ROOT="${ONTOLOGY_MACMINI_PROD_ROOT:-$HOME/Services/ontology-dashboard-prod}"
SOURCE_ROOT="$ROOT"

if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]] || (( INTERVAL < 300 )); then
  echo "ONTOLOGY_MACMINI_BACKGROUND_REFRESH_SECONDS must be an integer >= 300" >&2
  exit 1
fi

mkdir -p "$INSTALL_ROOT" "$HOME/Library/LaunchAgents" "$LOG_ROOT"
install -m 0755 "$ROOT/scripts/run_macmini_background_refresh.sh" "$RUNNER"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>dev.oosu.ontology-dashboard-background-refresh</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$RUNNER</string>
  </array>
  <key>RunAtLoad</key>
  <false/>
  <key>StartInterval</key>
  <integer>$INTERVAL</integer>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ONTOLOGY_MACMINI_PROD_ROOT</key>
    <string>$PROD_ROOT</string>
    <key>ONTOLOGY_MACMINI_SOURCE_ROOT</key>
    <string>$SOURCE_ROOT</string>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_ROOT/stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_ROOT/stderr.log</string>
</dict>
</plist>
EOF

plutil -lint "$PLIST"
launchctl bootout "$DOMAIN" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "$DOMAIN" "$PLIST"

if [[ "${ONTOLOGY_MACMINI_BACKGROUND_REFRESH_RUN_NOW:-0}" == "1" ]]; then
  launchctl kickstart -k "$DOMAIN/dev.oosu.ontology-dashboard-background-refresh"
fi

echo "Installed Mac mini background refresh every ${INTERVAL}s: $PLIST"

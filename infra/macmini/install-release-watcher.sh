#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_ROOT="${ONTOLOGY_MACMINI_WATCH_ROOT:-$HOME/Services/ontology-dashboard-release}"
WATCHER="$INSTALL_ROOT/watch-main.sh"
PLIST="$HOME/Library/LaunchAgents/dev.oosu.ontology-dashboard-release-watcher.plist"
LOG_ROOT="$HOME/Library/Logs/dev.oosu.ontology-dashboard-release-watcher"
DOMAIN="gui/$(id -u)"

mkdir -p "$INSTALL_ROOT" "$HOME/Library/LaunchAgents" "$LOG_ROOT"
install -m 0755 "$ROOT/scripts/macmini_release_watcher.sh" "$WATCHER"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>dev.oosu.ontology-dashboard-release-watcher</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$WATCHER</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>60</integer>
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
launchctl kickstart -k "$DOMAIN/dev.oosu.ontology-dashboard-release-watcher"

echo "Installed Mac mini release watcher: $PLIST"

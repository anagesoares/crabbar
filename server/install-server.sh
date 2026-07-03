#!/usr/bin/env bash
# Instala o clawd-serve como launchd agent (roda no login) e testa.
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$(command -v python3)"
PLIST="$HOME/Library/LaunchAgents/com.ana.clawd-serve.plist"

sed -e "s#__PY__#$PY#" \
    -e "s#__SCRIPT__#$DIR/clawd_serve.py#" \
    -e "s#__LOG__#$HOME/Library/Logs/clawd-serve.log#" \
    "$DIR/com.ana.clawd-serve.plist" > "$PLIST"

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "✓ clawd-serve rodando e no login. Testando…"
sleep 2
curl -s "http://localhost:8787/tokens"; echo

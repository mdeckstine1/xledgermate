#!/usr/bin/env bash
# Pull Ashigaru on VPS, verify version files, restart ws-engine + HUD (picks up new VERSION / HTML).
set -euo pipefail
cd /root/xledgermate

echo "=== git pull Ashigaru ==="
git fetch origin Ashigaru
git checkout Ashigaru
git pull origin Ashigaru
echo "HEAD: $(git rev-parse --short HEAD)"

PROJECT_VER="$(tr -d '\r\n' < VERSION)"
WS_VER="$(tr -d '\r\n' < experimental/ws_feed/WS_AS_VERSION)"
echo "VERSION=${PROJECT_VER}  WS_AS_VERSION=${WS_VER}"
if [ "${PROJECT_VER}" != "${WS_VER}" ]; then
  echo "WARN: VERSION and WS_AS_VERSION differ — align before next release tag."
fi

echo "=== restart ws-engine + HUD ==="
systemctl restart xledgermate
systemctl restart xledgermate-ws-hud
sleep 4
systemctl is-active xledgermate
systemctl is-active xledgermate-ws-hud

echo "=== HUD /state version ==="
python3 - <<'PY'
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8765/state", timeout=10) as resp:
    state = json.load(resp)
print("ws_as_version:", state.get("ws_as_version"))
PY

echo "=== engine log (version line) ==="
grep -E "WsPureTradingEngine v|WS pure engine path v" logs/xledgermate.log | tail -3 || true

echo "=== deploy complete ==="

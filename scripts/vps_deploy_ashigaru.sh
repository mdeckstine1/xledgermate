#!/usr/bin/env bash
# Pull Ashigaru-Kaizen on VPS, verify version files, restart ws-engine + HUD.
set -euo pipefail
cd /root/xledgermate

BRANCH="Ashigaru-Kaizen"

echo "=== git pull ${BRANCH} ==="
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull origin "${BRANCH}"
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

echo "=== runtime persist check (no g4 TypeError) ==="
sleep 6
if grep -q "g4_size_mult" logs/xledgermate.log 2>/dev/null; then
  echo "WARN: recent g4_size_mult errors in log — check runtime_state.json mtime"
else
  echo "OK: no g4_size_mult errors since restart"
fi
if [ -f logs/runtime_state.json ]; then
  echo "runtime_state mtime: $(stat -c %y logs/runtime_state.json 2>/dev/null || stat -f %Sm logs/runtime_state.json)"
  PY=.venv/bin/python
  $PY -c "import json; d=json.load(open('logs/runtime_state.json')); print('updated_utc:', d.get('updated_utc'), 'cycle:', d.get('cycle_count'), 'ws:', d.get('ws_as_version'))"
fi

echo "=== hourly Telegram report timer ==="
if [ -f scripts/ensure_hourly_telegram_timer.sh ]; then
  bash scripts/ensure_hourly_telegram_timer.sh || echo "WARN: hourly timer setup failed"
fi

echo "=== deploy complete ==="

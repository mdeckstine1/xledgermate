#!/usr/bin/env bash
# Deploy Trading Bot Alpha branch on VPS — engine + HUD.
set -euo pipefail
cd /root/xledgermate

BRANCH="${ALPHA_BRANCH:-samurai}"

echo "=== git pull ${BRANCH} ==="
git fetch origin "refs/heads/${BRANCH}:refs/heads/${BRANCH}" 2>/dev/null || git fetch origin "${BRANCH}"
git checkout "refs/heads/${BRANCH}" 2>/dev/null || git checkout "${BRANCH}"
git pull origin "${BRANCH}" 2>/dev/null || true
echo "HEAD: $(git rev-parse --short HEAD)"

if [ -f alpha/version.py ]; then
  echo "ALPHA_VERSION: $(tr -d '\r\n' < alpha/version.py | grep ALPHA_VERSION | cut -d= -f2 | tr -d ' \"')"
fi

echo "=== pip install (if needed) ==="
.venv/bin/pip install -q -r requirements.txt

_restart_unit() {
  local unit="$1"
  if systemctl cat "${unit}" >/dev/null 2>&1; then
    systemctl restart "${unit}"
    systemctl is-active "${unit}"
    return 0
  fi
  return 1
}

echo "=== restart Alpha services ==="
if _restart_unit xledgermate-alpha.service; then
  sleep 3
else
  echo "No xledgermate-alpha.service — install from scripts/systemd/xledgermate-alpha.service"
fi

if _restart_unit xledgermate-alpha-hud.service; then
  :
elif _restart_unit xledgermate-alpha-gui.service; then
  :
else
  echo "No alpha HUD/GUI systemd unit — install scripts/systemd/xledgermate-alpha-hud.service"
fi

echo "=== hourly Telegram timer (Alpha uses same script) ==="
if [ -f scripts/ensure_hourly_telegram_timer.sh ]; then
  bash scripts/ensure_hourly_telegram_timer.sh || echo "WARN: hourly timer setup failed"
fi

echo "=== dry-run status cycle ==="
.venv/bin/python -m alpha status --no-telegram || true

echo "=== tail alpha activity ==="
tail -5 logs/alpha_activity.jsonl 2>/dev/null || echo "(no activity log yet)"

echo "Done. Verify dry_run in config/config.yaml before live trading."

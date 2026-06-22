#!/usr/bin/env bash
# Deploy Trading Bot Alpha branch on VPS — engine + optional GUI.
set -euo pipefail
cd /root/xledgermate

BRANCH="${ALPHA_BRANCH:-alpha}"

echo "=== git pull ${BRANCH} ==="
git fetch origin "${BRANCH}"
git checkout "${BRANCH}"
git pull origin "${BRANCH}"
echo "HEAD: $(git rev-parse --short HEAD)"

if [ -f alpha/version.py ]; then
  echo "ALPHA_VERSION: $(tr -d '\r\n' < alpha/version.py | grep ALPHA_VERSION | cut -d= -f2 | tr -d ' \"')"
fi

echo "=== pip install (if needed) ==="
.venv/bin/pip install -q -r requirements.txt

echo "=== restart Alpha services (if units installed) ==="
if systemctl list-unit-files | grep -q xledgermate-alpha.service; then
  systemctl restart xledgermate-alpha
  sleep 3
  systemctl is-active xledgermate-alpha
else
  echo "No xledgermate-alpha.service — install from scripts/systemd/xledgermate-alpha.service"
fi

if systemctl list-unit-files | grep -q xledgermate-alpha-hud.service; then
  systemctl restart xledgermate-alpha-hud
  systemctl is-active xledgermate-alpha-hud
elif systemctl list-unit-files | grep -q xledgermate-alpha-gui.service; then
  systemctl restart xledgermate-alpha-gui
  systemctl is-active xledgermate-alpha-gui
else
  echo "No alpha HUD/GUI systemd unit — install scripts/systemd/xledgermate-alpha-hud.service"
fi

echo "=== dry-run status cycle ==="
.venv/bin/python -m alpha status --no-telegram || true

echo "=== tail alpha activity ==="
tail -5 logs/alpha_activity.jsonl 2>/dev/null || echo "(no activity log yet)"

echo "Done. Verify dry_run in config/config.yaml before live trading."

#!/usr/bin/env bash
# Lean production MM on VPS: ws-engine + ws-hud only (no Streamlit sidecars).
set -euo pipefail

echo "=== Stopping legacy Streamlit services (not used for ws-engine MM) ==="
for unit in xledgermate-gui xledgermate-dashboard; do
  if systemctl is-active --quiet "$unit" 2>/dev/null; then
    systemctl stop "$unit"
    echo "stopped $unit"
  fi
  if systemctl is-enabled --quiet "$unit" 2>/dev/null; then
    systemctl disable "$unit"
    echo "disabled $unit"
  fi
done

echo "=== Ensuring ws-engine + production HUD ==="
systemctl enable xledgermate xledgermate-ws-hud
systemctl restart xledgermate xledgermate-ws-hud
sleep 3
systemctl is-active xledgermate
systemctl is-active xledgermate-ws-hud

echo "=== Hourly Telegram report timer ==="
ROOT="${XLEDGERMATE_ROOT:-/root/xledgermate}"
if [ -f "${ROOT}/scripts/ensure_hourly_telegram_timer.sh" ]; then
  bash "${ROOT}/scripts/ensure_hourly_telegram_timer.sh" || echo "WARN: hourly timer setup failed (check telegram config)"
else
  echo "WARN: ensure_hourly_telegram_timer.sh not found — pull latest Ashigaru-Kaizen"
fi

echo ""
echo "Lean profile active."
echo "Active Python MM processes should be ws-engine + ws-hud only:"
pgrep -af 'main.py --mode (ws-engine|ws-hud)' || true

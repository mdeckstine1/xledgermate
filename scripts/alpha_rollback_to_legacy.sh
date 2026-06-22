#!/usr/bin/env bash
# Roll back VPS from Alpha to legacy ws-engine MM (Ashigaru-Shoshin path).
set -euo pipefail
cd /root/xledgermate

echo "=== Stop Alpha services ==="
systemctl stop xledgermate-alpha 2>/dev/null || true
systemctl stop xledgermate-alpha-gui 2>/dev/null || true

echo "=== Ensure dry_run on Alpha config (safety) ==="
if [ -f config/config.yaml ]; then
  sed -i 's/^dry_run: false/dry_run: true/' config/config.yaml || true
fi

LEGACY_BRANCH="${LEGACY_BRANCH:-Ashigaru-Shoshin}"
echo "=== Checkout legacy branch ${LEGACY_BRANCH} ==="
git fetch origin "${LEGACY_BRANCH}"
git checkout "${LEGACY_BRANCH}"
git pull origin "${LEGACY_BRANCH}"

echo "=== Restart legacy ws-engine + HUD ==="
if [ -f scripts/vps_deploy_ashigaru.sh ]; then
  bash scripts/vps_deploy_ashigaru.sh
else
  systemctl restart xledgermate
  systemctl restart xledgermate-ws-hud
fi

echo "Rollback complete. Alpha units stopped; legacy MM restored."
echo "To retry Alpha later: git checkout alpha && bash scripts/vps_deploy_alpha.sh"

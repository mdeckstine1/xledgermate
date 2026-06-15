#!/usr/bin/env bash
# Kill legacy poll engine; ensure only ws-engine runs via systemd.
set -euo pipefail
cd /root/xledgermate

echo "=== Stop legacy poll engine ==="
pkill -f 'main.py --mode engine' 2>/dev/null || true
sleep 1
if pgrep -af 'main.py --mode engine' | grep -v ws-engine; then
  echo "WARNING: legacy engine process still present"
  pgrep -af 'main.py --mode engine' || true
else
  echo "No legacy --mode engine processes"
fi

echo "=== Ensure systemd uses ws-engine ==="
grep ExecStart /etc/systemd/system/xledgermate.service
if ! grep -q 'ws-engine' /etc/systemd/system/xledgermate.service; then
  perl -pi -e 's/--mode engine/--mode ws-engine/' /etc/systemd/system/xledgermate.service
  systemctl daemon-reload
fi

echo "=== Start WS pure A-S engine ==="
systemctl enable xledgermate
systemctl restart xledgermate
sleep 8
systemctl is-active xledgermate
pgrep -af 'main.py' || true

echo "=== Runtime ==="
grep -E 'as_mode|price_source|active_profile|dry_run|last_execution|cycle_count' logs/runtime_state.json | head -10

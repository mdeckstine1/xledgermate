#!/usr/bin/env bash
set -euo pipefail
cd /root/xledgermate

echo "=== dry_run -> true (first WS smoke) ==="
cp -a config/config.yaml config/config.yaml.bak-pre-ws-engine
perl -pi -e 's/^dry_run: false/dry_run: true/' config/config.yaml
grep '^dry_run:' config/config.yaml

echo "=== clear kill switch ==="
/root/xledgermate/.venv/bin/python main.py --mode clear-kill
python3 -c "import json; d=json.load(open('logs/kill_switch.json')); print('kill active:', d.get('active'), '|', d.get('reason','')[:80])"

echo "=== systemd -> ws-engine ==="
perl -pi -e 's/--mode engine/--mode ws-engine/' /etc/systemd/system/xledgermate.service
grep ExecStart /etc/systemd/system/xledgermate.service

echo "=== start service ==="
systemctl stop xledgermate 2>/dev/null || true
systemctl daemon-reload
systemctl enable xledgermate
systemctl start xledgermate
sleep 10
systemctl is-active xledgermate
systemctl status xledgermate --no-pager -l | head -20

echo "=== runtime_state ==="
python3 -c "import json; d=json.load(open('logs/runtime_state.json')); print({k:d.get(k) for k in ['as_mode','price_source','dry_run','kill_switch_active','ws_book_age_ms','last_cycle_utc'] if k in d or True})"

echo "=== recent log ==="
tail -15 logs/xledgermate.log

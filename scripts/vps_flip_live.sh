#!/usr/bin/env bash
set -euo pipefail
cd /root/xledgermate
cp -a config/config.yaml "config/config.yaml.bak-pre-live-$(date -u +%Y%m%dT%H%M%SZ)"
python3 <<'PY'
from pathlib import Path
p = Path("config/config.yaml")
t = p.read_text(encoding="utf-8")
if "dry_run: true" not in t:
    raise SystemExit("dry_run: true not found in config")
p.write_text(t.replace("dry_run: true", "dry_run: false", 1), encoding="utf-8")
print([ln for ln in p.read_text().splitlines() if ln.startswith("dry_run:")][0])
PY
systemctl restart xledgermate
sleep 15
systemctl is-active xledgermate
grep -E 'dry_run|offers_placed|last_execution|open_offers_count|fills_session|kill_switch_active' logs/runtime_state.json | head -10
tail -8 logs/xledgermate.log

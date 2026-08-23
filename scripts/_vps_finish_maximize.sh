#!/usr/bin/env bash
set -euo pipefail
cd /root/xledgermate
export PYTHONPATH=/root/xledgermate
ls -la alpha/hud/maximize_preset.py
.venv/bin/python - <<'PY'
from config.settings import BotConfig
assert hasattr(BotConfig(), "alpha_brackets_enabled")
print("settings_ok")
PY
.venv/bin/python scripts/_vps_apply_maximize.py
.venv/bin/python - <<'PY'
import json
d = json.load(open("logs/alpha_overrides.json", encoding="utf-8"))
keys = [
    "inventory_target_xrp_ratio",
    "alpha_brackets_enabled",
    "alpha_reload_min_rlusd_deploy_xrp_equiv",
    "alpha_strength_deviation",
    "alpha_risk_per_trade_pct",
    "alpha_accumulation_harvest_move_24h_watch_pct",
    "updated_utc",
]
for k in keys:
    print(f"{k}={d.get(k)}")
print("FINISH_OK")
PY
systemctl is-active xledgermate-alpha xledgermate-alpha-hud
sleep 35
tail -8 logs/alpha_activity.jsonl

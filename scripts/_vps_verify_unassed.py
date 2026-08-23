#!/usr/bin/env python3
"""Verify Unassed deploy on VPS."""
from __future__ import annotations

import json
from pathlib import Path

keys = [
    "alpha_strength_deviation",
    "alpha_bull_run_max_deviation",
    "alpha_reload_min_rlusd_deploy_xrp_equiv",
    "alpha_reload_block_accumulation_until_funded",
    "initial_stop_loss_pct",
    "bracket_trailing_enabled",
    "take_profit_rr",
    "take_profit_pct",
    "alpha_ta_min_sell_score",
    "inventory_target_xrp_ratio",
    "alpha_sell_limit_offset_pct",
    "updated_utc",
]

ov = Path("logs/alpha_overrides.json")
d = json.loads(ov.read_text(encoding="utf-8")) if ov.is_file() else {}
print("=== overrides ===")
for k in keys:
    print(f"{k}={d.get(k)}")

assert d.get("alpha_strength_deviation") == 0.06, d.get("alpha_strength_deviation")
assert d.get("alpha_reload_min_rlusd_deploy_xrp_equiv") == 18.0
assert d.get("alpha_reload_block_accumulation_until_funded") is False
assert d.get("bracket_trailing_enabled") is False
assert d.get("initial_stop_loss_pct") == 0.09
print("overrides_ok")

idx = Path("alpha/hud/index.html").read_text(encoding="utf-8", errors="replace")
assert "btnUnassedPreset" in idx
assert "/operator/unassed" in idx
print("index_ok")

assert Path("alpha/hud/unassed_preset.py").is_file()
print("preset_file_ok")

from alpha.operator.runtime import OPERATOR_TUNABLE_KEYS

assert "alpha_reload_min_rlusd_deploy_xrp_equiv" in OPERATOR_TUNABLE_KEYS
print("tunable_ok")
print("ALL_GOOD")

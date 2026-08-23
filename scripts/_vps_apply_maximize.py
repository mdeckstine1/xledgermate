#!/usr/bin/env python3
"""Apply Maximize preset on VPS and print effective knobs."""
from __future__ import annotations

import json
from pathlib import Path

from alpha.hud.maximize_preset import apply_maximize_preset, maximize_preset_payload
from alpha.hud.skynet_agent import merge_agent_patch
from alpha.operator.runtime import OperatorRuntimeStore, apply_overrides
from config.settings import BotConfig

base = BotConfig.load()
store = OperatorRuntimeStore()
merged, _agent, errors = apply_maximize_preset(
    patch_overrides=lambda ov, base=base: store.patch_overrides(ov, base=base),
    merge_agent_patch=merge_agent_patch,
    base_config=base,
)
print("errors", errors)
assert not errors, errors
eff = apply_overrides(base, merged)
keys = [
    "inventory_target_xrp_ratio",
    "alpha_strength_deviation",
    "alpha_risk_per_trade_pct",
    "alpha_reload_min_rlusd_deploy_xrp_equiv",
    "alpha_reload_block_accumulation_until_funded",
    "alpha_brackets_enabled",
    "bracket_trailing_enabled",
    "alpha_accumulation_harvest_move_24h_watch_pct",
    "alpha_accumulation_dip_move_24h_arm_pct",
]
for k in keys:
    print(f"{k}={getattr(eff, k, None)}")
print("desc", maximize_preset_payload()["description"][:160])
ov = json.loads(Path("logs/alpha_overrides.json").read_text(encoding="utf-8"))
print("updated_utc", ov.get("updated_utc"))
print("MAXIMIZE_APPLIED_OK")

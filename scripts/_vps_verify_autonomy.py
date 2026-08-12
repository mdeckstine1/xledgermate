#!/usr/bin/env python3
"""Verify autonomy knobs + live decision after deploy."""
from __future__ import annotations

import json
from pathlib import Path

ov = json.loads(Path("logs/alpha_overrides.json").read_text(encoding="utf-8"))
keys = [
    "alpha_stale_pending_sell_enabled",
    "alpha_stale_pending_sell_max_drift_pct",
    "alpha_accumulation_harvest_move_24h_watch_pct",
    "alpha_accumulation_harvest_pullback_arm_pct",
    "alpha_accumulation_dip_move_24h_arm_pct",
]
print("overrides:")
for k in keys:
    print(f"  {k}: {ov.get(k)}")

state = json.loads(Path("logs/alpha_runtime_state.json").read_text(encoding="utf-8"))
print("decision:", state.get("decision"))
offers = state.get("open_offers") or []
print("open_offers:", len(offers))
mid = float(state.get("mid") or 0)
for o in offers:
    side = o.get("side")
    price = float(o.get("price") or 0)
    dist = ((price / mid) - 1.0) * 100.0 if mid and price else None
    print(f"  side={side} price={price} dist={dist}")
bag = state.get("bag_growth") or {}
print("total", bag.get("portfolio_xrp_equiv"), "bot_added", bag.get("since_baseline_bot_xrp"))

#!/usr/bin/env python3
"""Print live bag scoreboard fields from alpha_runtime_state.json."""
from __future__ import annotations

import json
from pathlib import Path

path = Path("logs/alpha_runtime_state.json")
state = json.loads(path.read_text(encoding="utf-8"))
b = state.get("bag_growth") or {}
print("total", b.get("portfolio_xrp_equiv"))
print("rlusd_eq", b.get("portfolio_rlusd_equiv"))
print("day", b.get("day_delta_xrp"), b.get("day_delta_pct"))
print("week", b.get("week_delta_xrp"), b.get("week_delta_pct"))
print(
    "ath",
    b.get("high_water_portfolio_xrp"),
    "off",
    b.get("off_high_xrp"),
    "at",
    b.get("at_high_water"),
)
print("bot", b.get("since_baseline_bot_xrp"))
print("xrp", b.get("xrp"), "rlusd", b.get("rlusd"))
print("explain_ok", "TOTAL BAG" in str(b.get("explain") or ""))

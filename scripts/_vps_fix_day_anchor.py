#!/usr/bin/env python3
"""Align Monday day_start to week_start so today Δ matches week open."""
from __future__ import annotations

import json
from pathlib import Path

p = Path("logs/alpha_bag_week.json")
d = json.loads(p.read_text(encoding="utf-8"))
d["day_start_portfolio_xrp"] = d["week_start_portfolio_xrp"]
d["day_start_xrp"] = d.get("week_start_xrp")
d["day_start_rlusd"] = d.get("week_start_rlusd")
d["day_start_utc"] = d["week_start_utc"]
p.write_text(json.dumps(d, indent=2), encoding="utf-8")
print("day_start fixed to", d["day_start_portfolio_xrp"])

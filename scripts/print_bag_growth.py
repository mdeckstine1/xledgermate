"""Print key bag-growth metrics from HUD /state JSON on stdin."""
import json
import sys

d = json.load(sys.stdin)
bg = d.get("bag_growth") or {}
inv = d.get("inventory") or {}
bal = d.get("balances") or {}
dec = d.get("decision") or {}

print("timestamp:", d.get("timestamp") or d.get("updated_at"))
print("xrp:", bal.get("xrp"))
print("rlusd:", bal.get("rlusd"))
print("mid:", bal.get("mid_rlusd_per_xrp"))
print("portfolio_xrp_equiv:", inv.get("portfolio_xrp_equiv"))
print("xrp_alloc_pct:", inv.get("xrp_allocation_pct"))
print("target:", inv.get("target_xrp_ratio"))
print("deviation:", inv.get("deviation"))
print("decision:", dec.get("action") if isinstance(dec, dict) else dec)
print("decision_reason:", dec.get("reason") if isinstance(dec, dict) else None)
print("--- bag_growth ---")
for k in sorted(bg.keys()):
    v = bg[k]
    if v is not None:
        print(f"{k}: {v}")
print("--- session ---")
print("session_pnl_xrp_estimate:", d.get("session_pnl_xrp_estimate"))
print("realized_pnl_24h:", d.get("realized_pnl_24h"))

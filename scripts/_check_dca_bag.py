#!/usr/bin/env python3
"""One-off: print bag DCA from tax CSV (debug)."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha.reporting.tax_ledger import estimate_open_lot_cost_basis, load_all_tax_rows

logs = Path("logs")
rows = load_all_tax_rows(logs)
buy_xrp = sell_xrp = 0.0
for row in rows:
    if str(row.get("taxable") or "").upper() != "Y":
        continue
    side = (row.get("side") or row.get("event_type") or "").upper()
    try:
        xrp = float(row.get("xrp_amount") or 0)
    except (TypeError, ValueError):
        continue
    if side == "BUY":
        buy_xrp += xrp
    elif side == "SELL":
        sell_xrp += xrp
avg, rem = estimate_open_lot_cost_basis(logs)
print(f"tax_rows={len(rows)} buy_xrp={buy_xrp:.4f} sell_xrp={sell_xrp:.4f}")
print(f"open_lot_avg={avg:.6f} remaining_xrp={rem:.4f}")

buy_rlusd = sell_rlusd = 0.0
for row in rows:
    if str(row.get("taxable") or "").upper() != "Y":
        continue
    side = (row.get("side") or row.get("event_type") or "").upper()
    try:
        xrp = float(row.get("xrp_amount") or 0)
        rlusd = float(row.get("rlusd_amount") or 0)
        price = float(row.get("price_rlusd_per_xrp") or 0)
    except (TypeError, ValueError):
        continue
    if side == "BUY":
        buy_rlusd += rlusd if rlusd > 0 else xrp * price
    elif side == "SELL":
        sell_rlusd += rlusd if rlusd > 0 else xrp * price
if buy_xrp > 0:
    print(f"lifetime_avg_buy={buy_rlusd / buy_xrp:.6f}")
print(f"net_rlusd_flow={buy_rlusd - sell_rlusd:.2f}")

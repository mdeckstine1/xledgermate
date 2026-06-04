#!/usr/bin/env python3
"""One-off session analysis from logs."""
import csv
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    rs = json.loads((ROOT / "logs/runtime_state.json").read_text(encoding="utf-8"))
    mid = float(rs["mid_price"])
    xrp = float(rs["balance_xrp"])
    rlusd = float(rs["balance_rlusd"])
    total = xrp + rlusd / mid
    xrp_pct = xrp / total * 100

    print("=== CURRENT SESSION (engine) ===")
    print(f"Cycles: {rs['cycle_count']} | Profile: {rs['active_profile']} | Mode: {rs['inventory_mode']}")
    print(f"Portfolio: {rs['portfolio_value_xrp']:.4f} XRP")
    print(f"Session MTM PnL: {rs['session_pnl_mtm_xrp']:+.4f} | Balance PnL: {rs['session_pnl_balance_xrp']:+.4f}")
    print(f"XRP: {xrp:.2f} ({xrp_pct:.1f}pct) | RLUSD: {rlusd:.2f} | Target 55pct XRP")
    print(f"Mid: {mid:.6f} | Book spread: {rs['book_spread_pct']:.3f}pct")
    print(f"Fills (tracker): {rs['fills_session']} | Cancel/fill: {rs['cancel_per_fill']:.2f}")
    print(f"Toxic: {rs['toxic_fill_ratio']*100:.0f}pct / @30s {rs['toxic_fill_ratio_30s']*100:.0f}pct | Mean 30s markout: {rs['mean_markout_30s_pct']:+.3f}pct")
    print(f"Policy: {rs.get('quoting_policy_label', '')}")
    print(f"pause_bids={rs['pause_bids']} pause_asks={rs['pause_asks']} | dynamic_edge={rs['dynamic_min_edge_enabled']}")
    print(f"eff_edge={rs['effective_min_edge_pct']:.3f}pct | market_edge_met={rs['market_edge_met']} capture={rs['market_edge_pct']:+.3f}pct")
    print(f"Open offers: {rs['open_offers_count']} | {rs['last_execution_summary']}")

    # Trades since last MAJOR (session)
    rows = list(csv.DictReader((ROOT / "logs/trades_2026-06.csv").open(encoding="utf-8")))
    majors = [i for i, r in enumerate(rows) if r.get("event_type") == "MAJOR" and "Engine started" in (r.get("notes") or "")]
    start = majors[-1] if majors else 0
    session = rows[start:]
    fills = [r for r in session if r.get("event_type") in ("BUY", "SELL") or r.get("side") in ("BUY", "SELL")]
    buys = [r for r in fills if (r.get("side") or "").upper() == "BUY"]
    sells = [r for r in fills if (r.get("side") or "").upper() == "SELL"]

    def vol(lst):
        return sum(float(r.get("xrp_amount") or 0) for r in lst)

    def prof(lst):
        return sum(float(r.get("profit_xrp_equiv") or 0) for r in lst)

    print("\n=== CSV SESSION (since last engine start) ===")
    if session:
        print(f"Window: {session[0].get('timestamp_utc', '')[:19]} -> {session[-1].get('timestamp_utc', '')[:19]}")
    print(f"Fills: {len(fills)} ({len(buys)} BUY / {len(sells)} SELL)")
    print(f"Volume: BUY {vol(buys):.2f} XRP | SELL {vol(sells):.2f} XRP | net XRP {vol(buys)-vol(sells):+.2f}")
    print(f"Spread capture (logged): BUY {prof(buys):+.4f} | SELL {prof(sells):+.4f} | total {prof(fills):+.4f} XRP")
    neg = sum(1 for r in fills if float(r.get("profit_xrp_equiv") or 0) < 0)
    print(f"Negative capture fills: {neg}/{len(fills)} ({100*neg/max(1,len(fills)):.0f}pct)")

    # Large fills
    large = sorted(fills, key=lambda r: -float(r.get("xrp_amount") or 0))[:8]
    print("\nLargest fills:")
    for r in large:
        print(
            f"  {r.get('timestamp_utc','')[:19]} {(r.get('side') or ''):4} "
            f"{float(r.get('xrp_amount',0) or 0):.2f} XRP capture={float(r.get('profit_xrp_equiv',0) or 0):+.4f}"
        )

    # Current engine session only (13:37+ restart baseline)
    baseline_ts = "2026-06-03T13:37"
    recent = [r for r in fills if (r.get("timestamp_utc") or "") >= baseline_ts]
    if recent:
        print(f"\n=== POST-13:37 RESTART ({len(recent)} fills) ===")
        rb, rs_ = [r for r in recent if r.get("side") == "BUY"], [r for r in recent if r.get("side") == "SELL"]
        print(f"BUY {vol(rb):.2f} | SELL {vol(rs_):.2f} | capture {prof(recent):+.4f} XRP")


if __name__ == "__main__":
    main()

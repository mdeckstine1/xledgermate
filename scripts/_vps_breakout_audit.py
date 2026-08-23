#!/usr/bin/env python3
"""Audit breakout window: mid path, bag/stack, buy vs sell activity."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOGS = Path("logs")


def parse_ts(raw: str):
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except ValueError:
        return None


def main() -> None:
    state = json.loads((LOGS / "alpha_runtime_state.json").read_text())
    bag = state.get("bag_growth") or {}
    mid = float(state.get("mid") or 0)
    xrp = float(state.get("xrp") or 0)
    rlusd = float(state.get("rlusd") or 0)
    port = float(state.get("portfolio_xrp_equiv") or 0)
    print("=== NOW ===")
    print(f"mid={mid:.6f} xrp={xrp:.2f} rlusd={rlusd:.2f}")
    print(f"portfolio_xrp_eq={port:.2f} portfolio_rlusd_eq={port * mid:.2f}")
    print(f"stack_bot={bag.get('xrp_stack_delta_bot')} bot_added={bag.get('since_baseline_bot_xrp')}")
    print(f"day={bag.get('day_delta_xrp')} week={bag.get('week_delta_xrp')} off_ath={bag.get('off_high_xrp')}")
    print(f"ath={bag.get('high_water_portfolio_xrp')}")

    # Price path from bag week / session
    week = json.loads((LOGS / "alpha_bag_week.json").read_text())
    sess = json.loads((LOGS / "alpha_session.json").read_text())
    print("\n=== ANCHORS ===")
    print(f"week_start_port={week.get('week_start_portfolio_xrp')} week_xrp={week.get('week_start_xrp')} week_rlusd={week.get('week_start_rlusd')}")
    print(f"day_start_port={week.get('day_start_portfolio_xrp')}")
    print(f"session last_xrp={sess.get('last_xrp')} last_rlusd={sess.get('last_rlusd')} last_port={sess.get('last_portfolio_xrp')}")

    # Tax fills last 14 days
    since = datetime.now(tz=timezone.utc) - timedelta(days=14)
    buys = sells = 0
    buy_xrp = sell_xrp = 0.0
    rows_out = []
    for path in sorted(LOGS.glob("trades_2026-08.csv")):
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                ts = parse_ts(row.get("timestamp_utc") or "")
                if ts is None or ts < since:
                    continue
                side = (row.get("side") or "").upper()
                try:
                    # tax csv may put size in different cols
                    sz = float(row.get("xrp") or row.get("xrp_amount") or 0)
                except ValueError:
                    sz = 0.0
                px = row.get("price_rlusd_per_xrp") or row.get("price")
                notes = (row.get("notes") or "")[:70]
                if side == "BUY":
                    buys += 1
                    buy_xrp += sz
                elif side == "SELL":
                    sells += 1
                    sell_xrp += sz
                rows_out.append((ts.isoformat()[:19], side, sz, px, notes))

    print("\n=== TAX FILLS ~14d ===")
    print(f"buys={buys} buy_xrp_col_sum={buy_xrp:.1f} sells={sells} sell_xrp_col_sum={sell_xrp:.1f}")
    print("last 20:")
    for r in rows_out[-20:]:
        print(f"  {r[0]} {r[1]:4s} xrp={r[2]} px={r[3]} {r[4]}")

    # Activity reasons last 400
    act = (LOGS / "alpha_activity.jsonl").read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
    reasons = Counter()
    actions = Counter()
    breakoutish = []
    for line in act:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        a = str(row.get("action") or row.get("event") or "")
        r = str(row.get("reason") or row.get("message") or "")
        if a == "cycle" or row.get("event") == "cycle":
            actions["cycle"] += 1
        if "place_" in a or a in ("place_bid", "place_ask"):
            actions[a] += 1
        if r:
            reasons[r[:90]] += 1
        low = r.lower()
        if any(k in low for k in ("bull_run", "breakout", "near_high", "harvest", "heavy_prefer", "accumulation", "dip")):
            breakoutish.append(f"{str(row.get('ts') or '')[:19]} {a} {r[:100]}")

    print("\n=== ACTIVITY (last ~400) actions ===")
    for a, c in actions.most_common(10):
        print(f"  {c:3d} {a}")
    print("top reasons:")
    for r, c in reasons.most_common(12):
        print(f"  {c:3d} {r}")
    print("\nbreakout-related sample (last 25):")
    for line in breakoutish[-25:]:
        print(f"  {line}")

    # Explain XRP-eq vs RLUSD-eq on a pump
    print("\n=== PUMP ACCOUNTING ===")
    print("When mid (RLUSD/XRP) rises:")
    print("  - XRP coins keep count; USD/RLUSD wealth of coins rises")
    print("  - RLUSD powder converts to FEWER XRP-eq → TOTAL BAG (XRP-eq) can fall")
    print("  - Selling XRP into strength (harvest/trim) cuts stack coins, adds powder")
    print(f"  NOW: {xrp:.0f} XRP + {rlusd:.0f} RLUSD = {port:.0f} XRP-eq = {port*mid:.0f} RLUSD-eq")


if __name__ == "__main__":
    main()

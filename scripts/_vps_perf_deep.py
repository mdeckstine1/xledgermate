#!/usr/bin/env python3
"""Deeper performance diagnostics: stale offers, tax, inventory math."""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOGS = Path("logs")


def main() -> None:
    state = json.loads((LOGS / "alpha_runtime_state.json").read_text())
    mid = float(state.get("mid") or state.get("book", {}).get("mid") or 0)
    xrp = float(state.get("xrp") or 0)
    rlusd = float(state.get("rlusd") or 0)
    port = float(state.get("portfolio_xrp_equiv") or 0)
    inv = state.get("inventory") or {}
    print("=== INVENTORY MATH ===")
    print(f"xrp_ratio={xrp/port if port else None:.4f} target={inv.get('target_xrp_ratio')} dev={inv.get('deviation')}")
    print(f"powder_xrp_eq={rlusd/mid if mid else None:.2f} powder_rlusd={rlusd:.2f} floor=40")
    print(f"heavy_by={(xrp/port - float(inv.get('target_xrp_ratio') or 0.85))*100 if port else None:.2f} pp vs target")

    offers = state.get("open_offers") or []
    print("\n=== OPEN OFFERS vs MID ===")
    print(f"mid={mid:.6f}")
    for o in offers:
        price = o.get("price") or o.get("quality_price") or o.get("taker_gets")
        try:
            p = float(price)
        except (TypeError, ValueError):
            p = None
            # try nested
            p = o.get("price_rlusd_per_xrp")
            p = float(p) if p is not None else None
        side = o.get("side") or o.get("offer_side") or o.get("type")
        size = o.get("size_xrp") or o.get("size")
        seq = o.get("sequence") or o.get("seq")
        if p and mid:
            dist = (p / mid - 1.0) * 100.0
            print(f"  seq={seq} side={side} price={p:.6f} size={size} dist_to_mid={dist:+.3f}%")
        else:
            print(f"  raw={json.dumps(o)[:200]}")

    ss = json.loads((LOGS / "alpha_strength_sells.json").read_text())
    print("\n=== STRENGTH SELLS TRACKED ===")
    for o in ss.get("offers") or []:
        p = float(o.get("price_rlusd_per_xrp") or 0)
        dist = (p / mid - 1.0) * 100.0 if mid else 0
        print(f"  seq={o.get('sequence')} size={o.get('size_xrp')} price={p:.6f} purpose={o.get('purpose')} dist={dist:+.3f}%")

    # Tax CSV recent sells/buys Aug
    print("\n=== TAX CSV AUG (summary) ===")
    path = LOGS / "trades_2026-08.csv"
    if path.is_file():
        buys = sells = 0
        buy_xrp = sell_xrp = 0.0
        kinds = Counter()
        rows = []
        with path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                rows.append(row)
        print(f"rows={len(rows)}")
        for row in rows:
            side = (row.get("side") or row.get("event") or "").upper()
            try:
                sz = float(row.get("xrp") or row.get("size_xrp") or 0)
            except ValueError:
                sz = 0
            notes = row.get("notes") or row.get("note") or ""
            kinds[side or notes[:30]] += 1
            if "BUY" in side or "buy" in notes.lower():
                buys += 1
                buy_xrp += sz
            if "SELL" in side or "sell" in notes.lower() or "strength" in notes.lower():
                sells += 1
                sell_xrp += sz
        print(f"kinds={kinds.most_common(15)}")
        print(f"buy_events~{buys} buy_xrp~{buy_xrp:.1f} sell_events~{sells} sell_xrp~{sell_xrp:.1f}")
        print("last 15 rows:")
        for row in rows[-15:]:
            ts = (row.get("timestamp_utc") or "")[:19]
            print(f"  {ts} side={row.get('side')} xrp={row.get('xrp')} price={row.get('price_rlusd_per_xrp') or row.get('price')} notes={(row.get('notes') or '')[:70]}")

    # July too for stack context
    print("\n=== TAX CSV JULY (counts) ===")
    path = LOGS / "trades_2026-07.csv"
    if path.is_file():
        with path.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        print(f"rows={len(rows)}")
        sides = Counter((r.get("side") or "?") for r in rows)
        print(f"sides={sides}")

    # Decision stall duration from activity
    print("\n=== STALL DURATION (max_pending_sells) ===")
    act = (LOGS / "alpha_activity.jsonl").read_text(encoding="utf-8", errors="replace").splitlines()
    stall = 0
    first = last = None
    for line in act[-500:]:
        if "max_pending_sells" in line:
            stall += 1
            try:
                row = json.loads(line)
                ts = row.get("ts") or row.get("utc")
                if first is None:
                    first = ts
                last = ts
            except json.JSONDecodeError:
                pass
    print(f"in last 500 activity lines: max_pending_sells hits={stall} first={first} last={last}")

    # How many cycles not that reason recently?
    reasons = Counter()
    for line in act[-500:]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        r = str(row.get("reason") or row.get("message") or "")
        if r:
            reasons[r[:90]] += 1
    print("reason histogram last 500:")
    for r, c in reasons.most_common(12):
        print(f"  {c:4d} {r}")

    # Config offsets relevant to stale
    cfg = state.get("config_effective") or {}
    ov = json.loads((LOGS / "alpha_overrides.json").read_text()) if (LOGS / "alpha_overrides.json").is_file() else {}
    print("\n=== STALE / SELL RELATED KNOBS ===")
    for k in sorted(set(list(cfg) + list(ov))):
        if any(x in k for x in ("stale", "sell", "strength", "pending", "offset", "reload", "harvest", "dip", "trim")):
            print(f"  {k}: {cfg.get(k, ov.get(k))}")

    bag = state.get("bag_growth") or {}
    print("\n=== PERFORMANCE VERDICT INPUTS ===")
    print(f"bot_added={bag.get('since_baseline_bot_xrp')} ({bag.get('since_baseline_bot_pct')}%)")
    print(f"stack_bot_coins={bag.get('xrp_stack_delta_bot')}")
    print(f"day={bag.get('day_delta_xrp')} week={bag.get('week_delta_xrp')} off_ath={bag.get('off_high_xrp')}")
    print(f"mid_now={mid} — portfolio mostly XRP so bag tracks XRP price heavily")


if __name__ == "__main__":
    main()

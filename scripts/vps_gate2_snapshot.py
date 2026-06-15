#!/usr/bin/env python3
"""One-shot Gate 2 snapshot from VPS logs (run on server)."""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/root/xledgermate")
LOGS = REPO / "logs"


def main() -> int:
    print("=== VPS GATE 2 SNAPSHOT ===")
    print("utc_now:", datetime.now(timezone.utc).isoformat())
    print("repo:", REPO)

    rt_path = LOGS / "runtime_state.json"
    if not rt_path.exists():
        print("MISSING runtime_state.json")
        return 1
    rt = json.loads(rt_path.read_text(encoding="utf-8"))
    keys = [
        "version",
        "active_profile",
        "portfolio_value_xrp",
        "balance_xrp",
        "balance_rlusd",
        "session_fill_count",
        "session_spread_capture_xrp",
        "session_pnl_balance_delta_xrp",
        "cancel_per_fill",
        "toxic_ratio",
        "toxic_ratio_30s",
        "kill_switch_active",
        "kill_switch_reason",
        "open_offers_count",
        "dry_run",
        "trading_enabled",
        "mid_price",
        "last_cycle_ts_utc",
        "quoting_policy_label",
    ]
    print("\n--- runtime_state ---")
    for k in keys:
        if k in rt:
            print(f"  {k}: {rt[k]}")

    dec_path = LOGS / "decisions.jsonl"
    if dec_path.exists():
        n = sum(1 for _ in dec_path.open(encoding="utf-8", errors="replace"))
        print(f"\n--- decisions.jsonl lines: {n} ---")

    snap_path = LOGS / "portfolio_snapshots.csv"
    if snap_path.exists():
        rows = list(csv.DictReader(snap_path.open(encoding="utf-8", errors="replace")))
        if rows:
            first, last = rows[0], rows[-1]
            pk = "portfolio_xrp_equiv"
            try:
                delta = float(last.get(pk) or 0) - float(first.get(pk) or 0)
            except (TypeError, ValueError):
                delta = None
            print(f"\n--- portfolio_snapshots: {len(rows)} rows ---")
            print(f"  first {pk}: {first.get(pk)}")
            print(f"  last  {pk}: {last.get(pk)}")
            print(f"  delta: {delta}")

    print("\n--- trades CSV ---")
    all_fills = 0
    all_cap = 0.0
    all_neg = 0
    for f in sorted(LOGS.glob("trades_*.csv")):
        rows = list(csv.DictReader(f.open(encoding="utf-8", errors="replace")))
        fills = [r for r in rows if (r.get("event_type") or "").lower() == "fill"]
        cap = sum(float(r.get("profit_xrp_equiv") or 0) for r in fills)
        neg = sum(1 for r in fills if float(r.get("profit_xrp_equiv") or 0) < 0)
        all_fills += len(fills)
        all_cap += cap
        all_neg += neg
        ts0 = fills[0].get("timestamp_utc") if fills else "—"
        ts1 = fills[-1].get("timestamp_utc") if fills else "—"
        print(
            f"  {f.name}: fills={len(fills)} capture={cap:.4f} neg={neg} "
            f"({100*neg/max(1,len(fills)):.1f}%) range={ts0} .. {ts1}"
        )
    print(f"  TOTAL fills={all_fills} capture={all_cap:.4f} neg_pct={100*all_neg/max(1,all_fills):.1f}%")

    print("\n--- Gate 2 quick check (doc 05) ---")
    sess_fills = int(rt.get("session_fill_count") or 0)
    sess_cap = float(rt.get("session_spread_capture_xrp") or 0)
    sess_bal = float(rt.get("session_pnl_balance_delta_xrp") or 0)
    toxic = float(rt.get("toxic_ratio") or 0)
    checks = [
        ("2A fills >= 60 (cumulative)", all_fills >= 60, f"{all_fills}"),
        ("2A session fills (since restart)", sess_fills >= 0, f"{sess_fills}"),
        ("2B session balance PnL >= -0.85", sess_bal >= -0.85, f"{sess_bal:.4f}"),
        ("capture > 0 (cumulative)", all_cap > 0, f"{all_cap:.4f}"),
        ("2D neg fills <= 18% (cumulative)", (100 * all_neg / max(1, all_fills)) <= 18, f"{100*all_neg/max(1,all_fills):.1f}%"),
        ("2E toxic <= 32% (session)", toxic <= 0.32 or sess_fills < 50, f"{100*toxic:.1f}%"),
        ("kill clear", not rt.get("kill_switch_active"), str(rt.get("kill_switch_reason"))),
    ]
    for name, ok, val in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {val}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

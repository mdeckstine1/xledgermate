#!/usr/bin/env python3
"""Analyze current ws-engine session fills + M6 ages from VPS logs."""
from __future__ import annotations

import csv
import glob
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def session_start_from_log() -> datetime:
    log = LOGS / "xledgermate.log"
    if not log.exists():
        return datetime(2026, 6, 18, 22, 55, 39, tzinfo=timezone.utc)
    for line in reversed(log.read_text(encoding="utf-8", errors="replace").splitlines()):
        if "WsPureTradingEngine v2.1.21" in line and "| INFO |" in line:
            # 2026-06-18 22:55:39,483 | INFO | ...
            prefix = line.split("|", 1)[0].strip()
            dt = datetime.strptime(prefix.split(",")[0], "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
    return datetime(2026, 6, 18, 22, 55, 39, tzinfo=timezone.utc)


def main() -> int:
    start = session_start_from_log()
    print(f"Session start (v2.1.21 boot): {start.isoformat()}")
    print()

    m6_rows: list[dict] = []
    path = LOGS / "fill_quote_age.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            ts = _parse_ts(r.get("ts_utc", ""))
            if ts and ts >= start:
                m6_rows.append(r)

    print("=== M6 (this session) ===")
    print(f"fills logged: {len(m6_rows)}")
    if m6_rows:
        ages = [float(r["quote_age_seconds"]) for r in m6_rows]
        ages_s = sorted(ages)
        p95 = ages_s[int(0.95 * (len(ages_s) - 1))]
        print(
            f"quote_age_s: mean={statistics.mean(ages):.4f} "
            f"median={statistics.median(ages):.4f} p95={p95:.4f} max={max(ages):.1f}"
        )
        instant = sum(1 for a in ages if a < 0.01)
        stale = sum(1 for a in ages if a > 30)
        print(f"instant (<10ms): {instant}/{len(ages)} ({100*instant/len(ages):.0f}%)")
        print(f"stale (>30s): {stale}")
        by_side: dict[str, list[float]] = {}
        for r in m6_rows:
            by_side.setdefault(str(r.get("side", "?")), []).append(float(r["quote_age_seconds"]))
        for side, vals in sorted(by_side.items()):
            print(f"  {side}: n={len(vals)} median_age={statistics.median(vals):.3f}s")
        if stale:
            print("  stale fills:")
            for r in m6_rows:
                if float(r["quote_age_seconds"]) > 30:
                    print(
                        f"    {r.get('ts_utc')} {r.get('side')} "
                        f"age={r.get('quote_age_seconds')}s cycle={r.get('cycle')}"
                    )
    print()

    trade_rows: list[dict] = []
    for p in sorted(glob.glob(str(LOGS / "trades_*.csv"))):
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("Type") not in ("BUY", "SELL"):
                    continue
                ts = _parse_ts(row.get("Timestamp", ""))
                if ts and ts >= start:
                    trade_rows.append(row)

    print("=== TRADES (this session) ===")
    print(f"fills: {len(trade_rows)}")
    cap_sum = 0.0
    pos = neg = zero = 0
    buy_n = sell_n = 0
    for r in trade_rows:
        try:
            c = float(r.get("Spread_Capture_XRP") or 0)
        except ValueError:
            c = 0.0
        cap_sum += c
        if c > 0:
            pos += 1
        elif c < 0:
            neg += 1
        else:
            zero += 1
        if r.get("Type") == "BUY":
            buy_n += 1
        else:
            sell_n += 1
    print(f"spread_capture_sum: {cap_sum:.4f} XRP")
    print(f"pos/neg/zero: {pos}/{neg}/{zero}  neg_pct: {100*neg/max(len(trade_rows),1):.1f}%")
    print(f"BUY/SELL: {buy_n}/{sell_n}")
    print()

    rt = LOGS / "runtime_state.json"
    if rt.exists():
        d = json.loads(rt.read_text(encoding="utf-8"))
        print("=== RUNTIME SESSION ===")
        print(f"cycle_count: {d.get('cycle_count')}")
        print(f"fills_session: {d.get('fills_session')}")
        print(f"session_spread_capture_xrp: {d.get('session_spread_capture_xrp')}")
        print(f"session_pnl_balance_xrp: {d.get('session_pnl_balance_xrp')}")
        print(f"cancel_per_fill: {d.get('cancel_per_fill')}")
        print(f"toxic_fill_ratio: {d.get('toxic_fill_ratio')}")
        print(f"as_presence_pct: {d.get('as_presence_pct')}")
        print(f"g7: {d.get('g7_summary')}")
        print(f"visibility: {d.get('quote_visibility_summary')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

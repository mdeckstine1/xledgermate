#!/usr/bin/env python3
"""Balance-based mainnet drift from portfolio_snapshots (ignores bad mids)."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "logs" / "portfolio_snapshots.csv"


def main() -> int:
    rows: list[dict] = []
    with PATH.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("network") != "mainnet":
                continue
            if str(row.get("dry_run", "")).lower() == "true":
                continue
            try:
                mid = float(row["mid_rlusd_per_xrp"])
            except (KeyError, TypeError, ValueError):
                continue
            if mid < 0.45 or mid > 5.0:
                continue
            xrp = float(row["xrp_balance"])
            rlusd = float(row["rlusd_balance"])
            rows.append(
                {
                    "ts": row["timestamp_utc"],
                    "xrp": xrp,
                    "rlusd": rlusd,
                    "mid": mid,
                    "port": xrp + rlusd / mid,
                }
            )
    if not rows:
        print("No trustworthy mainnet live snapshots.")
        return 1

    def bal_at_mid(r: dict, m: float) -> float:
        return r["xrp"] + r["rlusd"] / m

    first, last = rows[0], rows[-1]
    ref_mid = last["mid"]
    start_bal = bal_at_mid(first, ref_mid)
    end_bal = bal_at_mid(last, ref_mid)
    mtm_start = first["port"]
    mtm_end = last["port"]

    print("=== Mainnet live (trustworthy mid only) ===")
    print(f"Snapshots: {len(rows)}")
    print(f"From: {first['ts']}")
    print(f"      XRP {first['xrp']:.4f} RLUSD {first['rlusd']:.4f} mid {first['mid']:.4f}")
    print(f"To:   {last['ts']}")
    print(f"      XRP {last['xrp']:.4f} RLUSD {last['rlusd']:.4f} mid {last['mid']:.4f}")
    print()
    print(f"Balance @ constant mid ({ref_mid:.4f}): {start_bal:.4f} -> {end_bal:.4f}  ({end_bal - start_bal:+.4f} XRP)")
    print(f"MTM portfolio (each cycle mid):         {mtm_start:.4f} -> {mtm_end:.4f}  ({mtm_end - mtm_start:+.4f} XRP)")
    print()
    print("Inventory shift:")
    print(f"  XRP:   {first['xrp'] - last['xrp']:+.4f} (sold net if negative)")
    print(f"  RLUSD: {last['rlusd'] - first['rlusd']:+.4f}")

    # Session chunks by >30min gap
    from datetime import datetime

    def parse_ts(s: str) -> datetime:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    chunks: list[list[dict]] = [[rows[0]]]
    for r in rows[1:]:
        gap = (parse_ts(r["ts"]) - parse_ts(chunks[-1][-1]["ts"])).total_seconds()
        if gap > 1800:
            chunks.append([r])
        else:
            chunks[-1].append(r)
    print()
    print("=== Per run (gap >30m), balance @ run end mid ===")
    total = 0.0
    for i, ch in enumerate(chunks, 1):
        a, b = ch[0], ch[-1]
        m = b["mid"]
        d = bal_at_mid(b, m) - bal_at_mid(a, m)
        total += d
        print(f"  Run {i}: {a['ts'][:16]} .. {b['ts'][:16]}  n={len(ch)}  d={d:+.4f} XRP")
    print(f"  Sum of runs: {total:+.4f} XRP")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

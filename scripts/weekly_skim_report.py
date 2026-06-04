#!/usr/bin/env python3
"""Weekly / session skim report from logs (Gate 1–2 metrics)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"


def _load_runtime() -> dict:
    path = LOGS / "runtime_state.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _session_fills() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(LOGS.glob("trades_*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    majors = [
        i
        for i, r in enumerate(rows)
        if r.get("event_type") == "MAJOR" and "Engine started" in (r.get("notes") or "")
    ]
    start = majors[-1] if majors else 0
    session = rows[start:]
    return [
        r
        for r in session
        if (r.get("side") or r.get("event_type", "")).upper() in ("BUY", "SELL")
    ]


def _visibility_pct() -> tuple[int, int, float]:
    path = LOGS / "portfolio_snapshots.csv"
    if not path.exists():
        return 0, 0, 0.0
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        return 0, 0, 0.0
    majors = [
        i
        for i, r in enumerate(rows)
        if "Engine started" in str(r.get("notes", ""))
    ]
    # snapshots lack MAJOR — use last N rows of file as proxy for recent session
    recent = rows[-min(500, len(rows)) :]
    total = len(recent)
    visible = sum(1 for r in recent if int(float(r.get("open_offers") or 0)) > 0)
    pct = (visible / total * 100.0) if total else 0.0
    return visible, total, pct


def main() -> int:
    rs = _load_runtime()
    fills = _session_fills()
    n = len(fills)
    capture = sum(float(r.get("profit_xrp_equiv") or 0) for r in fills)
    neg = sum(1 for r in fills if float(r.get("profit_xrp_equiv") or 0) < 0)
    volume = sum(float(r.get("xrp_amount") or 0) for r in fills)
    bps = (capture / volume * 10000.0) if volume > 0 else 0.0
    cap_per = capture / n if n else 0.0

    toxic = float(rs.get("toxic_fill_ratio") or 0) * 100
    toxic_30 = float(rs.get("toxic_fill_ratio_30s") or 0) * 100
    cancel_cf = float(rs.get("cancel_per_fill") or 0)
    vis_n, vis_total, vis_pct = _visibility_pct()

    print("=== XLedgerMate skim report ===")
    print(f"Profile: {rs.get('active_profile', '?')} | Cycles: {rs.get('cycle_count', 0)}")
    print(f"Portfolio: {float(rs.get('portfolio_value_xrp') or 0):.4f} XRP")
    print()
    print("--- Session fills (since last engine start) ---")
    print(f"Fills: {n} | Spread capture: {capture:+.4f} XRP")
    print(f"Capture / fill: {cap_per:+.4f} XRP | ~{bps:.2f} bps vs filled volume")
    print(f"Negative capture fills: {neg}/{n} ({100 * neg / max(1, n):.0f}%)")
    print()
    print("--- Protection ---")
    print(f"Toxic ratio: {toxic:.0f}% | Toxic @30s: {toxic_30:.0f}%")
    print(f"Cancel per fill: {cancel_cf:.2f}")
    print(f"Open offers (snapshot proxy): {vis_n}/{vis_total} cycles ({vis_pct:.0f}% visible)")
    print(f"Policy: {rs.get('quoting_policy_label', '')}")
    print(f"Pause bids/asks: {rs.get('pause_bids')}/{rs.get('pause_asks')}")
    print()
    print("--- Gate checklist ---")
    g1_fills = "PASS" if n >= 40 else "pending"
    g1_cap = "PASS" if capture > 0 else "pending"
    g1_toxic = "PASS" if toxic < 25 or n < 8 else "watch"
    g2_toxic = "PASS" if toxic < 20 and n >= 50 else "pending"
    print(f"Gate 1 fills >= 40: {g1_fills} ({n})")
    print(f"Gate 1 capture > 0: {g1_cap}")
    print(f"Gate 1 toxic < 25% (or <8 fills ignore): {g1_toxic}")
    print(f"Gate 2 toxic < 20% over 50+ fills: {g2_toxic}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

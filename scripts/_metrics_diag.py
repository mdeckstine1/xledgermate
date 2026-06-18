#!/usr/bin/env python3
import csv
import json
import sys
from pathlib import Path

repo = Path("/root/xledgermate")
sys.path.insert(0, str(repo))

rt = json.loads((repo / "logs/runtime_state.json").read_text())
print("=== runtime (engine-written) ===")
for k in (
    "session_spread_capture_xrp",
    "fills_session",
    "ws_fills_csv",
    "portfolio_value_xrp",
    "toxic_fill_ratio_30s",
    "drawdown_pct",
):
    print(f"  {k}: {rt.get(k)}")

rows = [
    r
    for r in csv.DictReader((repo / "logs/trades_2026-06.csv").open())
    if "WS pure fill" in (r.get("notes") or "")
]
fs = int(rt.get("fills_session") or 0)
session_rows = rows[-fs:] if fs > 0 else rows[-20:]
print(f"\n=== CSV ws fills total={len(rows)} session_window={len(session_rows)} (fills_session={fs}) ===")

from scripts.ws_path_session_report import session_spread_capture_xrp

book_pct = float(rt.get("book_spread_pct") or 0.1)
half_bps = max(3.0, (book_pct / 100.0) * 10_000.0 / 2.0)
hud_skim = session_spread_capture_xrp(fills_session=fs, half_spread_bps=half_bps)
print(f"hud_enriched skim (half_bps={half_bps:.2f}): {hud_skim:.4f}")

stored_sum = sum(float(r.get("profit_xrp_equiv") or 0) for r in session_rows)
print(f"session window stored profit sum: {stored_sum:.4f}")

from experimental.ws_feed.performance_metrics import build_performance_metrics

pm = build_performance_metrics(runtime=rt, logs_dir=repo / "logs")
cap = pm.get("capture") or {}
act = pm.get("activation") or {}
print("\n=== G6 / performance_metrics ===")
print(f"  ws_fills (all csv): {cap.get('ws_fills')}")
print(f"  total_capture_xrp: {cap.get('total_capture_xrp')}")
print(f"  pos_pct: {cap.get('positive_capture_pct')}")
print(f"  avg_bps: {cap.get('avg_capture_bps')}")
print(f"  neg_pct: {cap.get('neg_capture_pct')}")
print(f"  activation tier: {act.get('tier')}")
print(f"  activation summary: {act.get('summary')}")
for g in pm.get("grades") or []:
    print(f"  grade {g.get('id')}: {g.get('grade')} — {g.get('value')}")

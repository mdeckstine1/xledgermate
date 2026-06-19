#!/usr/bin/env python3
"""Runtime posture + wealth decomposition."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.wealth_metrics import compute_wealth_metrics

rt = json.loads((ROOT / "logs" / "runtime_state.json").read_text(encoding="utf-8"))
w = compute_wealth_metrics(rt)
print("=== wealth ===")
for k, v in w.items():
    if v is not None:
        print(f"  {k}: {v}")
print()
for k in (
    "inventory_label",
    "g2_spread_mult",
    "g2_scaler_label",
    "fill_quality_summary",
    "toxic_fill_ratio_30s",
    "mean_markout_30s_pct",
    "g7_summary",
    "execution_envelope_summary",
    "cancels_session",
    "fills_session",
):
    if k in rt:
        print(f"{k}: {rt[k]}")
qi = rt.get("quote_intents")
if isinstance(qi, list) and qi:
    q = qi[0]
    print(f"L1 bid: {q.get('bid_backoff_bps')}bps {q.get('bid_role')} ask: {q.get('ask_backoff_bps')}bps {q.get('ask_role')}")
elif isinstance(qi, dict):
    print(f"L1 bid: {qi.get('bid_backoff_bps')}bps {qi.get('bid_role')} ask: {qi.get('ask_backoff_bps')}bps {qi.get('ask_role')}")

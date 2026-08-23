#!/usr/bin/env python3
"""One-shot post-deploy verification (run on VPS)."""
import json
from pathlib import Path

log = Path("logs/xledgermate.log")
if log.exists():
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        if "WsPureTradingEngine v" in line or "ws_as_version" in line:
            print("LOG:", line[-120:])

rt_path = Path("logs/runtime_state.json")
if rt_path.exists():
    d = json.loads(rt_path.read_text(encoding="utf-8"))
    print(
        "RUNTIME:",
        "ws=", d.get("ws_as_version"),
        "cycle=", d.get("cycle_count"),
        "sample_count=", d.get("sample_count"),
        "hist_len=", len(d.get("sample_history") or []),
        "fill_age=", d.get("effective_quote_age_at_fill_seconds"),
        "stale_cross=", d.get("reservation_crossed_after_ws_sample"),
    )

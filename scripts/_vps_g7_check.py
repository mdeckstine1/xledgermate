#!/usr/bin/env python3
import json
from pathlib import Path
d = json.loads(Path("logs/runtime_state.json").read_text())
print("ws", d.get("ws_as_version"), "cycle", d.get("cycle_count"))
print("g7", d.get("g7_summary"))
print("backoff bid/ask", d.get("bid_touch_backoff_bps"), d.get("ask_touch_backoff_bps"))
print("visibility", d.get("worst_vs_touch_bps"), d.get("quote_visibility_summary"))
print("inv", d.get("inventory_label"), "g2", d.get("g2_grade"))

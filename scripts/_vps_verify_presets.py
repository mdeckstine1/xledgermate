#!/usr/bin/env python3
"""Quick VPS check: only Maximize + Unassed presets remain."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

from alpha.hud.maximize_preset import maximize_preset_payload
from alpha.hud.unassed_preset import unassed_preset_payload

gone = []
for m in ("walkaway", "long_build", "stack_growth", "bracket_edge"):
    path = f"alpha/hud/{m}_preset.py"
    if os.path.exists(path):
        print(f"FAIL still present: {path}")
        sys.exit(1)
    gone.append(m)

mx = maximize_preset_payload()
ua = unassed_preset_payload()
assert "maximize_comparison" in ua
assert "unassed_comparison" in mx
print("ok maximize:", mx["label"])
print("ok unassed:", ua["label"])
print("ok deleted:", ", ".join(gone))
print("ok maximize vs unassed deltas:", len(ua["maximize_comparison"]["different_operator_keys"]))

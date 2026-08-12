#!/usr/bin/env python3
"""Patch live operator overrides for autonomous Maximize (stale sells + grind arms)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("logs/alpha_overrides.json")

# Autonomy-critical keys (code defaults + maximize posture). No package imports.
PATCH = {
    "alpha_stale_pending_sell_enabled": True,
    "alpha_stale_pending_sell_max_drift_pct": 0.50,
    "alpha_stale_pending_sell_max_age_seconds": 0,
    "alpha_accumulation_harvest_move_24h_watch_pct": 2.0,
    "alpha_accumulation_harvest_pullback_arm_pct": 0.7,
    "alpha_accumulation_dip_move_24h_arm_pct": 2.0,
    "alpha_accumulation_dip_bounce_arm_pct": 0.25,
    "alpha_max_pending_sells": 2,
    "alpha_sell_limit_offset_pct": 0.08,
}


def main() -> None:
    data = {}
    if PATH.is_file():
        data = json.loads(PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    before = {k: data.get(k) for k in PATCH}
    data.update(PATCH)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(PATH)
    after = {k: data.get(k) for k in PATCH}
    print("patched", PATH)
    print("before", before)
    print("after", after)


if __name__ == "__main__":
    main()

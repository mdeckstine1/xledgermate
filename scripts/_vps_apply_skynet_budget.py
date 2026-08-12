#!/usr/bin/env python3
"""Apply token-saver Agent Smith budget/event defaults on VPS (no package imports)."""
from __future__ import annotations

import json
from pathlib import Path

PATH = Path("logs/alpha_skynet_agent.json")

PATCH = {
    "interval_cycles_min": 40,
    "interval_cycles_max": 60,
    "daily_call_budget": 48,
    "max_tokens": 1536,
    "full_mode_enabled": False,
    "event_triggers": {
        "enabled": True,
        "min_cycles_between_event_runs": 12,
        "decision_changed": False,
        "opportunity": False,
        "kill_switch": True,
        "drawdown_spike": True,
        "drawdown_spike_pct": 1.0,
        "session_loss": True,
        "session_loss_xrp": 8.0,
        "inventory_shift": True,
        "inventory_shift_dev": 0.12,
        "accumulation": True,
        "reload": True,
        "drawdown_reload": True,
        "sell_slot_stall": True,
        "powder_shortfall": True,
    },
}


def main() -> None:
    data = {}
    if PATH.is_file():
        try:
            data = json.loads(PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        if not isinstance(data, dict):
            data = {}
    before = {
        "interval_cycles_min": data.get("interval_cycles_min"),
        "interval_cycles_max": data.get("interval_cycles_max"),
        "daily_call_budget": data.get("daily_call_budget"),
        "max_tokens": data.get("max_tokens"),
        "event_enabled": (data.get("event_triggers") or {}).get("enabled"),
    }
    data["interval_cycles_min"] = PATCH["interval_cycles_min"]
    data["interval_cycles_max"] = PATCH["interval_cycles_max"]
    data["daily_call_budget"] = PATCH["daily_call_budget"]
    data["max_tokens"] = PATCH["max_tokens"]
    data["full_mode_enabled"] = False
    # Keep agent_enabled as operator left it (default True if missing after Maximize)
    if "agent_enabled" not in data:
        data["agent_enabled"] = True
    ev = data.get("event_triggers") if isinstance(data.get("event_triggers"), dict) else {}
    ev.update(PATCH["event_triggers"])
    data["event_triggers"] = ev
    # Don't wipe call counters mid-day unless missing
    data.setdefault("daily_calls_used", 0)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(PATH)
    print("patched", PATH)
    print("before", before)
    print(
        "after",
        {
            "interval_cycles_min": data.get("interval_cycles_min"),
            "interval_cycles_max": data.get("interval_cycles_max"),
            "daily_call_budget": data.get("daily_call_budget"),
            "max_tokens": data.get("max_tokens"),
            "agent_enabled": data.get("agent_enabled"),
            "event_enabled": data["event_triggers"].get("enabled"),
            "sell_slot_stall": data["event_triggers"].get("sell_slot_stall"),
        },
    )


if __name__ == "__main__":
    main()

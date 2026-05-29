"""Debounce / cooldown state for automatic profile switching."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AUTO_PROFILE_STATE_PATH = Path("logs/auto_profile_state.json")


@dataclass
class AutoProfileState:
    pending_profile: Optional[str] = None
    pending_cycles: int = 0
    last_auto_switch_utc: Optional[str] = None


def load_auto_profile_state() -> AutoProfileState:
    if not AUTO_PROFILE_STATE_PATH.exists():
        return AutoProfileState()
    try:
        data = json.loads(AUTO_PROFILE_STATE_PATH.read_text(encoding="utf-8"))
        return AutoProfileState(
            pending_profile=data.get("pending_profile"),
            pending_cycles=int(data.get("pending_cycles", 0)),
            last_auto_switch_utc=data.get("last_auto_switch_utc"),
        )
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return AutoProfileState()


def save_auto_profile_state(state: AutoProfileState) -> None:
    AUTO_PROFILE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pending_profile": state.pending_profile,
        "pending_cycles": state.pending_cycles,
        "last_auto_switch_utc": state.last_auto_switch_utc,
    }
    AUTO_PROFILE_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_auto_profile_pending() -> None:
    state = load_auto_profile_state()
    state.pending_profile = None
    state.pending_cycles = 0
    save_auto_profile_state(state)


def minutes_since_auto_switch(state: AutoProfileState) -> float:
    if not state.last_auto_switch_utc:
        return 9999.0
    try:
        last = datetime.fromisoformat(state.last_auto_switch_utc.replace("Z", "+00:00"))
        delta = datetime.now(tz=timezone.utc) - last.astimezone(timezone.utc)
        return max(0.0, delta.total_seconds() / 60.0)
    except (ValueError, TypeError):
        return 9999.0

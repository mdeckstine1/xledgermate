"""Track when the operator last interacted (Save Config) for auto profile switching."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ACTIVITY_PATH = Path("logs/operator_activity.json")


def touch_operator_activity(action: str = "save_config") -> None:
    ACTIVITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_action": action,
        "last_action_utc": datetime.now(tz=timezone.utc).isoformat(),
    }
    ACTIVITY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def minutes_since_last_operator_action(default_minutes: float = 9999.0) -> float:
    if not ACTIVITY_PATH.exists():
        return default_minutes
    try:
        data = json.loads(ACTIVITY_PATH.read_text(encoding="utf-8"))
        ts = data.get("last_action_utc")
        if not ts:
            return default_minutes
        last = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        delta = datetime.now(tz=timezone.utc) - last.astimezone(timezone.utc)
        return max(0.0, delta.total_seconds() / 60.0)
    except (json.JSONDecodeError, ValueError, TypeError):
        return default_minutes
